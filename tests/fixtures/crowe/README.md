# Offline Crowe parser fixtures

These four small structural examples are based on the public embedded Apollo
responses inspected on 2026-10-29. They are reconstructed, sanitized examples,
not complete captured HTML responses or proof of full catalog coverage.

Observed sources:
- Historical catalog: https://bids.crauctions.com/auctions/48980-amazon-semi-load-auction-8166
- Historical detail: https://bids.crauctions.com/auctions/48980/lot/8078618-blue-and-white-flower-canvas-wall-art-12x16
- Active catalog: https://bids.crauctions.com/auctions/49187-amazon-semi-load-auction-8533
- Active detail: https://bids.crauctions.com/auctions/49187/lot/8127508-box-of-white-premium-2-ply-paper-towels-70-sheets

Retained observations: internal IDs, displayed lot numbers, sample titles, raw
status codes, timestamps, bid components, query filter shapes, reported totals
(878 historical / 827 active), reference relationships, and gallery order/counts
(five historical / two active attachments).

Sanitization and synthesis:
- Only one selected lot remains in each catalog fixture; the source page had 50.
  Totals are retained to test metadata association, not fixture completeness.
- Descriptions are replaced with short structural text. Dynamic-field definitions
  and image variants are reduced to representative fields.
- Public URLs omit title slugs. Image storage paths and external URLs are synthetic
  example.invalid values; they are not evidence of accessible image files.
- The rendered zero-count marker is retained on catalog fixtures as an adversarial
  distraction. Detail fixtures include the same synthetic marker for simplicity.
- Bidder identities, account/session fields, credentials, company settings,
  unrelated cache entries, and long retailer descriptions are absent.
- Extra conditions (mixed caches, dangling/cyclic refs, populated identifiers,
  captions, ambiguous queries, and malformed structures) are generated in tests.

## Parser API

`crowe_source_parser.py` uses only the Python standard library and performs no I/O.

```python
from crowe_source_parser import parse_catalog, parse_lot_detail

query = {
    "filter": {
        "auction_id": "48980",
        "is_visible": True,
        "limit_visibility_by_pick_up_locs": True,
        "auction_lot_status": [200, 300],
    },
    "order": [{"column": "lot_number", "direction": "asc"}],
    "pagination": {"page": 1, "pageSize": 50},
    "search": {"text": ""},
}
result = parse_catalog(html_text, source_url=request_url,
                       auction_id="48980", query_arguments=query)
detail = parse_lot_detail(detail_html, source_url=detail_request_url,
                          lot_id="8078618")
```

The caller supplies the actual requested context, not an arbitrary first cached
query. `query_arguments` must match the full encoded `lots(...)` argument object;
object key order is irrelevant, but values, types, and array order are significant.
Detail selection uses the observed ROOT_QUERY `lot({"auction_lot_id": ...})` shape.

Outputs preserve the caller's request URL, exact matching cache query key and
arguments, selected entity keys and source-provided public URLs. `raw_fields`
retains supported original field names and absent-versus-null distinctions.
`identifiers` provides null for missing/null known identifiers without extracting
values from prose. `prices` and `timestamps` retain source names and values.
No financial rates, auction status meanings, image types or conditions are inferred.

`images` is null when no full gallery is supplied (as on catalog pages), an empty
array for an explicitly empty gallery, or the resolved ordered attachment array.
All supplied attachment fields, captions, metadata and variants are retained.
`primary_image` is separate; it never substitutes for a full gallery.

## Limits

Only the observed standalone `window.__APOLLO_STATE__ = { ... };` form is accepted.
The parser does not execute JavaScript or support arbitrary script wrappers.
Missing/ambiguous queries, inconsistent identities, dangling/cyclic selected
references, invalid mandatory structures and contradictory local counts raise
SourceParseError. Unrelated cached entities are not traversed.

Reported totals remain query-specific. Local validation cannot prove page or
auction completeness, time stability, image availability, financial semantics,
or that a completed bid became a settled sale. Status codes and timestamp strings
are not converted. Unknown future lot/auction fields are not automatically copied;
the supported field projection must be extended deliberately. Dynamic fields and
image metadata remain intact. Safe HTML rendering is a future UI responsibility.

No changes to V4, the HTML scraper, financial logic, eBay logic, datasets or UI are
included. No network integration, pagination traversal, image downloads or file
publication are provided.

## Validation

From the repository root:

```sh
python3 -m unittest discover -s tests -p test_crowe_source_parser.py -v
/workspace/pythonprojects-venv/bin/python -m unittest discover -s tests -v
```

The first command requires no third-party dependencies. The second also runs the
12 existing ingestion-guard regressions with their installed dependencies.
