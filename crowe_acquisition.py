"""Bounded public Crowe acquisition: one catalog, optionally one selected lot.

No discovery, retries, pagination traversal, image retrieval, or persistence.
The existing offline parser remains responsible for interpreting Apollo state.
"""

from email.message import Message
import re
from urllib.parse import urlsplit

import requests

from crowe_source_parser import parse_catalog, parse_lot_detail


TIMEOUT = (5, 20)  # Connection and read-inactivity seconds, respectively.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024  # Also enforced on decompressed content.
_HOST = "bids.crauctions.com"


class AcquisitionError(RuntimeError):
    """Invalid request, failed transport, invalid response, or identity conflict."""


def _validate_url(url, auction_id, lot_id=None):
    if not isinstance(url, str) or not url or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise AcquisitionError("URL must be nonempty text without whitespace or controls")
    if "\\" in url:
        raise AcquisitionError("Backslashes are not permitted in URLs")
    try:
        parts = urlsplit(url)
        allowed = (
            parts.scheme == "https" and parts.hostname == _HOST
            and parts.username is None and parts.password is None
            and parts.port in (None, 443) and not parts.fragment
        )
    except ValueError as error:
        raise AcquisitionError("Malformed URL") from error
    if not allowed:
        raise AcquisitionError("Only credential-free HTTPS Crowe URLs on port 443 are permitted")
    if lot_id is None:
        match = re.fullmatch(r"/auctions/(\d+)(?:-[^/]+)?/?", parts.path)
        matches_identity = match and match[1] == auction_id
    else:
        match = re.fullmatch(r"/auctions/(\d+)/lot/(\d+)(?:-[^/]+)?/?", parts.path)
        matches_identity = match and match[1] == auction_id and match[2] == lot_id
    if not matches_identity:
        raise AcquisitionError("URL must identify the explicitly selected auction/lot page")


def _fetch_html(url, http_get):
    response = None
    try:
        response = http_get(
            url, timeout=TIMEOUT, allow_redirects=False, stream=True, verify=True,
        )
        # Requests may normalize escaping/case, but must not change destinations.
        expected_url = requests.Request("GET", url).prepare().url
        if response.history or response.url != expected_url:
            raise AcquisitionError("Unexpected redirected response")
        if response.status_code != 200:
            raise AcquisitionError(f"Expected HTTP 200; received {response.status_code}")
        content_type = Message()
        content_type["content-type"] = response.headers.get("Content-Type", "")
        if content_type.get_content_type() not in ("text/html", "application/xhtml+xml"):
            raise AcquisitionError("Expected an HTML Content-Type")
        length = response.headers.get("Content-Length")
        if length is not None:
            if not re.fullmatch(r"[0-9]+", length.strip()):
                raise AcquisitionError("Invalid Content-Length")
            # Compare digit strings to avoid converting an unbounded header.
            digits = length.strip().lstrip("0") or "0"
            limit = str(MAX_RESPONSE_BYTES)
            if len(digits) > len(limit) or (len(digits) == len(limit) and digits > limit):
                raise AcquisitionError("Declared response exceeds size limit")
        body = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                raise AcquisitionError("Decoded response exceeds size limit")
            body.extend(chunk)
        charset = content_type.get_content_charset() or "utf-8"
        try:
            return body.decode(charset, errors="strict")
        except (LookupError, UnicodeError) as error:
            raise AcquisitionError("Invalid HTML character encoding") from error
    except requests.RequestException as error:
        # Do not include response bodies, headers, or sensitive transport text.
        raise AcquisitionError(f"Crowe request failed ({type(error).__name__})") from error
    finally:
        if response is not None:
            response.close()


def acquire_catalog_page(
    catalog_url, *, auction_id, query_arguments, detail_url=None, lot_id=None,
    http_get=None,
):
    """Return ``{'catalog': parsed_catalog, 'detail': parsed_detail_or_None}``.

    The exact caller-supplied query arguments go to parse_catalog unchanged.
    A detail selection must identify a lot present in this selected catalog
    page. Its returned auction/lot identities must agree. Both results retain
    their own request URL and raw values; they are not merged or reconciled.

    AcquisitionError covers request/response and cross-result conflicts.
    SourceParseError propagates unchanged. On any failure no result is returned.
    ``http_get`` is an optional requests.get-compatible callable for offline
    testing; it must honor the supplied redirect, streaming, timeout and TLS
    options. The default requests.get uses the inherited proxy/CA configuration.
    """
    if not isinstance(auction_id, str) or not re.fullmatch(r"[0-9]+", auction_id):
        raise AcquisitionError("auction_id must be a numeric string")
    if not isinstance(query_arguments, dict):
        raise AcquisitionError("query_arguments must be the complete Apollo arguments object")
    filters = query_arguments.get("filter")
    if not isinstance(filters, dict) or filters.get("auction_id") != auction_id:
        raise AcquisitionError("Query context must identify the selected auction")
    if (detail_url is None) != (lot_id is None):
        raise AcquisitionError("detail_url and lot_id must be supplied together")
    _validate_url(catalog_url, auction_id)
    if detail_url is not None:
        if not isinstance(lot_id, str) or not re.fullmatch(r"[0-9]+", lot_id):
            raise AcquisitionError("lot_id must be a numeric string")
        _validate_url(detail_url, auction_id, lot_id)
    get = requests.get if http_get is None else http_get
    catalog = parse_catalog(
        _fetch_html(catalog_url, get), source_url=catalog_url,
        auction_id=auction_id, query_arguments=query_arguments,
    )
    detail = None
    if detail_url is not None:
        if not any(lot["lot_id"] == lot_id for lot in catalog["lots"]):
            raise AcquisitionError("Selected detail lot is not on the selected catalog page")
        detail = parse_lot_detail(
            _fetch_html(detail_url, get), source_url=detail_url, lot_id=lot_id,
        )
        selected = detail["lots"][0]
        if (detail["auction"]["auction_id"] != auction_id
                or selected["auction_id"] != auction_id or selected["lot_id"] != lot_id):
            raise AcquisitionError("Catalog and detail identities conflict")
    return {"catalog": catalog, "detail": detail}
