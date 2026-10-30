"""Offline AppTest pilot acceptance checks; all persistent data is temporary."""
import copy
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from core import audit_evidence as evidence
from core import audit_pilot as pilot
from core import audit_pilot_demo as demo
from core.feedback_store import FeedbackStore, Relationship, StorageError

APP = Path(__file__).resolve().parents[1] / "apps/internal_validation_ui.py"


class PilotUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {"AUDIT_PILOT_HOME": str(self.root),
                                     "AUDIT_PILOT_CONFIG": str(pilot.ROOT / "config/internal-audit.example.json")})
        env.start(); self.addCleanup(env.stop)
        network = patch.object(socket.socket, "connect", side_effect=AssertionError("Offline tests only"))
        network.start(); self.addCleanup(network.stop)

    def start(self):
        app = AppTest.from_file(str(APP), default_timeout=15).run()
        self.clean(app)
        return app

    def clean(self, app):
        self.assertEqual([e.message for e in app.exception], [])
        self.assertEqual([e.value for e in app.error], [])

    def widget(self, elements, label):
        return next(element for element in elements if element.label == label)

    def click(self, app, label):
        self.widget(app.button, label).click().run()
        return app

    def decision(self, app, value, reasons=(), notes=""):
        self.widget(app.radio, "Your judgment").set_value(value)
        self.widget(app.multiselect, "Reasons (required for REJECT)").set_value(list(reasons))
        self.widget(app.text_area, "Reviewer notes (optional)").set_value(notes)
        button = next(b for b in app.button if b.label in ("Save judgment", "Save correction"))
        button.click().run()
        return app

    def rows(self, mode="demo"):
        path = self.root / mode / "feedback.sqlite3"
        if not path.exists():
            return []
        with sqlite3.connect(path) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM decision_events ORDER BY sequence")]

    def candidate(self, app, mode="demo", reviewer="owner"):
        session = app.session_state[f"pilot_session:{mode}:{reviewer}"]
        entry = next(e for e in session["page"]["lots"] if e["lot"]["lot_id"] == session["selected_lot"])
        value = self.widget(app.selectbox, "Selected comparable").value
        return next(c for c in entry["candidates"] if c["relationship"]["listing_id"] == value)

    def live_ready(self):
        app = self.start()
        app.radio(key="data_mode").set_value("Genuine review").run()
        source = demo.source()  # Explicit mocked source; never a live fixture capture.
        result = demo.search("48980", "8078618", "offline API response")
        for index, item in enumerate(result["items"]):
            item["itemId"] = f"v1|synthetic-api-{index}|0"
        with patch.object(evidence, "acquire_crowe_for_review", return_value=source) as crowe, \
                patch.object(evidence, "fetch_ebay_candidates", return_value=result) as ebay, \
                patch.object(demo, "source", side_effect=AssertionError("No live-mode demo fallback")), \
                patch.object(demo, "search", side_effect=AssertionError("No live-mode demo fallback")):
            self.click(app, "Load configured catalog page")
            self.click(app, "Fetch candidates")
            crowe.assert_called_once(); ebay.assert_called_once()
        self.clean(app)
        return app

    def test_demo_opens_with_full_evidence_and_no_network(self):
        app = self.start()
        self.assertTrue(any("OFFLINE DEMO" in x.value for x in app.warning))
        self.assertIn("Original Crowe lot", [x.value for x in app.subheader])
        self.assertTrue(any("Short fixture description" in x.value for x in app.text))
        self.assertEqual(self.widget(app.selectbox, "Crowe photograph").options, [f"Photo {i} of 5" for i in range(1, 6)])
        self.assertEqual(self.rows(), [])

    def test_previous_next_lot_navigation_and_checkpoint(self):
        app = self.start()
        self.click(app, "Next lot"); self.clean(app)
        self.assertEqual(self.widget(app.selectbox, "Review queue").value, "8078619")
        self.assertTrue(any("NOT_REQUESTED" in x.value for x in app.warning))
        self.assertTrue(any("Description unavailable" in x.value for x in app.text))
        restored = self.start()
        self.assertEqual(self.widget(restored.selectbox, "Review queue").value, "8078619")
        self.click(app, "Previous lot"); self.clean(app)
        self.assertEqual(self.widget(app.selectbox, "Review queue").value, "8078618")

    def test_candidate_navigation_keeps_listing_identity_and_unknown_shipping(self):
        app = self.start()
        self.click(app, "Next candidate"); self.clean(app)
        self.assertEqual(self.candidate(app)["relationship"]["listing_id"], "demo|listing-B|0")
        self.assertTrue(any(x.value == "Shipping: Unknown" for x in app.text))
        self.assertTrue(any("Listing image unavailable" in x.value for x in app.info))
        restored = self.start()
        self.assertEqual(self.candidate(restored)["relationship"]["listing_id"], "demo|listing-B|0")
        self.click(app, "Previous candidate")
        self.assertEqual(self.candidate(app)["relationship"]["listing_id"], "demo|listing-A|0")

    def test_accept_reject_unsure_corrections_and_restart(self):
        app = self.start()
        self.decision(app, "ACCEPT"); self.clean(app)
        self.decision(app, "REJECT", ["MODEL_VARIANT_MISMATCH"], "Different size"); self.clean(app)
        self.decision(app, "UNSURE", notes="Need a closer look"); self.clean(app)
        rows = self.rows()
        self.assertEqual([r["decision"] for r in rows], ["ACCEPT", "REJECT", "UNSURE"])
        self.assertEqual(rows[1]["supersedes_event_id"], rows[0]["event_id"])
        self.assertEqual(rows[2]["supersedes_event_id"], rows[1]["event_id"])
        self.assertEqual(len({r["event_id"] for r in rows}), 3)
        restored = self.start()
        self.assertTrue(any("Current judgment: UNSURE" in x.value for x in restored.info))
        self.assertEqual(len(self.rows()), 3)

    def test_rejection_requires_reason_and_does_not_confirm_save(self):
        app = self.start()
        self.decision(app, "REJECT")
        self.assertTrue(any("structured rejection reason" in x.value for x in app.error))
        self.assertEqual(self.rows(), [])
        self.assertEqual(list(app.success), [])

    def test_independent_reviewer_histories(self):
        app = self.start(); self.decision(app, "ACCEPT")
        app.selectbox(key="reviewer").set_value("buyer").run(); self.clean(app)
        self.assertTrue(any("No judgment saved" in x.value for x in app.info))
        self.decision(app, "REJECT", ["CONDITION_DIFFERENCE"]); self.clean(app)
        app.selectbox(key="reviewer").set_value("owner").run()
        self.assertTrue(any("Current judgment: ACCEPT" in x.value for x in app.info))
        self.assertEqual([(r["reviewer_id"], r["decision"]) for r in self.rows()], [("owner", "ACCEPT"), ("buyer", "REJECT")])

    def test_genuine_mode_uses_api_id_and_separate_database(self):
        app = self.start(); self.decision(app, "UNSURE")
        live = self.live_ready()
        self.decision(live, "ACCEPT"); self.clean(live)
        self.assertEqual(self.rows("live")[0]["listing_id"], "v1|synthetic-api-0|0")
        self.assertEqual(self.rows()[0]["listing_id"], "demo|listing-A|0")
        self.assertEqual(len(self.rows()), 1); self.assertEqual(len(self.rows("live")), 1)
        restored = self.start()
        with patch.object(evidence, "acquire_crowe_for_review", side_effect=AssertionError("No reload network")), \
                patch.object(evidence, "fetch_ebay_candidates", side_effect=AssertionError("No reload network")):
            restored.radio(key="data_mode").set_value("Genuine review").run()
        self.clean(restored)
        self.assertTrue(any("Current judgment: ACCEPT" in x.value for x in restored.info))

    def test_navigation_and_rerenders_do_not_refetch(self):
        app = self.live_ready()
        with patch.object(evidence, "acquire_crowe_for_review", side_effect=AssertionError("Unexpected Crowe request")) as crowe, \
                patch.object(evidence, "fetch_ebay_candidates", side_effect=AssertionError("Unexpected eBay request")) as ebay:
            self.click(app, "Next candidate"); self.click(app, "Next lot"); self.click(app, "Previous lot")
            app.run(); self.clean(app)
            crowe.assert_not_called(); ebay.assert_not_called()

    def test_detail_load_is_explicit_and_preserves_saved_decision(self):
        app = self.live_ready(); self.decision(app, "ACCEPT")
        before = self.rows("live")[0]
        source = demo.source()
        source["retrieved_at"]["detail"] = "2026-10-30T12:00:00Z"
        with patch.object(evidence, "acquire_crowe_for_review", return_value=source) as fetch:
            self.click(app, "Load lot photos and description"); self.clean(app)
            fetch.assert_called_once()
            self.assertEqual(fetch.call_args.kwargs["lot_id"], "8078618")
        self.assertTrue(any("earlier evidence" in x.value for x in app.warning))
        self.assertEqual(self.rows("live")[0], before)

    def test_detail_failure_retains_valid_crowe_evidence(self):
        app = self.live_ready()
        with patch.object(evidence, "acquire_crowe_for_review", side_effect=ValueError("synthetic failure")):
            self.click(app, "Load lot photos and description")
        self.assertTrue(any("Lot evidence load failed" in x.value for x in app.error))
        self.assertTrue(any("Short fixture description" in x.value for x in app.text))
        self.assertEqual(self.candidate(app, mode="live")["relationship"]["listing_id"], "v1|synthetic-api-0|0")

    def test_image_render_failure_leaves_feedback_controls_available(self):
        app = self.start()
        with patch("streamlit.image", side_effect=RuntimeError("synthetic image error")):
            app.run()
        self.assertTrue(any("Photograph could not be displayed" in x.value for x in app.warning))
        self.assertTrue(any(b.label == "Save judgment" for b in app.button))
        self.assertEqual([e.message for e in app.exception], [])

    def test_empty_error_history_and_recovery(self):
        app = self.start()
        for status in ("EMPTY", "ERROR"):
            self.widget(app.selectbox, "Demo search outcome").set_value(status)
            self.click(app, "Load synthetic candidates"); self.clean(app)
            self.assertTrue(any(status + " —" in x.value for x in app.warning))
            self.assertFalse(any(b.label in ("Save judgment", "Save correction") for b in app.button))
        recovered = self.start()
        self.assertTrue(any("ERROR —" in x.value for x in recovered.warning))
        self.assertEqual(len(self.widget(recovered.selectbox, "Retrieved candidate sets").options), 3)
        self.widget(recovered.selectbox, "Retrieved candidate sets").set_value(0).run(); self.clean(recovered)
        self.assertEqual(self.candidate(recovered)["relationship"]["listing_id"], "demo|listing-A|0")

    def test_no_credentials_gives_explicit_error_not_fake_candidates(self):
        app = self.live_ready()
        with patch.object(evidence, "get_oauth_token", return_value=None):
            self.click(app, "Fetch candidates")
        self.assertTrue(any("credentials or authentication are unavailable" in x.value for x in app.error))
        self.assertFalse(any(x.label == "Selected comparable" for x in app.selectbox))
        self.assertIn("Original Crowe lot", [x.value for x in app.subheader])
        self.assertEqual(self.rows("live"), [])

    def test_accept_cannot_verify_lot_or_change_price(self):
        app = self.start()
        prices_before = [x.value for x in app.text if "USD" in x.value]
        self.decision(app, "ACCEPT"); self.clean(app)
        self.assertEqual([x.value for x in app.text if "USD" in x.value], prices_before)
        self.assertEqual(list(app.metric), [])
        text = " ".join(x.value for kind in (app.info, app.success, app.warning, app.subheader, app.markdown) for x in kind)
        self.assertNotIn("VERIFIED", text)
        self.assertNotIn("Market Floor", text)
        self.assertNotIn("Max Hammer", text)

    def test_reordering_preserves_judgment_identity(self):
        app = self.start(); self.decision(app, "ACCEPT")
        session = app.session_state["pilot_session:demo:owner"]
        session["searches"]["8078618"]["items"].reverse()
        with FeedbackStore(self.root / "demo/feedback.sqlite3") as store:
            pilot.refresh_entry(session, "8078618", store)
        app.run(); self.clean(app)
        self.assertEqual(self.candidate(app)["relationship"]["listing_id"], "demo|listing-A|0")
        self.assertTrue(any("earlier evidence" in x.value for x in app.warning))
        self.click(app, "Previous candidate")
        self.assertEqual(self.candidate(app)["relationship"]["listing_id"], "demo|listing-B|0")
        self.assertTrue(any("No judgment saved" in x.value for x in app.info))
        self.assertEqual(len(self.rows()), 1)

    def test_failed_save_has_no_success_and_retry_reuses_event(self):
        app = self.start()
        original = FeedbackStore.record_decision
        submitted_ids = []

        def commit_then_fail(store, **kwargs):
            submitted_ids.append(kwargs["event_id"])
            original(store, **kwargs)
            raise StorageError("Synthetic uncertain commit")

        with patch.object(FeedbackStore, "record_decision", commit_then_fail):
            self.decision(app, "ACCEPT")
        self.assertTrue(any("Save not confirmed" in x.value for x in app.error))
        self.assertEqual(list(app.success), [])
        self.assertEqual(len(self.rows()), 1)
        self.decision(app, "ACCEPT"); self.clean(app)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]["event_id"], submitted_ids[0])

    def test_concurrent_correction_reloads_without_overwriting(self):
        app = self.start(); self.decision(app, "ACCEPT")
        candidate = self.candidate(app)
        with FeedbackStore(self.root / "demo/feedback.sqlite3") as store:
            current = store.latest_decision(Relationship(**candidate["relationship"]), "owner")
            store.record_decision(event_id="other-window", reviewer_id="owner", evidence_id=candidate["evidence_id"],
                                  decision="REJECT", reasons=["OTHER"], expected_current_event_id=current["event_id"])
        self.decision(app, "UNSURE"); self.clean(app)
        self.assertTrue(any("Another save changed" in x.value for x in app.warning))
        self.assertEqual([r["decision"] for r in self.rows()], ["ACCEPT", "REJECT"])
        self.decision(app, "UNSURE"); self.clean(app)
        self.assertEqual(self.rows()[-1]["decision"], "UNSURE")

    def test_changed_evidence_requires_fresh_review_and_durable_history(self):
        app = self.start(); self.decision(app, "ACCEPT")
        old = self.rows()[0]["evidence_id"]
        self.widget(app.text_input, "Search query").set_value("different demo query")
        self.click(app, "Load synthetic candidates"); self.clean(app)
        self.assertTrue(any("earlier evidence" in x.value for x in app.warning))
        self.assertNotEqual(self.candidate(app)["evidence_id"], old)
        self.decision(app, "ACCEPT"); self.clean(app)
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(self.rows()[0]["evidence_id"], old)

    def test_corrupt_checkpoint_is_disclosed_without_demo_fallback(self):
        (self.root / "live").mkdir()
        (self.root / "live/session-owner.json").write_text("broken JSON")
        app = self.start(); app.radio(key="data_mode").set_value("Genuine review").run()
        self.assertTrue(any("could not be restored" in x.value for x in app.error))
        self.assertEqual(self.rows("live"), [])

    def test_checkpoint_failure_is_disclosed_and_previous_file_preserved(self):
        app = self.start()
        path = self.root / "demo/session-owner.json"
        previous = path.read_bytes()
        with patch.object(pilot.os, "replace", side_effect=OSError("synthetic disk failure")):
            self.click(app, "Next lot")
        self.assertTrue(any("Queue recovery could not be saved" in x.value for x in app.warning))
        self.assertEqual(path.read_bytes(), previous)


class PilotHelperTests(unittest.TestCase):
    def test_image_urls_are_restricted_and_medium_is_preferred(self):
        allowed = "https://as-assets.marknetalliance.com/medium/example.jpg"
        self.assertEqual(pilot.image_url({"cached_assets": [{"variant": "original", "url": "https://as-assets.marknetalliance.com/original/a.jpg"},
                                                             {"variant": "medium", "url": allowed}]}), allowed)
        for value in ("http://i.ebayimg.com/a.jpg", "https://i.ebayimg.com.evil.invalid/a", "https://user:secret@i.ebayimg.com/a",
                      "https://i.ebayimg.com:444/a", "javascript:alert(1)", "https://unapproved.invalid/image", None):
            self.assertIsNone(pilot.safe_url(value, pilot.IMAGE_HOSTS))
        thumbnail = {"imageUrl": "https://i.ebayimg.com/thumb.jpg"}
        self.assertEqual(pilot.listing_image({"thumbnailImages": [thumbnail]}), thumbnail)

    def test_description_html_is_plain_text_without_script(self):
        self.assertEqual(pilot.description({"description_html": "<p>All &amp; available</p><script>bad()</script><style>bad</style><div>details</div>"}), "All & available\ndetails")
        self.assertEqual(pilot.money({"value": "10.00"}), "10.00 (currency unknown)")
        self.assertEqual(pilot.money(None), "Unknown")

    def test_demo_checkpoint_cannot_be_loaded_in_genuine_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "copied.json"
            path.write_text(json.dumps({"version": 1, "mode": "demo"}))
            with self.assertRaises(pilot.PilotError):
                pilot.load_session(path, "live", None)

    def test_repo_data_and_storage_aliasing_are_rejected(self):
        with patch.dict(os.environ, {"AUDIT_PILOT_HOME": str(pilot.ROOT / "private-data")}):
            with self.assertRaises(pilot.PilotError):
                pilot.storage_paths("demo", "owner")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "live").mkdir(); (root / "demo").symlink_to(root / "live", target_is_directory=True)
            with patch.dict(os.environ, {"AUDIT_PILOT_HOME": folder}), self.assertRaises(pilot.PilotError):
                pilot.storage_paths("demo", "owner")


if __name__ == "__main__":
    unittest.main()
