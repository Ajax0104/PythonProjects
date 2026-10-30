"""Bounded source evidence for internal review, independent of V4 valuations/UI."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit

import requests

from core.feedback_store import Relationship
from crowe_acquisition import acquire_catalog_page
from ebay_api_client import get_oauth_token


MAX_CANDIDATES = 50
MAX_PAGE_LOTS = 200
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
TIMEOUT = (5, 20)
EBAY_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_ITEM_FIELDS = (
    "itemId", "itemWebUrl", "title", "image", "thumbnailImages", "additionalImages",
    "condition", "conditionId", "price", "shippingOptions", "buyingOptions",
)


class EvidenceError(ValueError):
    """Invalid source structure or conflicting identity; no inferred repair."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, label):
    if (not isinstance(value, str) or not value.strip() or value != value.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise EvidenceError(f"{label} must be nonempty text without surrounding whitespace or controls")
    return value


def _crowe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value):
        raise EvidenceError("Crowe internal IDs must be numeric strings")
    return value


def _object(value, label):
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    return value


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(_text(value, "retrieved_at").replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError("Timezone required")
    except ValueError as error:
        raise EvidenceError("Source retrieval timestamp must include a timezone") from error
    return value


def _clone(value):
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (ValueError, TypeError, RecursionError) as error:
        raise EvidenceError("Source evidence must be finite JSON") from error


def _query_matches(key, name, arguments):
    try:
        if not isinstance(key, str) or not key.startswith(name + "(") or not key.endswith(")"):
            return False
        decoded = json.loads(key[len(name) + 1:-1])
        return json.dumps(decoded, sort_keys=True) == json.dumps(arguments, sort_keys=True)
    except ValueError:
        return False


def acquire_crowe_for_review(catalog_url, *, auction_id, query_arguments,
                             detail_url=None, lot_id=None, http_get=None):
    """Use the existing bounded adapter, adding per-response receipt timestamps.

    Times record when HTTP headers are received, before the adapter reads the
    body. Any acquisition/parser failure propagates; no partial page is returned.
    """
    receipts = []
    get = http_get or requests.get

    def timed_get(*args, **kwargs):
        response = get(*args, **kwargs)
        receipts.append(_now())
        return response

    result = acquire_catalog_page(
        catalog_url, auction_id=auction_id, query_arguments=query_arguments,
        detail_url=detail_url, lot_id=lot_id, http_get=timed_get,
    )
    return {**result, "retrieved_at": {
        "catalog": receipts[0], "detail": receipts[1] if result["detail"] is not None else None,
    }}


def _items(body, limit):
    _object(body, "eBay response")
    total = body.get("total")
    if total is not None and (type(total) is not int or total < 0):
        raise EvidenceError("Invalid eBay total")
    items = body.get("itemSummaries", [] if total == 0 else None)
    if not isinstance(items, list) or len(items) > limit:
        raise EvidenceError("Missing or oversized eBay itemSummaries")
    if total is not None and (len(items) > total or (total > 0 and not items)):
        raise EvidenceError("Contradictory eBay result count")
    seen, result = set(), []
    for item in items:
        _object(item, "eBay item")
        item_id = _text(item.get("itemId"), "eBay itemId")
        if item_id in seen:
            raise EvidenceError("Duplicate eBay itemId")
        seen.add(item_id)
        for field in ("itemWebUrl", "title", "condition", "conditionId"):
            if item.get(field) is not None and not isinstance(item[field], str):
                raise EvidenceError(f"Invalid eBay {field}")
        for field in ("price", "image"):
            if item.get(field) is not None:
                _object(item[field], field)
        for field in ("shippingOptions", "thumbnailImages", "additionalImages", "buyingOptions"):
            if item.get(field) is not None and not isinstance(item[field], list):
                raise EvidenceError(f"Invalid eBay {field}")
        result.append({key: _clone(item[key]) for key in _ITEM_FIELDS if key in item})
    return result


def fetch_ebay_candidates(*, auction_id, lot_id, query, filters=None, sort=None,
                          limit=20, marketplace_id="EBAY_US", http_get=None, token_provider=None):
    """One Browse search, no retries/fallback prices. API failures are explicit outcomes.

    Caller/configuration errors raise EvidenceError. Expected authentication,
    transport and source failures return ERROR with zero candidates. Tokens,
    response headers and arbitrary API error messages are never returned/stored.
    """
    _crowe_id(auction_id)
    _crowe_id(lot_id)
    _text(query, "query")
    _text(marketplace_id, "marketplace_id")
    if type(limit) is not int or not 1 <= limit <= MAX_CANDIDATES:
        raise EvidenceError(f"limit must be between 1 and {MAX_CANDIDATES}")
    params = {"q": query, "limit": str(limit)}
    for key, value in (("filter", filters), ("sort", sort)):
        if value is not None:
            params[key] = _text(value, key)
    outcome = {
        "target": {"auction_source": "crowe", "auction_id": auction_id, "lot_id": lot_id},
        "marketplace_source": "ebay",
        "request": {"endpoint": EBAY_SEARCH_URL, "params": params,
                    "marketplace_id": marketplace_id,
                    "url": requests.Request("GET", EBAY_SEARCH_URL, params=params).prepare().url},
        "attempted_at": _now(), "retrieved_at": None, "http_status": None,
        "status": "ERROR", "error": None, "response_metadata": {}, "items": [],
    }

    def failed(code):
        outcome["status"] = "ERROR"
        outcome["items"] = []
        outcome["error"] = {"code": code}
        return outcome

    try:
        token = (token_provider or get_oauth_token)()
    except requests.RequestException:
        return failed("AUTH_ERROR")
    if not isinstance(token, str) or not token.strip():
        return failed("AUTH_UNAVAILABLE")
    response = None
    try:
        response = (http_get or requests.get)(
            EBAY_SEARCH_URL, params=params,
            headers={"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": marketplace_id},
            timeout=TIMEOUT, allow_redirects=False, stream=True, verify=True,
        )
        outcome["retrieved_at"] = _now()
        outcome["http_status"] = response.status_code
        if response.history or response.url != outcome["request"]["url"]:
            return failed("UNEXPECTED_REDIRECT")
        if response.status_code != 200:
            return failed("HTTP_ERROR")
        if response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            return failed("NON_JSON_RESPONSE")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                return failed("RESPONSE_TOO_LARGE")
            content.extend(chunk)
        def invalid_constant(_):
            raise EvidenceError("Nonfinite JSON constant")

        body = _clone(json.loads(content, parse_constant=invalid_constant))
        _object(body, "eBay response")
        # Restrict diagnostics to codes, never token-bearing messages/parameters.
        outcome["response_metadata"] = {key: body[key] for key in ("total", "limit", "offset") if key in body}
        for key in ("errors", "warnings"):
            if key in body:
                if not isinstance(body[key], list) or any(not isinstance(e, dict) for e in body[key]):
                    raise EvidenceError("Malformed API diagnostics")
                outcome["response_metadata"][key] = [
                    {name: e[name] for name in ("errorId", "domain", "category") if name in e}
                    for e in body[key]
                ]
        if body.get("errors"):
            return failed("API_ERROR")
        outcome["items"] = _items(body, limit)
        outcome["status"] = "READY" if outcome["items"] else "EMPTY"
        return _clone(outcome)
    except requests.RequestException:
        return failed("TRANSPORT_ERROR")
    except (ValueError, UnicodeError):
        return failed("INVALID_RESPONSE")
    finally:
        if response is not None:
            response.close()


def _crowe_result(result, kind):
    _object(result, kind)
    auction = _object(result.get("auction"), "auction")
    aid = _crowe_id(auction.get("auction_id"))
    source = _object(result.get("source"), "source")
    if source.get("kind") != kind or source.get("format") != "embedded_apollo":
        raise EvidenceError("Unexpected Crowe source kind/format")
    url = _text(source.get("url"), "Crowe request URL")
    try:
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.hostname != "bids.crauctions.com"
                or parts.username is not None or parts.password is not None
                or parts.port not in (None, 443) or parts.fragment):
            raise ValueError("Invalid source URL")
    except ValueError as error:
        raise EvidenceError("Invalid Crowe request URL") from error
    lots = result.get("lots")
    if not isinstance(lots, list) or len(lots) > MAX_PAGE_LOTS or (kind == "detail" and len(lots) != 1):
        raise EvidenceError("Expected a bounded selected Crowe page")
    seen = set()
    for lot in lots:
        _object(lot, "lot")
        lid = _crowe_id(lot.get("lot_id"))
        number = _text(lot.get("lot_number"), "displayed lot number")
        raw = _object(lot.get("raw_fields"), "raw lot fields")
        if (lot.get("auction_id") != aid or lid in seen or lot.get("source_record_key") != "AuctionLot." + lid
                or raw.get("auction_id") != aid or raw.get("auction_lot_id") != lid
                or raw.get("lot_number") != number):
            raise EvidenceError("Conflicting Crowe lot identity")
        seen.add(lid)
    args = _object(source.get("query_arguments"), "Crowe query arguments")
    if not _query_matches(source.get("query_key"), "lots" if kind == "catalog" else "lot", args):
        raise EvidenceError("Encoded Crowe query disagrees with query arguments")
    if kind == "catalog":
        pagination = _object(result.get("pagination"), "pagination")
        page_args = _object(args.get("pagination"), "query pagination")
        if (_object(args.get("filter"), "query filter").get("auction_id") != aid
                or not _query_matches(source.get("auction_query_key"), "auction", {"auction_id": aid})
                or not re.fullmatch(r"/auctions/" + aid + r"(?:-[^/]+)?/?", parts.path)):
            raise EvidenceError("Conflicting catalog query identity")
        if (any(type(pagination.get(k)) is not int for k in ("page", "pageSize", "total", "returned_count"))
                or not 1 <= pagination["pageSize"] <= MAX_PAGE_LOTS or pagination["page"] < 1
                or pagination["returned_count"] != len(lots) or not len(lots) <= pagination["total"]
                or len(lots) > pagination["pageSize"]
                or any(pagination[k] != page_args.get(k) for k in ("page", "pageSize"))):
            raise EvidenceError("Inconsistent catalog pagination")
    elif (args.get("auction_lot_id") != lots[0]["lot_id"] or not re.fullmatch(
            r"/auctions/" + aid + r"/lot/" + lots[0]["lot_id"] + r"(?:-[^/]+)?/?", parts.path)):
        raise EvidenceError("Conflicting detail query identity")
    return aid


def _search_result(search, auction_id, selected_ids):
    _object(search, "search")
    target = _object(search.get("target"), "search target")
    lid = _crowe_id(target.get("lot_id"))
    if (target.get("auction_source") != "crowe" or target.get("auction_id") != auction_id
            or lid not in selected_ids or search.get("marketplace_source") != "ebay"):
        raise EvidenceError("Search target is outside the selected auction/page")
    request = _object(search.get("request"), "search request")
    params = _object(request.get("params"), "search parameters")
    if set(params) - {"q", "filter", "sort", "limit"}:
        raise EvidenceError("Unexpected search parameter")
    _text(params.get("q"), "query")
    for field in ("filter", "sort"):
        if field in params:
            _text(params[field], field)
    _text(request.get("marketplace_id"), "marketplace_id")
    limit = params.get("limit")
    if not isinstance(limit, str) or limit not in {str(i) for i in range(1, MAX_CANDIDATES + 1)}:
        raise EvidenceError("Invalid search limit")
    if (request.get("endpoint") != EBAY_SEARCH_URL or request.get("url") !=
            requests.Request("GET", EBAY_SEARCH_URL, params=params).prepare().url):
        raise EvidenceError("Conflicting eBay request context")
    _timestamp(search.get("attempted_at"))
    if search.get("retrieved_at") is not None:
        _timestamp(search["retrieved_at"])
    status = search.get("status")
    items = search.get("items")
    if status not in ("READY", "EMPTY", "ERROR") or not isinstance(items, list):
        raise EvidenceError("Invalid search outcome")
    if status == "ERROR":
        if items or not _object(search.get("error"), "search error").get("code"):
            raise EvidenceError("A failed search cannot contain candidates")
    else:
        if search.get("http_status") != 200 or search.get("retrieved_at") is None or search.get("error") is not None:
            raise EvidenceError("Successful search lacks response provenance")
        if bool(items) != (status == "READY"):
            raise EvidenceError("Search status contradicts candidates")
        metadata = _object(search.get("response_metadata"), "response metadata")
        if metadata.get("errors"):
            raise EvidenceError("Successful search contains API errors")
        body = {"itemSummaries": items}
        if "total" in metadata:
            body["total"] = metadata["total"]
        search["items"] = _items(body, int(limit))
    return lid


def build_review_page(crowe, *, searches=(), store):
    """Validate the complete selected-page input, then store candidate evidence.

    Consumes acquire_crowe_for_review output, or existing acquisition output with
    an explicit retrieved_at mapping supplied by its caller. Returns all lots,
    including NOT_REQUESTED/EMPTY/ERROR outcomes. Never records human judgments.
    Storage failures propagate; previously committed bundles may remain (retry
    identical inputs safely). No page-wide transaction or queue persistence.
    """
    crowe = _clone(_object(crowe, "Crowe acquisition"))
    catalog, detail = crowe.get("catalog"), crowe.get("detail")
    aid = _crowe_result(catalog, "catalog")
    times = _object(crowe.get("retrieved_at"), "Crowe receipt timestamps")
    _timestamp(times.get("catalog"))
    by_id = {lot["lot_id"]: lot for lot in catalog["lots"]}
    detailed_id = None
    if detail is not None:
        if _crowe_result(detail, "detail") != aid:
            raise EvidenceError("Detail belongs to another auction")
        _timestamp(times.get("detail"))
        detailed_id = detail["lots"][0]["lot_id"]
        if (detailed_id not in by_id or detail["lots"][0]["lot_number"] != by_id[detailed_id]["lot_number"]):
            raise EvidenceError("Detail does not match a selected catalog lot")
    elif times.get("detail") is not None:
        raise EvidenceError("Detail timestamp supplied without detail evidence")
    if not isinstance(searches, (list, tuple)) or len(searches) > len(by_id):
        raise EvidenceError("At most one explicit search per selected lot is supported")
    selected_searches = {}
    for search in _clone(searches):
        lid = _search_result(search, aid, by_id)
        if lid in selected_searches:
            raise EvidenceError("Duplicate search for a selected lot")
        selected_searches[lid] = search
    queue, bundles = [], []
    for lid, lot in by_id.items():
        snapshot = {
            "auction_source": "crowe", "auction_id": aid, "lot_id": lid, "lot_number": lot["lot_number"],
            "catalog": {"source": catalog["source"], "auction": catalog["auction"],
                        "pagination": catalog["pagination"], "retrieved_at": times["catalog"], "lot": lot},
            "detail": None,
        }
        if lid == detailed_id:
            snapshot["detail"] = {"source": detail["source"], "auction": detail["auction"],
                                  "retrieved_at": times["detail"], "lot": detail["lots"][0]}
        search = selected_searches.get(lid)
        context = {key: value for key, value in search.items() if key != "items"} if search else None
        entry = {"lot": snapshot, "outcome": search["status"] if search else "NOT_REQUESTED",
                 "search": context, "candidates": []}
        for rank, item in enumerate(search["items"] if search else [], start=1):
            relationship = Relationship("crowe", aid, lid, "ebay", item["itemId"])
            listing = {"marketplace_source": "ebay", "api": "browse",
                       "retrieved_at": search["retrieved_at"], "item": item}
            candidate_context = {"schema_version": 1, "search": context, "rank": rank}
            bundle = {"relationship": asdict(relationship), "lot": snapshot,
                      "listing": listing, "candidate_context": candidate_context}
            # This versions evidence contents, not the auction/lot/listing identity.
            digest = hashlib.sha256(json.dumps(bundle, sort_keys=True, separators=(",", ":"),
                                               allow_nan=False).encode()).hexdigest()
            evidence_id = "audit-v1-" + digest
            bundles.append((evidence_id, relationship, snapshot, listing, candidate_context))
            entry["candidates"].append({"evidence_id": evidence_id, "relationship": asdict(relationship),
                                         "listing": listing, "rank": rank})
        queue.append(entry)
    # All mandatory identities have been checked before the first database write.
    for evidence_id, relationship, lot, listing, context in bundles:
        store.add_evidence(evidence_id, relationship, lot=lot, listing=listing, candidate_context=context)
    return {"schema_version": 1, "auction": catalog["auction"], "source": catalog["source"],
            "pagination": catalog["pagination"], "lots": queue}
