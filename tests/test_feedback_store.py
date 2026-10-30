"""Synthetic, offline feedback tests. All databases and legacy samples are temporary."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import socket
import sqlite3
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from core import feedback_store as module
from core.feedback_store import (
    ConflictError, FeedbackStore, Relationship, StaleDecisionError, StorageError,
    ValidationError,
)


class FeedbackStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "feedback.sqlite3"
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("Offline only"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.store = FeedbackStore(self.path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        # These opaque listing IDs are explicitly synthetic test identifiers.
        self.rel = Relationship("crowe", "auction-A", "internal-lot-A", "ebay", "v1|synthetic-A|0")
        self.lot = {
            "lot_number": "42", "title": "Synthetic test product", "model": None,
            "description": "Short synthetic description.", "retrieved_at": "2026-01-01T10:00:00Z",
            "version": "lot-v1", "images": [{"attachment_id": "synthetic-image-2"},
                                          {"attachment_id": "synthetic-image-1"}],
        }
        self.listing = {"price": {"value": "10.00", "currency": "USD"}, "version": "listing-v1"}
        self.context = {"query": "synthetic product", "rank": 1, "filters": {"condition": None}}
        self.evidence("evidence-A")

    def evidence(self, evidence_id, relationship=None, **overrides):
        return self.store.add_evidence(
            evidence_id, relationship or self.rel,
            lot=overrides.get("lot", self.lot), listing=overrides.get("listing", self.listing),
            candidate_context=overrides.get("candidate_context", self.context),
        )

    def decide(self, event_id="event-A", **overrides):
        args = dict(event_id=event_id, reviewer_id="owner", evidence_id="evidence-A",
                    decision="ACCEPT", expected_current_event_id=None)
        args.update(overrides)
        return self.store.record_decision(**args)

    def test_initialization_is_explicit_repeatable_and_persistent(self):
        self.store.initialize()
        with FeedbackStore(self.root / "new.sqlite3") as fresh:
            with self.assertRaises(StorageError):
                fresh.latest_decision(self.rel, "owner")
            fresh.initialize()
            self.assertIsNone(fresh.latest_decision(self.rel, "owner"))
        with FeedbackStore(self.path) as reopened:
            reopened.initialize()
            self.assertEqual(reopened.get_evidence("evidence-A")["lot"], self.lot)

    def test_same_display_number_in_different_auctions(self):
        other = replace(self.rel, auction_id="auction-B")
        self.evidence("evidence-B", other)
        self.decide()
        self.assertIsNone(self.store.latest_decision(other, "owner"))
        self.decide("event-B", evidence_id="evidence-B", decision="UNSURE")
        self.assertEqual(self.store.latest_decision(self.rel, "owner")["decision"], "ACCEPT")
        self.assertEqual(self.store.latest_decision(other, "owner")["decision"], "UNSURE")

    def test_listing_used_against_different_lots_is_isolated(self):
        other = replace(self.rel, lot_id="internal-lot-B")
        self.evidence("evidence-B", other)
        self.decide()
        self.assertIsNone(self.store.latest_decision(other, "owner"))
        with self.assertRaises(StaleDecisionError):
            self.decide("event-B", evidence_id="evidence-B", expected_current_event_id="event-A")

    def test_every_identity_component_scopes_decisions(self):
        self.decide()
        for field in ("auction_source", "auction_id", "lot_id", "marketplace_source", "listing_id"):
            with self.subTest(field=field):
                other = replace(self.rel, **{field: "different-source-id"})
                self.evidence("evidence-" + field, other)
                self.assertIsNone(self.store.latest_decision(other, "owner"))

    def test_reordering_does_not_transfer_decisions(self):
        other = replace(self.rel, listing_id="v1|synthetic-B|0")
        self.evidence("evidence-B", other, candidate_context={"rank": 2})
        original = self.decide()
        self.evidence("evidence-A-refresh", candidate_context={"rank": 2})
        self.evidence("evidence-B-refresh", other, candidate_context={"rank": 1})
        self.assertEqual(self.store.latest_decision(self.rel, "owner"), original)
        self.assertIsNone(self.store.latest_decision(other, "owner"))
        self.assertEqual(self.store.get_evidence(original["evidence_id"])["candidate_context"]["rank"], 1)

    def test_corrections_history_and_reopen(self):
        first = self.decide()
        second = self.decide("event-B", decision="REJECT", reasons=["MODEL_VARIANT_MISMATCH"],
                             expected_current_event_id="event-A", notes="Different synthetic variant")
        third = self.decide("event-C", decision="UNSURE", expected_current_event_id="event-B")
        self.assertEqual(second["supersedes_event_id"], first["event_id"])
        self.assertEqual(third["supersedes_event_id"], second["event_id"])
        self.store.close()
        with FeedbackStore(self.path) as reopened:
            self.assertEqual(reopened.latest_decision(self.rel, "owner"), third)
            self.assertEqual(reopened.history(self.rel, "owner"), [first, second, third])

    def test_two_reviewers_have_independent_histories(self):
        first = self.decide()
        second = self.decide("event-B", reviewer_id="buyer", decision="REJECT", reasons=["WRONG_CATEGORY"])
        self.assertEqual(self.store.latest_decision(self.rel, "owner"), first)
        self.assertEqual(self.store.latest_decision(self.rel, "buyer"), second)
        with self.assertRaises(StaleDecisionError):
            self.decide("event-C", reviewer_id="buyer", expected_current_event_id="event-A")

    def test_stale_correction_and_missing_expected_revision(self):
        self.decide()
        for expected in (None, "nonexistent-event"):
            with self.subTest(expected=expected), self.assertRaises(StaleDecisionError):
                self.decide("event-B", expected_current_event_id=expected)
        self.assertEqual(len(self.store.history(self.rel, "owner")), 1)
        self.decide("event-C", decision="UNSURE", expected_current_event_id="event-A")

    def test_concurrent_corrections_have_one_winner(self):
        self.decide()
        barrier = Barrier(2)

        def correct(event_id):
            with FeedbackStore(self.path) as worker:
                current = worker.latest_decision(self.rel, "owner")["event_id"]
                barrier.wait(timeout=5)
                try:
                    worker.record_decision(event_id=event_id, reviewer_id="owner", evidence_id="evidence-A",
                                           decision="UNSURE", expected_current_event_id=current)
                    return "saved"
                except StaleDecisionError:
                    return "stale"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(correct, ["event-B", "event-C"]))
        self.assertCountEqual(results, ["saved", "stale"])
        self.assertEqual(len(self.store.history(self.rel, "owner")), 2)

    def test_duplicate_submission_is_idempotent_even_after_correction(self):
        first = self.decide()
        self.assertEqual(self.decide(), first)
        latest = self.decide("event-B", decision="UNSURE", expected_current_event_id="event-A")
        self.assertEqual(self.decide(), first)
        self.assertEqual(self.store.latest_decision(self.rel, "owner"), latest)
        self.assertEqual(len(self.store.history(self.rel, "owner")), 2)

    def test_concurrent_duplicate_submissions_append_once(self):
        barrier = Barrier(2)

        def submit(_):
            with FeedbackStore(self.path) as worker:
                barrier.wait(timeout=5)
                return worker.record_decision(
                    event_id="event-A", reviewer_id="owner", evidence_id="evidence-A",
                    decision="ACCEPT", expected_current_event_id=None,
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.store.history(self.rel, "owner")), 1)

    def test_duplicate_identifier_with_changed_payload_fails(self):
        self.decide()
        for change in ({"decision": "UNSURE"}, {"reviewer_id": "buyer"}, {"notes": "Changed"},
                       {"expected_current_event_id": "event-A"}):
            with self.subTest(change=change), self.assertRaises(ConflictError):
                self.decide(**change)
        self.assertEqual(len(self.store.history(self.rel, "owner")), 1)

    def test_evidence_refresh_and_returned_mutations_cannot_rewrite_history(self):
        first = self.decide()
        self.evidence("evidence-refresh", listing={"price": {"value": "20.00"}, "version": "listing-v2"})
        current = self.store.get_evidence("evidence-A")
        current["listing"]["price"]["value"] = "999.00"
        self.listing["price"]["value"] = "777.00"
        self.assertEqual(self.store.get_evidence(first["evidence_id"])["listing"]["price"]["value"], "10.00")
        revised = self.decide("event-B", evidence_id="evidence-refresh", expected_current_event_id="event-A")
        self.assertEqual(revised["evidence_id"], "evidence-refresh")
        self.assertEqual(self.store.history(self.rel, "owner")[0], first)

    def test_evidence_idempotency_and_conflicts(self):
        original = self.store.get_evidence("evidence-A")
        self.assertEqual(self.evidence("evidence-A"), original)
        with self.assertRaises(ConflictError):
            self.evidence("evidence-A", listing={"price": "20.00"})
        with self.assertRaises(ConflictError):
            self.evidence("evidence-A", replace(self.rel, lot_id="other"))
        self.assertEqual(self.store.get_evidence("evidence-A"), original)

    def test_snapshots_retain_nulls_order_and_versioned_references(self):
        evidence = self.store.get_evidence("evidence-A")
        self.assertEqual(evidence["lot"], self.lot)
        self.assertEqual(evidence["listing"], self.listing)
        self.assertEqual(evidence["candidate_context"], self.context)
        reference = {"reference": "synthetic-evidence:lot", "version": "v3"}
        result = self.evidence("reference-only", lot=reference, listing={}, candidate_context={})
        self.assertEqual(result["lot"], reference)
        self.assertEqual(result["listing"], {})

    def test_missing_or_nontext_identities_fail(self):
        for name in module._IDENTITY_FIELDS:
            for value in (None, "", " ", 42, " leading", "trailing ", "id\n"):
                with self.subTest(name=name, value=value), self.assertRaises(ValidationError):
                    replace(self.rel, **{name: value})
        for field in ("event_id", "reviewer_id", "evidence_id"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.decide(**{field: ""})

    def test_invalid_decisions_reasons_and_notes_fail(self):
        for change in ({"decision": "verified"}, {"decision": []}, {"decision": "REJECT"},
                       {"reasons": "OTHER"}, {"reasons": ["PROFITABLE"]}, {"reasons": [None]},
                       {"notes": {}}, {"evidence_id": "missing"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.decide(**change)
        self.assertEqual(self.store.history(self.rel, "owner"), [])

    def test_all_reason_codes_and_normalized_idempotency(self):
        reasons = sorted(module.REASONS)
        first = self.decide(decision="REJECT", reasons=reasons)
        self.assertEqual(first["reasons"], reasons)
        self.assertEqual(self.decide(decision="REJECT", reasons=list(reversed(reasons)) + reasons), first)

    def test_non_json_evidence_is_rejected_without_writes(self):
        cycle = {}; cycle["self"] = cycle
        for payload in ([], {1: "key"}, {"value": float("nan")}, {"value": float("inf")},
                        {"tuple": (1, 2)}, {"obj": object()}, cycle):
            with self.subTest(kind=type(payload).__name__), self.assertRaises(ValidationError):
                self.evidence("bad", lot=payload)
        with self.assertRaises(ValidationError):
            self.store.get_evidence("bad")

    def test_immutable_rows_and_database_constraints(self):
        self.decide()
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA foreign_keys = ON")
            for table in ("evidence", "decision_events"):
                for sql in (f"DELETE FROM {table}", f"UPDATE {table} SET lot_id = 'changed'"):
                    with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                        db.execute(sql)
            columns = [r[1] for r in db.execute("PRAGMA table_info(decision_events)") if r[1] != "sequence"]
            original = dict(zip(columns, db.execute("SELECT " + ",".join(columns) + " FROM decision_events").fetchone()))
            for change in ({"supersedes_event_id": None}, {"decision": "VERIFIED"},
                           {"decision": "REJECT", "reasons_json": "[]"},
                           {"reasons_json": '["PROFITABLE"]'}, {"evidence_id": "missing"},
                           {"reviewer_id": "other", "supersedes_event_id": "event-A"}):
                row = {**original, "event_id": "illegal", "supersedes_event_id": "event-A", **change}
                sql = f"INSERT INTO decision_events ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
                with self.subTest(change=change), self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql, [row[c] for c in columns])
        self.assertEqual(len(self.store.history(self.rel, "owner")), 1)

    def test_transaction_failure_rolls_back_and_is_visible(self):
        self.decide()
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TRIGGER injected_failure AFTER INSERT ON decision_events "
                       "WHEN NEW.event_id = 'event-B' BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        with self.assertRaises(StorageError) as caught:
            self.decide("event-B", expected_current_event_id="event-A")
        self.assertIsInstance(caught.exception.__cause__, sqlite3.IntegrityError)
        self.assertEqual(self.store.latest_decision(self.rel, "owner")["event_id"], "event-A")
        self.assertEqual(len(self.store.history(self.rel, "owner")), 1)
        self.decide("event-C", expected_current_event_id="event-A")

    def test_schema_initialization_rolls_back(self):
        with FeedbackStore(self.root / "init-failure.sqlite3") as fresh:
            with patch.object(module, "_SCHEMA", module._SCHEMA + ("INVALID SQL",)):
                with self.assertRaises(StorageError):
                    fresh.initialize()
            fresh.initialize()
            self.assertIsNone(fresh.latest_decision(self.rel, "owner"))

    def test_database_lock_is_an_explicit_failure_then_retry_succeeds(self):
        with FeedbackStore(self.path, timeout=0) as impatient, sqlite3.connect(self.path) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            args = dict(event_id="event-A", reviewer_id="owner", evidence_id="evidence-A",
                        decision="ACCEPT", expected_current_event_id=None)
            with self.assertRaises(StorageError):
                impatient.record_decision(**args)
            blocker.rollback()
            self.assertEqual(impatient.record_decision(**args)["event_id"], "event-A")

    def test_explicit_path_schema_and_storage_errors(self):
        for path in (None, "", "\x00", 12):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                FeedbackStore(path)
        for timeout in (-1, float("inf"), "5", True):
            with self.subTest(timeout=timeout), self.assertRaises(ValidationError):
                FeedbackStore(self.path, timeout=timeout)
        with self.assertRaises(StorageError):
            FeedbackStore(self.root / "absent-parent" / "db.sqlite3")
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA user_version = 999")
        with self.assertRaises(StorageError):
            self.store.initialize()
        with self.assertRaises(StorageError):
            self.decide()
        self.store.close()
        with self.assertRaises(StorageError):
            self.store.get_evidence("evidence-A")

    def test_legacy_files_are_unchanged_and_not_imported(self):
        originals = {
            "auction_manifest.csv": b"lot,title\r\n42,Legacy\r\n",
            "comp_audit.csv": b"crowe_lot,comp_rank\n42,1\n",
            "profitable_lots.csv": b"original financial outputs\x00\r\n",
            "data/audit_decisions.jsonl": b'{"decision":"ACCEPT","ebay_item_id":"comp_42_1"}\n',
            "data/historical_reconciliations.jsonl": b'{"legacy":"unknown provenance"}\n',
        }
        for name, content in originals.items():
            path = self.root / name; path.parent.mkdir(exist_ok=True)
            path.write_bytes(content)
        self.store.initialize()
        self.assertEqual(self.store.history(self.rel, "owner"), [])
        self.decide()
        with self.assertRaises(StorageError):
            with FeedbackStore(self.root / "comp_audit.csv") as legacy:
                legacy.initialize()
        for name, content in originals.items():
            self.assertEqual((self.root / name).read_bytes(), content, name)

    def test_unrelated_sqlite_database_is_not_adopted(self):
        path = self.root / "unrelated.sqlite3"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE legacy (value TEXT)")
            db.execute("INSERT INTO legacy VALUES ('keep')")
        before = path.read_bytes()
        with FeedbackStore(path) as other, self.assertRaises(StorageError):
            other.initialize()
        self.assertEqual(path.read_bytes(), before)

    def test_accept_adds_only_match_feedback_not_verification_or_valuation(self):
        evidence_before = self.store.get_evidence("evidence-A")
        event = self.decide()
        self.assertEqual(set(event), {
            "event_id", "reviewer_id", "evidence_id", "decision", "notes", "supersedes_event_id",
            "recorded_at", "relationship", "reasons",
        })
        self.assertEqual(event["decision"], "ACCEPT")
        self.assertEqual(self.store.get_evidence("evidence-A"), evidence_before)
        with sqlite3.connect(self.path) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertEqual(tables, {"evidence", "decision_events", "sqlite_sequence"})


if __name__ == "__main__":
    unittest.main()
