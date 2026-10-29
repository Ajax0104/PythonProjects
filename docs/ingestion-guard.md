# V4 ingestion failure guard

V4 now propagates ingestion errors before opening the manifest, constructing a
Manifest, or requesting comparable prices. A scrape returns rows only after all
configured pages pass validation. The CSV is written to a temporary file beside
the destination, flushed and synced, then published with os.replace. Normal
write/replacement failures remove the staging file and preserve the old manifest.
The existing four-column CSV schema and successful-run pricing remain unchanged.

## What is checked

- Every configured page request must succeed within the existing retry budget
  and return HTTP 200.
- An explicitly non-HTML content type is rejected. Missing Content-Type is
  tolerated, but the response must still contain parseable lot cards.
- Each requested page must contain at least one parseable lot with a title.
- Every lot number visible within the existing selected card elements must be
  represented by a parseable card on that page. Otherwise the run is rejected.
- Each page must contribute a previously unseen lot. Featured duplicates remain
  allowed alongside new lots; a wholly repeated page is rejected as unverifiable.
- Empty data cannot be exported.

These are consistency checks, not an arbitrary minimum auction size. A short
last page containing one new valid lot is accepted.

## Limits and edge cases

The auction URL, 18-page default, selectors, bid/title parsing, and V4's first-50
processing limit are unchanged. Passing these checks does not prove that 18 pages
cover the auction, that pagination stayed consistent during bidding, or that all
lots were exposed in the HTML. Lots omitted by the server, outside the selected
HTML elements, or lacking a recognizable lot number cannot be counted reliably.
The existing broad selectors and first-price regex do not establish semantic
correctness of a bid, title, condition, or auction identity. HTML parser recovery
can also accept malformed markup if it still yields parseable cards.

An empty requested page (including an overspecified last page), a wholly repeated
page, or a recognized lot with an unsupported bid format now stops the run. This
is intentional conservative behavior: the scraper cannot distinguish a legitimate
empty/end page from missing data. Text referring to another lot inside a card can
also trigger the visible-ID consistency check. Live Crowe compatibility has not
been verified; network access and JSON investigation remain separate work.

Atomic replacement protects manifest contents against partial CSV writes; it is
not a transaction across all V4 outputs. After successful ingestion, downstream
pricing/export failures and the existing successful-run overwrite behavior are
unchanged. Concurrent runs are not serialized. Abrupt process termination can
leave a staging file, and directory metadata is not synced for power-loss
recovery. Existing audit decisions and historical records are never written by
this ingestion path.

## Offline validation

From the repository root, using the prepared Python environment:

```sh
/workspace/pythonprojects-venv/bin/python -m unittest discover -s tests -v
```

Tests mock HTTP requests and retry delays and work exclusively in temporary
directories. Failure cases check byte-for-byte preservation of existing files;
pipeline failures check that no comparable-pricing or valuation objects are
invoked. Successful cases check the CSV contracts and the unchanged $45.19 V4
maximum bid for a $100 resale value under its defaults.
