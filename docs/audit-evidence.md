# Internal audit evidence integration

`core.audit_evidence` supplies structured evidence for the future internal review
interface. It does not run V4, calculate values, infer verification, create human
judgments, modify the existing interfaces, or import legacy audit records.

## Bounded API

1. `acquire_crowe_for_review(...)` delegates to the existing
   `crowe_acquisition.acquire_catalog_page`. Supply the explicit catalog URL,
   internal auction ID and complete Apollo arguments, plus optionally one detail
   URL/internal lot ID. The wrapper adds separate UTC timestamps recording when
   each HTTP response's headers arrived. It performs exactly the adapter's one or
   two requests, never follows pagination and propagates acquisition/parser errors.
2. `fetch_ebay_candidates(...)` makes one explicit Browse API search for one
   identified Crowe lot. Supply the exact query, optional filter/sort strings and
   marketplace header. `limit` defaults to 20 and is configurable from 1 to 50.
   These are acquisition bounds, not evidence of search or auction completeness.
3. `build_review_page(crowe, searches=[...], store=store)` validates the selected
   page and all search identities before writing candidate evidence bundles. It
   returns all selected lots, including lots without candidates. It does not
   initiate any searches itself. At most one search result per lot is accepted in
   each call; the page is limited to 200 lots. Additional search history, discovery
   and automatic pagination are outside this increment.

Existing acquisition results can also be supplied directly by adding
`retrieved_at={"catalog": <actual timestamp>, "detail": <actual timestamp or None>}`.
Do not stamp old evidence with the current time. Missing or timezone-free source
retrieval timestamps fail validation.

## Evidence contract

The returned page contains `schema_version`, `auction`, `source`, `pagination`
and `lots`. Each lot entry has:

- `lot`: source identity and displayed lot number, with separate `catalog` and
  optional `detail` snapshots. Each snapshot retains the full normalized lot,
  auction/source metadata and retrieval timestamp. Catalog pagination is retained.
- `outcome`: `READY`, `EMPTY`, `ERROR` or `NOT_REQUESTED`.
- `search`: exact request context, timestamps, HTTP status, response metadata and
  explicit error code; null when not requested.
- `candidates`: original API listing evidence, five-part relationship, rank and
  immutable evidence ID. No ACCEPT/REJECT/UNSURE state is assigned.

Crowe descriptions, source URLs, attachment order, image variants, captions,
attributes, raw status codes and separate raw price components remain as returned
by the parser. Catalog and detail values are not reconciled; the next UI may prefer
available detail evidence but must keep its provenance. Missing gallery data does
not become a fabricated photograph or condition claim. The integration validates
the auction ID, internal lot ID, displayed number, raw ID fields, record keys,
request route and encoded query context before storage.

The eBay item projection retains original field names and values:
`itemId`, `itemWebUrl`, `title`, `image`, `thumbnailImages`, `additionalImages`,
`condition`, `conditionId`, `price`, `shippingOptions`, `buyingOptions`.
`itemId` is required, opaque and never parsed from a URL, title or rank. Missing
optional fields stay absent and nulls stay null. Price amounts remain source
strings/numbers, currency is not guessed and shipping is never added to price.
These are listing observations, not verified sales or valuations. Seller details
and unrelated item fields are excluded.

The exact query/filter/sort strings, requested limit, marketplace header and
prepared request URL are retained. Metadata preserves available `total`, `limit`,
`offset`, and API error/warning identifiers (`errorId`, `domain`, `category`).
Diagnostic messages and parameters are omitted to avoid persisting potentially
sensitive transport information. Authorization headers and tokens are never part
of the returned records or stored evidence.

## Storage and identity

Relationships are always:

```text
("crowe", internal auction ID, internal lot ID, "ebay", original itemId)
```

`FeedbackStore.add_evidence` receives the Crowe snapshot in `lot`, the eBay snapshot
in `listing`, and the search context/rank in `candidate_context`. Evidence IDs are
SHA-256 hashes of these versioned contents and the relationship. They identify
evidence versions, not listings. Repeating identical inputs is idempotent;
retrieval refreshes or rank changes create new evidence while the source
relationship remains unchanged. Existing decisions stay attached to the evidence
originally reviewed. The future UI must distinguish a prior relationship judgment
from a judgment on newly refreshed evidence.

All validation precedes database writes. Storage errors propagate without a
success result. Each bundle uses the existing store transaction; a page is not one
transaction. If a later write fails, earlier immutable bundles may remain, and
retrying the same inputs safely reuses them. No FeedbackStore schema/API changes
or legacy migrations are included.

EMPTY, ERROR and NOT_REQUESTED lots remain in the **returned queue**, with their
Crowe evidence. They do not create database evidence rows: there is no legitimate
listing identity to associate with them. Queue/search-outcome persistence across
application restarts is not implemented; the next integration must explicitly
retain or reconstruct that queue without inventing a listing ID.

## Example orchestration

This demonstrates the API; it would make real requests and is not an offline demo.
Use approved network access and credentials, and choose an explicit persistent
database location whose parent directory already exists.

```python
from core.audit_evidence import (
    acquire_crowe_for_review, fetch_ebay_candidates, build_review_page,
)
from core.feedback_store import FeedbackStore

# supplied_catalog_url, supplied_auction_id and supplied_query_arguments identify
# exactly one selected catalog request. No automatic source/query discovery.
crowe = acquire_crowe_for_review(
    supplied_catalog_url,
    auction_id=supplied_auction_id,
    query_arguments=supplied_query_arguments,
    detail_url=selected_detail_url,
    lot_id=selected_internal_lot_id,
)
search = fetch_ebay_candidates(
    auction_id=supplied_auction_id,
    lot_id=selected_internal_lot_id,
    query=reviewer_supplied_query,
    filters="buyingOptions:{FIXED_PRICE}", sort="price", limit=20,
    marketplace_id="EBAY_US",
)
with FeedbackStore(database_path) as store:
    store.initialize()
    review_page = build_review_page(crowe, searches=[search], store=store)
```

An abbreviated synthetic candidate record looks like:

```json
{
  "evidence_id": "audit-v1-<content digest>",
  "relationship": {
    "auction_source": "crowe", "auction_id": "48980", "lot_id": "8078618",
    "marketplace_source": "ebay", "listing_id": "v1|synthetic-listing-A|0"
  },
  "listing": {
    "marketplace_source": "ebay", "api": "browse",
    "retrieved_at": "<timezone-aware receipt timestamp>",
    "item": {
      "itemId": "v1|synthetic-listing-A|0",
      "title": "Synthetic product candidate",
      "price": {"value": "10.00", "currency": "CAD"},
      "shippingOptions": [{
        "shippingCostType": "FIXED",
        "shippingCost": {"value": "3.25", "currency": "CAD"}
      }]
    }
  },
  "rank": 1
}
```

## Failure behavior and limits

The new eBay path reuses `ebay_api_client.get_oauth_token` only; V4's pricing
functions and return contracts are unchanged. The existing helper returns no token
on absent credentials/authentication failure, represented here as
`AUTH_UNAVAILABLE`. Injectable `token_provider` and requests-compatible `http_get`
allow offline tests. Unexpected dependency/programming errors propagate.

Browse acquisition uses the fixed HTTPS production search endpoint, TLS checking,
no redirects, no retries, a 5-second connect/20-second read-inactivity timeout and
a 4 MiB decoded-body limit. Non-200, malformed/non-JSON, failed transport and
oversized results produce ERROR. A missing/blank/duplicate item ID invalidates the
entire search, including otherwise valid items. An absent item array is treated
as empty only when the API explicitly reports `total: 0`. No synthetic candidates,
fallback prices or cached substitutions are used. No image URLs are fetched.

No live Crowe/eBay acquisition or image rendering was performed for this increment.
eBay response fixtures are synthetic examples of Browse fields, not authenticated
live captures. Source IDs supplied through custom transports cannot be independently
authenticated here. Timeouts are not total wall-clock deadlines. Totals are
source-reported and query-specific. The existing parser's field projection and
adapter limitations still apply. API access, image-host access, persistent storage,
credential provisioning and responsive rendering remain separate operational work.

## Offline validation

```sh
/workspace/pythonprojects-venv/bin/python -B -m unittest discover -s tests -p test_audit_evidence.py -v
/workspace/pythonprojects-venv/bin/python -B -m unittest discover -s tests -v
```

Tests reuse the existing sanitized Crowe fixtures and construct small synthetic
Browse responses in memory. All HTTP and token retrieval is mocked, socket
connections are blocked, and SQLite databases/legacy samples use temporary files.
They exercise stable identities, full evidence preservation, search failures and
empty queues, mixed outcomes, pre-write validation, idempotent storage, unchanged
history, HTTP bounds, and continued separation from financial calculations.
