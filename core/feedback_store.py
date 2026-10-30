"""Isolated human match feedback. No acquisition, verification or valuation logic.

Each connection belongs to one thread. Use a separate store per worker and a
persistent, explicitly chosen database path. No legacy data is imported.
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
import sqlite3


class FeedbackError(Exception):
    """Base class for explicit feedback failures."""


class ValidationError(FeedbackError):
    """Invalid identities, evidence or decision fields."""


class ConflictError(FeedbackError):
    """An immutable identifier was reused with different contents."""


class StaleDecisionError(ConflictError):
    """The expected current event is no longer current."""


class StorageError(FeedbackError):
    """SQLite access, schema or transaction failure; no success is implied."""


DECISIONS = frozenset({"ACCEPT", "REJECT", "UNSURE"})
REASONS = frozenset({
    "CONDITION_DIFFERENCE", "MODEL_VARIANT_MISMATCH", "WRONG_CATEGORY",
    "QUANTITY_BUNDLE_MISMATCH", "ACCESSORY_MISMATCH", "OTHER",
})
_IDENTITY_FIELDS = (
    "auction_source", "auction_id", "lot_id", "marketplace_source", "listing_id",
)
_APPLICATION_ID = 0x43524642
_SCHEMA_VERSION = 1


def _identity(value, name):
    if (not isinstance(value, str) or not value.strip() or value != value.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValidationError(f"{name} must be nonempty text without surrounding whitespace or controls")
    return value


@dataclass(frozen=True)
class Relationship:
    """Source IDs supplied by the caller, never inferred from display content.

    lot_id is Crowe's internal lot ID, not the displayed lot number. listing_id
    is the original opaque marketplace ID. This module cannot authenticate IDs.
    """

    auction_source: str
    auction_id: str
    lot_id: str
    marketplace_source: str
    listing_id: str

    def __post_init__(self):
        for name, value in asdict(self).items():
            _identity(value, name)


def _relationship_values(relationship):
    if not isinstance(relationship, Relationship):
        raise ValidationError("relationship must be a Relationship")
    return tuple(asdict(relationship).values())


def _snapshot(value):
    def validate(node):
        if type(node) is dict:
            if any(type(key) is not str for key in node):
                raise ValidationError("Evidence object keys must be strings")
            for child in node.values():
                validate(child)
        elif type(node) is list:
            for child in node:
                validate(child)
        elif node is not None and type(node) not in (str, int, float, bool):
            raise ValidationError("Evidence must contain only JSON values")

    if type(value) is not dict:
        raise ValidationError("Each evidence component must be a JSON object")
    try:
        validate(value)
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError) as error:
        raise ValidationError("Evidence must be finite, acyclic JSON") from error


_SCHEMA = (
    """CREATE TABLE evidence (
        evidence_id TEXT PRIMARY KEY NOT NULL CHECK(length(trim(evidence_id)) > 0),
        auction_source TEXT NOT NULL CHECK(length(trim(auction_source)) > 0),
        auction_id TEXT NOT NULL CHECK(length(trim(auction_id)) > 0),
        lot_id TEXT NOT NULL CHECK(length(trim(lot_id)) > 0),
        marketplace_source TEXT NOT NULL CHECK(length(trim(marketplace_source)) > 0),
        listing_id TEXT NOT NULL CHECK(length(trim(listing_id)) > 0),
        lot_json TEXT NOT NULL CHECK(json_valid(lot_json) AND json_type(lot_json) = 'object'),
        listing_json TEXT NOT NULL CHECK(json_valid(listing_json) AND json_type(listing_json) = 'object'),
        context_json TEXT NOT NULL CHECK(json_valid(context_json) AND json_type(context_json) = 'object'),
        recorded_at TEXT NOT NULL,
        UNIQUE(evidence_id, auction_source, auction_id, lot_id, marketplace_source, listing_id)
    )""",
    """CREATE TABLE decision_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE CHECK(length(trim(event_id)) > 0),
        reviewer_id TEXT NOT NULL CHECK(length(trim(reviewer_id)) > 0),
        auction_source TEXT NOT NULL,
        auction_id TEXT NOT NULL,
        lot_id TEXT NOT NULL,
        marketplace_source TEXT NOT NULL,
        listing_id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        decision TEXT NOT NULL CHECK(decision IN ('ACCEPT', 'REJECT', 'UNSURE')),
        reasons_json TEXT NOT NULL CHECK(json_valid(reasons_json) AND json_type(reasons_json) = 'array'),
        notes TEXT,
        supersedes_event_id TEXT,
        recorded_at TEXT NOT NULL,
        CHECK(decision != 'REJECT' OR json_array_length(reasons_json) > 0),
        CHECK(supersedes_event_id IS NULL OR supersedes_event_id != event_id),
        UNIQUE(event_id, reviewer_id, auction_source, auction_id, lot_id, marketplace_source, listing_id),
        FOREIGN KEY(evidence_id, auction_source, auction_id, lot_id, marketplace_source, listing_id)
            REFERENCES evidence(evidence_id, auction_source, auction_id, lot_id, marketplace_source, listing_id),
        FOREIGN KEY(supersedes_event_id, reviewer_id, auction_source, auction_id, lot_id, marketplace_source, listing_id)
            REFERENCES decision_events(event_id, reviewer_id, auction_source, auction_id, lot_id, marketplace_source, listing_id)
    )""",
    """CREATE UNIQUE INDEX one_initial_decision ON decision_events
        (reviewer_id, auction_source, auction_id, lot_id, marketplace_source, listing_id)
        WHERE supersedes_event_id IS NULL""",
    """CREATE UNIQUE INDEX one_correction ON decision_events(supersedes_event_id)
        WHERE supersedes_event_id IS NOT NULL""",
    """CREATE TRIGGER valid_reasons BEFORE INSERT ON decision_events
        WHEN EXISTS (SELECT 1 FROM json_each(NEW.reasons_json)
            WHERE type != 'text' OR value NOT IN (
                'CONDITION_DIFFERENCE', 'MODEL_VARIANT_MISMATCH', 'WRONG_CATEGORY',
                'QUANTITY_BUNDLE_MISMATCH', 'ACCESSORY_MISMATCH', 'OTHER'))
        BEGIN SELECT RAISE(ABORT, 'Invalid reason code'); END""",
) + tuple(
    f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} "
    "BEGIN SELECT RAISE(ABORT, 'Append-only feedback records'); END"
    for table in ("evidence", "decision_events") for action in ("UPDATE", "DELETE")
)
_SCOPE = " AND ".join(f"{name} = ?" for name in _IDENTITY_FIELDS)


class FeedbackStore:
    """Explicit SQLite API. Call initialize() before use; close after use."""

    def __init__(self, path, *, timeout=5.0):
        try:
            path = os.fspath(path)
        except TypeError as error:
            raise ValidationError("An explicit database path is required") from error
        if not isinstance(path, str) or not path.strip() or "\x00" in path:
            raise ValidationError("An explicit database path is required")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout < 0:
            raise ValidationError("timeout must be a finite nonnegative number of seconds")
        try:
            self._db = sqlite3.connect(path, timeout=timeout, isolation_level=None)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.execute("PRAGMA synchronous = FULL")
        except sqlite3.Error as error:
            if hasattr(self, "_db"):
                self._db.close()
            raise StorageError("Cannot open feedback database") from error

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._db.close()

    @contextmanager
    def _access(self, *, write=False):
        try:
            if write:
                self._db.execute("BEGIN IMMEDIATE")
            yield
            if write:
                self._db.commit()
        except Exception as error:
            if write:
                try:
                    self._db.rollback()
                except sqlite3.Error:
                    pass
            if isinstance(error, sqlite3.Error):
                raise StorageError("Feedback database operation failed") from error
            raise

    def _check_schema(self):
        app_id = self._db.execute("PRAGMA application_id").fetchone()[0]
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if (app_id, version) != (_APPLICATION_ID, _SCHEMA_VERSION):
            raise StorageError("Uninitialized or unsupported feedback database; no migration attempted")

    def initialize(self):
        """Create schema in an empty DB, or validate an existing version. No imports."""
        with self._access(write=True):
            app_id = self._db.execute("PRAGMA application_id").fetchone()[0]
            version = self._db.execute("PRAGMA user_version").fetchone()[0]
            if (app_id, version) == (_APPLICATION_ID, _SCHEMA_VERSION):
                return
            objects = self._db.execute("SELECT name FROM sqlite_master").fetchall()
            if app_id or version or objects:
                raise StorageError("Refusing to initialize a nonempty or unsupported database")
            for statement in _SCHEMA:
                self._db.execute(statement)
            self._db.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            self._db.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    def add_evidence(self, evidence_id, relationship, *, lot, listing, candidate_context):
        """Store an immutable evidence bundle; exact retries are idempotent.

        Each component may contain a snapshot or an explicitly versioned reference.
        Empty objects preserve unknown evidence; source timestamps are never invented.
        """
        _identity(evidence_id, "evidence_id")
        values = _relationship_values(relationship)
        payload = tuple(_snapshot(value) for value in (lot, listing, candidate_context))
        with self._access(write=True):
            self._check_schema()
            old = self._db.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
            if old is not None:
                if tuple(old[name] for name in _IDENTITY_FIELDS) != values or tuple(
                    old[name] for name in ("lot_json", "listing_json", "context_json")
                ) != payload:
                    raise ConflictError("evidence_id already identifies different evidence")
            else:
                self._db.execute(
                    "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (evidence_id, *values, *payload, datetime.now(timezone.utc).isoformat()),
                )
        return self.get_evidence(evidence_id)

    def get_evidence(self, evidence_id):
        _identity(evidence_id, "evidence_id")
        with self._access():
            self._check_schema()
            row = self._db.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
            if row is None:
                raise ValidationError("Unknown evidence_id")
            return {
                "evidence_id": row["evidence_id"],
                "relationship": {name: row[name] for name in _IDENTITY_FIELDS},
                "lot": json.loads(row["lot_json"]), "listing": json.loads(row["listing_json"]),
                "candidate_context": json.loads(row["context_json"]), "recorded_at": row["recorded_at"],
            }

    @staticmethod
    def _event(row):
        if row is None:
            return None
        return {
            **{name: row[name] for name in (
                "event_id", "reviewer_id", "evidence_id", "decision", "notes",
                "supersedes_event_id", "recorded_at",
            )},
            "relationship": {name: row[name] for name in _IDENTITY_FIELDS},
            "reasons": json.loads(row["reasons_json"]),
        }

    def _latest(self, values, reviewer_id):
        return self._db.execute(
            f"SELECT * FROM decision_events WHERE {_SCOPE} AND reviewer_id = ? "
            "ORDER BY sequence DESC LIMIT 1", (*values, reviewer_id),
        ).fetchone()

    def record_decision(self, *, event_id, reviewer_id, evidence_id, decision,
                        expected_current_event_id, reasons=(), notes=None):
        """Append a judgment, or replay the identical event_id without another write.

        expected_current_event_id must be None for an initial judgment; corrections
        must name the current event for this reviewer and relationship. A replay
        of an older submission returns that historical event, not the latest one.
        """
        for name, value in (("event_id", event_id), ("reviewer_id", reviewer_id), ("evidence_id", evidence_id)):
            _identity(value, name)
        if expected_current_event_id is not None:
            _identity(expected_current_event_id, "expected_current_event_id")
        if not isinstance(decision, str) or decision not in DECISIONS:
            raise ValidationError("decision must be ACCEPT, REJECT or UNSURE")
        if not isinstance(reasons, (list, tuple)) or any(
            not isinstance(reason, str) or reason not in REASONS for reason in reasons
        ):
            raise ValidationError("reasons must be a list or tuple of supported reason codes")
        reasons_json = json.dumps(sorted(set(reasons)), separators=(",", ":"))
        if decision == "REJECT" and not reasons:
            raise ValidationError("REJECT requires at least one structured reason")
        if notes is not None and not isinstance(notes, str):
            raise ValidationError("notes must be text or null")
        submitted = (reviewer_id, evidence_id, decision, reasons_json, notes, expected_current_event_id)
        with self._access(write=True):
            self._check_schema()
            old = self._db.execute("SELECT * FROM decision_events WHERE event_id = ?", (event_id,)).fetchone()
            if old is not None:
                if tuple(old[name] for name in (
                    "reviewer_id", "evidence_id", "decision", "reasons_json", "notes", "supersedes_event_id",
                )) != submitted:
                    raise ConflictError("event_id already identifies a different submission")
                return self._event(old)
            evidence = self._db.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
            if evidence is None:
                raise ValidationError("Unknown evidence_id")
            values = tuple(evidence[name] for name in _IDENTITY_FIELDS)
            current = self._latest(values, reviewer_id)
            if (current["event_id"] if current else None) != expected_current_event_id:
                raise StaleDecisionError("Expected event is not current for this reviewer and relationship")
            self._db.execute(
                "INSERT INTO decision_events (event_id, reviewer_id, evidence_id, decision, reasons_json, "
                "notes, supersedes_event_id, auction_source, auction_id, lot_id, marketplace_source, "
                "listing_id, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, *submitted, *values, datetime.now(timezone.utc).isoformat()),
            )
            return self._event(self._latest(values, reviewer_id))

    def latest_decision(self, relationship, reviewer_id):
        values = _relationship_values(relationship)
        _identity(reviewer_id, "reviewer_id")
        with self._access():
            self._check_schema()
            return self._event(self._latest(values, reviewer_id))

    def history(self, relationship, reviewer_id):
        """All events in transaction insertion order, including superseded judgments."""
        values = _relationship_values(relationship)
        _identity(reviewer_id, "reviewer_id")
        with self._access():
            self._check_schema()
            return [self._event(row) for row in self._db.execute(
                f"SELECT * FROM decision_events WHERE {_SCOPE} AND reviewer_id = ? ORDER BY sequence",
                (*values, reviewer_id),
            )]
