# Identity-safe human feedback foundation

`core.feedback_store` is an isolated, standard-library SQLite storage API for
internal match review. It imports no UI, acquisition, matching, risk or financial
modules. It does not fetch evidence, read legacy files, migrate reviews, designate
lots VERIFIED, or calculate values. ACCEPT means only that the named reviewer
considers a listing a suitable comparable match.

## Identity and schema

Schema version 1 uses two application tables plus SQLite's internal sequence:

| Table | Stored fields |
| --- | --- |
| `evidence` | `evidence_id`; `auction_source`, `auction_id`, `lot_id`, `marketplace_source`, `listing_id`; `lot_json`, `listing_json`, `context_json`; `recorded_at` |
| `decision_events` | Monotonic `sequence`; unique `event_id`; `reviewer_id`; the same five relationship identity fields; `evidence_id`; `decision`, `reasons_json`, `notes`; `supersedes_event_id`; `recorded_at` |

The five identity fields are exact strings. `lot_id` must be Crowe's internal ID,
not its displayed lot number. `listing_id` must be the original opaque marketplace
ID. No identity is extracted from rank, title, display number or URL. Callers must
use consistent source namespaces and authentic upstream IDs; this offline module
cannot authenticate their origin. Reviewer IDs are stable internal attribution,
not an authentication system.

Evidence stores three JSON objects supplied by the caller. They can hold selected
snapshots or immutable, versioned references. Preserve available descriptions,
ordered image metadata, source IDs/URLs, original price components and currency,
retrieval timestamps, exact queries/filters, search or matcher versions and ranks
inside the appropriate object. Empty objects, missing fields and explicit nulls
remain distinct; no source timestamp, currency or identifier is filled in.
`recorded_at` is the storage event's UTC time, not a retrieval time.

The three JSON payloads are deliberately extensible, not a second Crowe/eBay
schema. Their internal fields are not interpreted or cross-validated against the
declared relationship. The future integration must validate that binding before
calling this API. A versionless URL alone is not reproducible evidence: callers
using references must ensure the referenced version is immutable and retained.
No image bytes or full HTML captures are required.

Composite foreign keys bind each decision to its evidence's exact relationship.
Another composite foreign key constrains a correction to the same reviewer and
relationship as the superseded event. Unique partial indexes permit only one
initial event per reviewer/relationship and one successor per event. UPDATE and
DELETE triggers protect both application tables. Database checks and a trigger
validate decision values, JSON shapes, rejection reason presence and reason codes.
The exact DDL is `_SCHEMA` in `core/feedback_store.py`.

## API and example

This example uses **synthetic** source and reviewer identifiers. Choose an explicit
database path on persistent storage outside the repository for operational use.
The parent directory must already exist. The API never chooses a default path.

```python
from core.feedback_store import FeedbackStore, Relationship

relationship = Relationship(
    auction_source="crowe", auction_id="synthetic-auction-A",
    lot_id="synthetic-internal-lot-A", marketplace_source="ebay",
    listing_id="v1|synthetic-listing-A|0",
)

with FeedbackStore("/tmp/review-example.sqlite3") as store:
    store.initialize()  # Idempotent for this schema; refuses unrelated databases.
    store.add_evidence(
        "evidence-A-v1", relationship,
        lot={"lot_number": "42", "description": "Synthetic product.", "model": None},
        listing={"price": {"value": "10.00", "currency": "USD"}, "version": "v1"},
        candidate_context={"query": "synthetic product", "rank": 1},
    )
    first = store.record_decision(
        event_id="event-A", reviewer_id="reviewer-owner",
        evidence_id="evidence-A-v1", decision="ACCEPT",
        expected_current_event_id=None,
    )
    corrected = store.record_decision(
        event_id="event-B", reviewer_id="reviewer-owner",
        evidence_id="evidence-A-v1", decision="REJECT",
        reasons=["MODEL_VARIANT_MISMATCH"], notes="Different variant observed.",
        expected_current_event_id=first["event_id"],
    )
    latest = store.latest_decision(relationship, "reviewer-owner")
    assert latest == corrected
    assert [event["decision"] for event in store.history(relationship, "reviewer-owner")] == ["ACCEPT", "REJECT"]
```

The returned event has this shape (storage timestamp abbreviated):

```json
{
  "event_id": "event-B",
  "reviewer_id": "reviewer-owner",
  "evidence_id": "evidence-A-v1",
  "decision": "REJECT",
  "reasons": ["MODEL_VARIANT_MISMATCH"],
  "notes": "Different variant observed.",
  "supersedes_event_id": "event-A",
  "recorded_at": "<UTC storage timestamp>",
  "relationship": {
    "auction_source": "crowe",
    "auction_id": "synthetic-auction-A",
    "lot_id": "synthetic-internal-lot-A",
    "marketplace_source": "ebay",
    "listing_id": "v1|synthetic-listing-A|0"
  }
}
```

REJECT requires one or more of `CONDITION_DIFFERENCE`, `MODEL_VARIANT_MISMATCH`,
`WRONG_CATEGORY`, `QUANTITY_BUNDLE_MISMATCH`, `ACCESSORY_MISMATCH`, `OTHER`.
Optional reasons and notes are also supported for ACCEPT and UNSURE. Reasons are
stored as a sorted unique set; notes and source payload values are not rewritten.

`get_evidence(evidence_id)` returns the immutable evidence bundle. New evidence
requires a new evidence ID. Refreshing a source does not move an old judgment to
the new evidence; a reviewer must append a new event referencing that evidence.
`latest_decision(relationship, reviewer_id)` returns an event or `None`.
`history(...)` returns all events in insertion order, not timestamp order.
Judgments from different reviewers remain separate; no consensus is invented.

## Transactions, retries and failures

Writes use `BEGIN IMMEDIATE`, foreign keys and synchronous commits. The expected
event is checked while holding the SQLite writer lock. Two corrections based on
the same current event cannot both succeed. Each worker/thread needs its own
`FeedbackStore`; a single connection must not be shared between threads.

- `ValidationError`: invalid arguments or unknown evidence ID.
- `ConflictError`: an evidence/event ID reused with different contents.
- `StaleDecisionError` (a `ConflictError`): expected event is not current for the
  selected reviewer and relationship. Reload state for an explicit correction.
- `StorageError`: database/schema/lock/transaction failure. The original SQLite
  exception is retained as the cause when applicable. There is no success fallback.

Callers must retain the same event ID and submission payload when retrying an
uncertain save. Exact repeats return the original event without appending, even
if it has since been superseded. Different contents under that ID fail. Reordered
or duplicated reason codes count as the same reason set. New intentions require
new event IDs. Never automatically retry a stale edit against a newer revision.

Schema initialization is transactional and versioned; no migrations or automatic
legacy imports occur. Evidence and decisions are separately committed operations;
a failed decision may leave an unreferenced evidence bundle. No feedback success
is returned if its transaction fails. An I/O failure around commit can leave the
caller uncertain; stable submission IDs permit safe reconciliation/retry.

## Validation and limitations

```sh
/workspace/pythonprojects-venv/bin/python -B -m unittest discover -s tests -p test_feedback_store.py -v
/workspace/pythonprojects-venv/bin/python -B -m unittest discover -s tests -v
```

Synthetic tests cover every identity component, equal displayed lot numbers,
shared listings, reordered candidates, immutable evidence refreshes, corrections,
reopening storage, separate reviewers, competing connections, stale edits,
idempotency, validation, direct SQL constraints, rollback, locks, schema errors
and unchanged legacy files. Socket connections are blocked in feedback tests.
There are no live credentials, source captures or new dependencies.

SQLite must support JSON functions (available in this environment). Persistent
storage placement, filesystem locking, backups, retention, file permissions and
restoration remain deployment responsibilities. Local disk alone is not a
persistence guarantee; network filesystem behavior is not tested. No encryption,
authentication, external reference verification, review adjudication or schema
migration is implemented. File owners can bypass triggers by altering the schema;
this is consistency protection, not a tamper-proof ledger.

Legacy CSV/JSONL records remain untouched and unclassified. Nothing in this
increment changes the existing applications' verification or valuation behavior:
the new foundation is intentionally not connected to them.
