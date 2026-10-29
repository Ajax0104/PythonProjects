"""Offline extraction of Crowe's observed Apollo HTML state.

Callers must select the catalog's exact ``lots(...)`` arguments, or the detail
page's internal lot ID. No requests, JavaScript execution, price calculations,
status interpretation, or description-derived identifier guesses occur here.
"""

import json
import re
from html.parser import HTMLParser


class SourceParseError(ValueError):
    """Missing, malformed, ambiguous, or inconsistent source data."""


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append("".join(self.current))
            self.current = None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SourceParseError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise SourceParseError(f"Non-JSON numeric constant: {value}")


_DECODER = json.JSONDecoder(object_pairs_hook=_unique_object, parse_constant=_constant)
_ASSIGNMENT = re.compile(r"\A\s*window\.__APOLLO_STATE__\s*=\s*")


def extract_apollo_state(html):
    """Decode a standalone state assignment; never evaluate script contents.

    Only the observed assignment form, with optional trailing semicolon, is
    accepted. Other JavaScript expressions or multiple assignments are errors.
    """
    if not isinstance(html, str):
        raise SourceParseError("HTML must be text")
    parser = _Scripts()
    parser.feed(html)
    candidates = [text for text in parser.scripts if _ASSIGNMENT.match(text)]
    if len(candidates) != 1:
        raise SourceParseError("Expected exactly one Apollo state assignment")
    text = _ASSIGNMENT.sub("", candidates[0], count=1)
    try:
        state, end = _DECODER.raw_decode(text)
    except (ValueError, RecursionError) as error:
        raise SourceParseError("Invalid Apollo JSON") from error
    if text[end:].strip() not in ("", ";"):
        raise SourceParseError("Unexpected script after Apollo JSON")
    if not isinstance(state, dict) or not isinstance(state.get("ROOT_QUERY"), dict):
        raise SourceParseError("Apollo state requires an object ROOT_QUERY")
    return state


def _object(value, label):
    if not isinstance(value, dict):
        raise SourceParseError(f"{label} must be an object")
    return value


def _id(value, label):
    if not isinstance(value, str) or not value.strip():
        raise SourceParseError(f"{label} must be a nonempty string")
    return value


def _resolve(value, state, trail=()):
    if isinstance(value, dict):
        if "__ref" in value:
            ref = _id(value["__ref"], "__ref")
            if set(value) != {"__ref"}:
                raise SourceParseError(f"Ambiguous reference: {ref}")
            if ref in trail:
                raise SourceParseError(f"Cyclic reference: {ref}")
            if ref not in state:
                raise SourceParseError(f"Dangling reference: {ref}")
            return _resolve(state[ref], state, (*trail, ref))
        return {key: _resolve(item, state, trail) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, state, trail) for item in value]
    return value


def _record(ref, state, prefix):
    """Load a selected entity without traversing unrelated entity fields."""
    _object(ref, "Entity reference")
    key = _id(ref.get("__ref"), "Entity reference")
    if set(ref) != {"__ref"} or not key.startswith(prefix + "."):
        raise SourceParseError(f"Expected {prefix} reference")
    if key not in state:
        raise SourceParseError(f"Dangling reference: {key}")
    return key, _object(state[key], key)


def _query(container, name, arguments):
    matches = []
    for key, value in container.items():
        if not key.startswith(name + "("):
            continue
        if not key.endswith(")"):
            raise SourceParseError(f"Malformed {name} query key")
        try:
            args = _DECODER.decode(key[len(name) + 1:-1])
        except ValueError as error:
            raise SourceParseError(f"Malformed {name} query arguments") from error
        # Python considers True == 1; query context must preserve JSON types.
        if json.dumps(args, sort_keys=True) == json.dumps(arguments, sort_keys=True):
            matches.append((key, value))
    if len(matches) != 1:
        raise SourceParseError(f"Expected one matching {name} query; found {len(matches)}")
    return matches[0]


_TIMES = ("start_time", "end_time", "original_end_time", "prebid_start_time", "prebid_end_time")
_IDENTIFIERS = ("upc", "gtin", "ean", "asin", "brand", "model", "mpn")
_PRICES = ("winning_bid_amount", "current_bid", "hammer_price", "price", "starting_bid",
           "required_bid", "bid_increment_amount", "buy_it_now_price", "premium",
           "online_premium", "bid_with_premium", "currency")
_AUCTION_FIELDS = ("auction_id", "auction_ref", "title", "auction_status", "public_url", *_TIMES)
_LOT_FIELDS = ("auction_id", "auction_lot_id", "lot_number", "lot_ref", "title",
               "description", "description_plain", "public_url", "auction_lot_status",
               "auction_type", "bid_count", "is_no_sale", "pending_confirmation",
               "is_past_end_time", "quantity", "unit_quantity", "dynamic_fields",
               "image_count", *_TIMES, *_IDENTIFIERS, *_PRICES)


def _fields(record, names, state):
    # Preserve source spelling and distinguish absent fields from explicit nulls.
    return {name: _resolve(record[name], state) for name in names if name in record}


def _auction(record, state, expected_id):
    if _id(record.get("auction_id"), "auction_id") != expected_id:
        raise SourceParseError("Auction identity mismatch")
    return _fields(record, _AUCTION_FIELDS, state)


def _lot(record, state, key, auction_id):
    lot_id = _id(record.get("auction_lot_id"), "auction_lot_id")
    if key != "AuctionLot." + lot_id or record.get("auction_id") != auction_id:
        raise SourceParseError("Lot identity mismatch")
    _id(record.get("lot_number"), "lot_number")
    _id(record.get("title"), "title")
    for field in ("description", "description_plain", "public_url"):
        if record.get(field) is not None and not isinstance(record[field], str):
            raise SourceParseError(f"{field} must be text or null")
    raw = _fields(record, _LOT_FIELDS, state)
    if raw.get("dynamic_fields") is not None:
        if not isinstance(raw["dynamic_fields"], list):
            raise SourceParseError("dynamic_fields must be an array or null")
        for attribute in raw["dynamic_fields"]:
            _object(attribute, "Dynamic field")
    gallery = None
    if "images" in record:
        gallery = _resolve(record["images"], state)
        if not isinstance(gallery, list):
            raise SourceParseError("images must be an array when supplied")
        for image in gallery:
            _object(image, "Image")
            attachment_id = image.get("attachment_id")
            if (not isinstance(attachment_id, (str, int))
                    or isinstance(attachment_id, bool) or attachment_id == ""):
                raise SourceParseError("Image requires an attachment_id")
    primary = _resolve(record.get("primary_image"), state)
    if primary is not None:
        _object(primary, "primary_image")
    return {
        "auction_id": auction_id, "lot_id": lot_id, "lot_number": record["lot_number"],
        "title": record["title"], "description_html": record.get("description"),
        "description_plain": record.get("description_plain"),
        "source_url": record.get("public_url"), "source_record_key": key,
        "raw_fields": raw, "identifiers": {name: raw.get(name) for name in _IDENTIFIERS},
        "prices": {name: raw[name] for name in _PRICES if name in raw},
        "timestamps": {name: raw[name] for name in _TIMES if name in raw},
        "attributes": raw.get("dynamic_fields"),
        "images": gallery, "primary_image": primary,
        "image_provenance": "unknown",
    }


def parse_catalog(html, *, source_url, auction_id, query_arguments):
    """Normalize only lots referenced by the exact requested catalog query.

    ``query_arguments`` is the complete object encoded in ``lots({...})``,
    including filters, order, pagination, and search. Argument key order is
    irrelevant; filters and values must match. Totals describe this query only.
    """
    _id(source_url, "source_url")
    _id(auction_id, "auction_id")
    _object(query_arguments, "query_arguments")
    if _object(query_arguments.get("filter"), "filter").get("auction_id") != auction_id:
        raise SourceParseError("Query auction identity mismatch")
    pagination = _object(query_arguments.get("pagination"), "pagination")
    for field in ("page", "pageSize"):
        if type(pagination.get(field)) is not int or pagination[field] < 1:
            raise SourceParseError(f"pagination.{field} must be a positive integer")
    state = extract_apollo_state(html)
    auction_query, ref = _query(state["ROOT_QUERY"], "auction", {"auction_id": auction_id})
    auction_key, auction = _record(ref, state, "Auction")
    if auction_key != "Auction." + auction_id:
        raise SourceParseError("Auction reference identity mismatch")
    auction_data = _auction(auction, state, auction_id)
    query_key, result = _query(auction, "lots", query_arguments)
    result = _object(result, "Catalog result")
    refs, total = result.get("lots"), result.get("total")
    if not isinstance(refs, list) or type(total) is not int or total < 0:
        raise SourceParseError("Catalog result requires lots array and nonnegative integer total")
    if len(refs) > pagination["pageSize"] or len(refs) > total:
        raise SourceParseError("Catalog result count contradicts pagination or total")
    lots, seen = [], set()
    for ref in refs:
        key, record = _record(ref, state, "AuctionLot")
        if key in seen:
            raise SourceParseError(f"Duplicate lot reference: {key}")
        seen.add(key)
        lots.append(_lot(record, state, key, auction_id))
    return {
        "source": {"url": source_url, "format": "embedded_apollo", "kind": "catalog",
                   "auction_query_key": auction_query, "query_key": query_key,
                   "query_arguments": _DECODER.decode(query_key[5:-1])},
        "auction": auction_data,
        "pagination": {**pagination, "total": total, "returned_count": len(lots)},
        "lots": lots,
    }


def parse_lot_detail(html, *, source_url, lot_id):
    """Normalize the ROOT_QUERY lot selected by its internal ID."""
    _id(source_url, "source_url")
    _id(lot_id, "lot_id")
    state = extract_apollo_state(html)
    query_key, ref = _query(state["ROOT_QUERY"], "lot", {"auction_lot_id": lot_id})
    key, record = _record(ref, state, "AuctionLot")
    if key != "AuctionLot." + lot_id:
        raise SourceParseError("Requested lot identity mismatch")
    auction_id = _id(record.get("auction_id"), "auction_id")
    # Detail pages contain an auction object on the selected lot; resolving the
    # whole cache would incorrectly conflate it with partial auction records.
    auction = _object(record.get("auction"), "Detail auction")
    if "__ref" in auction:
        auction_key, auction = _record(auction, state, "Auction")
        if auction_key != "Auction." + auction_id:
            raise SourceParseError("Detail auction reference identity mismatch")
    return {
        "source": {"url": source_url, "format": "embedded_apollo", "kind": "detail",
                   "query_key": query_key, "query_arguments": {"auction_lot_id": lot_id}},
        "auction": _auction(auction, state, auction_id),
        "lots": [_lot(record, state, key, auction_id)],
    }
