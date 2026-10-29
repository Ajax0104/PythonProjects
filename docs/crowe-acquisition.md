# Bounded Crowe acquisition adapter

`crowe_acquisition.acquire_catalog_page` performs one explicitly selected catalog
GET and, optionally, one selected detail GET. It invokes the unchanged offline
Apollo parser and returns `{"catalog": ..., "detail": ...}`. `detail` is null
when not requested. It never discovers pages, traverses pagination, retrieves
images, writes files, calculates prices, or calls V4/eBay/UI code.

## Usage

```python
from crowe_acquisition import acquire_catalog_page

result = acquire_catalog_page(
    "https://bids.crauctions.com/auctions/48980-amazon-semi-load-auction-8166?page=1&items=50",
    auction_id="48980",
    query_arguments={
        "filter": {
            "auction_id": "48980",
            "auction_lot_status": [200, 300],
            "is_visible": True,
            "limit_visibility_by_pick_up_locs": True,
        },
        "order": [{"column": "lot_number", "direction": "asc"}],
        "pagination": {"page": 1, "pageSize": 50},
        "search": {"text": ""},
    },
    detail_url="https://bids.crauctions.com/auctions/48980/lot/8078618-blue-and-white-flower-canvas-wall-art-12x16",
    lot_id="8078618",
)
```

This example would make real network requests; validation uses injected mocked
responses instead. Omit both detail arguments for catalog-only acquisition.
Both must be supplied together. The detail lot must be among the selected page's
normalized records, and the detail result must agree on auction and internal lot
identity. Different values between snapshots are not merged or reconciled.

The adapter passes the caller's full Apollo query arguments unchanged. It does
not derive or repair missing filters, rewrite the catalog URL to match them, or
select the first cached query. A mismatch fails in the parser. Each normalized
result retains the original caller-supplied request URL in `source.url`; source
record URLs are left untouched. Stable IDs link the two separate results.

## Network boundaries and errors

- HTTPS only, exact hostname `bids.crauctions.com`, default port or explicit 443.
- URL userinfo, fragments, control characters and backslashes are rejected.
- Only the observed `/auctions/<auction-id>[-slug]` and
  `/auctions/<auction-id>/lot/<lot-id>[-slug]` routes are permitted, with IDs
  matching the selection. Asset/image routes and other hosts are rejected.
- Redirect following is disabled. All redirects, including same-host redirects,
  and unexpectedly redirected transport results fail explicitly.
- Connection timeout: 5 seconds. Read-inactivity timeout: 20 seconds. These are
  not a total wall-clock deadline.
- HTTP 200 and `text/html` or `application/xhtml+xml` are required.
- A 4 MiB limit applies both to declared Content-Length and streamed decoded
  bytes. A false/missing Content-Length cannot bypass the streamed limit.
- HTML uses the declared charset, or UTF-8 if absent; decoding is strict.
- Responses close on success and failure. There are no adapter retries or caches.
- Default transport uses the existing requests dependency, inherited proxy/CA
  settings and explicit TLS verification. No dependency/configuration changes
  are included.

`AcquisitionError` reports request validation, transport, HTTP, content/encoding,
size, and cross-result identity failures. Requests exceptions remain available
through `__cause__`; no response body or headers are included in adapter messages.
`SourceParseError` propagates unchanged. A detail error raises rather than
returning the previously parsed catalog as an apparently complete acquisition.

`http_get` can inject a requests.get-compatible callable. It must honor the
supplied `timeout`, `allow_redirects=False`, `stream=True` and `verify=True`
options. Custom transports must not add retries or side effects. Network
restrictions and timeouts assume a conforming transport.

## Validation and limits

```sh
/workspace/pythonprojects-venv/bin/python -m unittest discover -s tests -p test_crowe_acquisition.py -v
/workspace/pythonprojects-venv/bin/python -m unittest discover -s tests -v
```

Tests reuse the existing sanitized historical/active HTML fixtures. Socket access
is disabled in adapter tests; transport responses, errors and timeouts are mocked.
Coverage includes exact output preservation, query selection, cross-auction
conflicts, redirects, malformed HTML/state, decompressed-size limits, no partial
returns, no file writes and response cleanup.

No live Crowe request was used to validate this increment. Compatibility remains
limited by the existing parser's schema and source-field projection. Query totals
do not establish auction completeness, and a single response is only a snapshot.
No claim is made about final-sale settlement, image availability, currency
interpretation, or unchanged bid values between catalog and detail requests.
A response above the limit fails even if otherwise legitimate. Redirected URL
aliases fail rather than being followed. No adapter integration into V4 is included.
