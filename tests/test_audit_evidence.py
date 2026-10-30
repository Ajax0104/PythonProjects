"""Offline source-to-feedback integration with synthetic eBay Browse responses."""

import copy
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from core import audit_evidence as audit
from core.feedback_store import FeedbackStore, Relationship, StorageError
from crowe_acquisition import AcquisitionError
from crowe_source_parser import extract_apollo_state


FIXTURES = Path(__file__).parent / "fixtures" / "crowe"
CATALOG_URL = "https://bids.crauctions.com/auctions/48980?page=1&items=50"
DETAIL_URL = "https://bids.crauctions.com/auctions/48980/lot/8078618"


def response(body, url, *, status=200, content_type="application/json"):
    result = requests.Response()
    result.status_code = status
    result.url = url
    result.headers["Content-Type"] = content_type
    result._content = body.encode() if isinstance(body, str) else json.dumps(body).encode()
    result._content_consumed = True
    result.close = Mock(wraps=result.close)
    return result


def item(item_id="v1|synthetic-listing-A|0"):
    return {
        "itemId": item_id, "itemWebUrl": "https://www.ebay.com/itm/synthetic-example",
        "title": "Synthetic product candidate", "condition": "Used", "conditionId": "3000",
        "image": {"imageUrl": "https://example.invalid/item.jpg"},
        "additionalImages": [{"imageUrl": "https://example.invalid/second.jpg"}],
        "price": {"value": "10.00", "currency": "CAD"},
        "shippingOptions": [{"shippingCostType": "FIXED", "shippingCost": {"value": "3.25", "currency": "CAD"}}],
        "buyingOptions": ["FIXED_PRICE"],
    }


class AuditEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "feedback.sqlite3"
        self.store = FeedbackStore(self.path)
        self.store.initialize()
        self.addCleanup(self.store.close)
        blocked = patch.object(socket.socket, "connect", side_effect=AssertionError("Tests must stay offline"))
        blocked.start(); self.addCleanup(blocked.stop)
        self.catalog_html = (FIXTURES / "historical_catalog.html").read_text()
        self.detail_html = (FIXTURES / "historical_detail.html").read_text()
        state = extract_apollo_state(self.catalog_html)
        self.args = json.loads(next(k for k in state["Auction.48980"] if k.startswith("lots("))[5:-1])
        self.crowe = self.acquire()

    def acquire(self):
        get = Mock(side_effect=[response(self.catalog_html, CATALOG_URL, content_type="text/html"),
                                response(self.detail_html, DETAIL_URL, content_type="text/html")])
        result = audit.acquire_crowe_for_review(
            CATALOG_URL, auction_id="48980", query_arguments=self.args,
            detail_url=DETAIL_URL, lot_id="8078618", http_get=get,
        )
        self.assertEqual(get.call_count, 2)
        return result

    def search(self, body=None, *, status=200, content_type="application/json", **overrides):
        args = dict(auction_id="48980", lot_id="8078618", query="synthetic & variant",
                    filters="buyingOptions:{FIXED_PRICE},conditionIds:{3000}", sort="price", limit=7,
                    marketplace_id="EBAY_CA")
        args.update(overrides)
        params = {"q": args["query"], "limit": str(args["limit"])}
        if args.get("filters") is not None:
            params["filter"] = args["filters"]
        if args.get("sort") is not None:
            params["sort"] = args["sort"]
        url = requests.Request("GET", audit.EBAY_SEARCH_URL, params=params).prepare().url
        self.reply = response(body if body is not None else {"total": 1, "itemSummaries": [item()]},
                              url, status=status, content_type=content_type)
        self.get = Mock(return_value=self.reply)
        return audit.fetch_ebay_candidates(**args, http_get=self.get, token_provider=lambda: "synthetic-test-token")

    def build(self, searches=None, crowe=None, store=None):
        return audit.build_review_page(crowe or self.crowe, searches=searches or [], store=store or self.store)

    def counts(self):
        with sqlite3.connect(self.path) as db:
            return tuple(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                         for table in ("evidence", "decision_events"))

    def test_ids_and_exact_api_evidence_survive_to_sqlite(self):
        search = self.search()
        page = self.build([search])
        candidate = page["lots"][0]["candidates"][0]
        stored = self.store.get_evidence(candidate["evidence_id"])
        self.assertEqual(stored["relationship"], {
            "auction_source": "crowe", "auction_id": "48980", "lot_id": "8078618",
            "marketplace_source": "ebay", "listing_id": "v1|synthetic-listing-A|0",
        })
        self.assertEqual(stored["listing"]["item"], item())
        self.assertEqual(stored["candidate_context"]["search"]["request"], search["request"])
        self.assertEqual(stored["listing"]["retrieved_at"], search["retrieved_at"])
        self.assertEqual(self.counts(), (1, 0))

    def test_descriptions_gallery_status_prices_and_request_provenance_are_lossless(self):
        page = self.build([self.search()])
        snapshot = self.store.get_evidence(page["lots"][0]["candidates"][0]["evidence_id"])["lot"]
        for kind in ("catalog", "detail"):
            self.assertEqual(snapshot[kind]["lot"], self.crowe[kind]["lots"][0])
            self.assertEqual(snapshot[kind]["auction"], self.crowe[kind]["auction"])
            self.assertEqual(snapshot[kind]["source"], self.crowe[kind]["source"])
            self.assertEqual(snapshot[kind]["retrieved_at"], self.crowe["retrieved_at"][kind])
        self.assertEqual(len(snapshot["detail"]["lot"]["images"]), 5)
        self.assertNotEqual(snapshot["lot_id"], snapshot["lot_number"])

    def test_active_source_and_catalog_only_input(self):
        html = (FIXTURES / "active_catalog.html").read_text()
        state = extract_apollo_state(html)
        args = json.loads(next(k for k in state["Auction.49187"] if k.startswith("lots("))[5:-1])
        url = "https://bids.crauctions.com/auctions/49187"
        get = Mock(return_value=response(html, url, content_type="text/html"))
        source = audit.acquire_crowe_for_review(url, auction_id="49187", query_arguments=args, http_get=get)
        page = self.build([self.search(auction_id="49187", lot_id="8127508")], source)
        self.assertEqual(page["auction"]["auction_status"], 200)
        self.assertIsNone(page["lots"][0]["lot"]["detail"])
        self.assertIsNone(source["retrieved_at"]["detail"])
        get.assert_called_once()

    def test_currency_shipping_and_optional_fields_are_not_guessed(self):
        sparse = {"itemId": "v1|sparse|0", "price": {"value": "0.00"}}
        search = self.search({"total": 2, "itemSummaries": [item(), sparse]})
        candidates = self.build([search])["lots"][0]["candidates"]
        self.assertEqual(candidates[0]["listing"]["item"]["shippingOptions"], item()["shippingOptions"])
        self.assertEqual(candidates[0]["listing"]["item"]["price"], {"value": "10.00", "currency": "CAD"})
        self.assertEqual(candidates[1]["listing"]["item"], sparse)

    def test_http_options_and_candidate_count_are_explicit(self):
        search = self.search(limit=17)
        self.assertEqual(search["request"]["params"]["limit"], "17")
        self.get.assert_called_once_with(
            audit.EBAY_SEARCH_URL, params=search["request"]["params"],
            headers={"Authorization": "Bearer synthetic-test-token", "X-EBAY-C-MARKETPLACE-ID": "EBAY_CA"},
            timeout=audit.TIMEOUT, allow_redirects=False, stream=True, verify=True,
        )
        self.reply.close.assert_called_once()
        self.assertNotIn("synthetic-test-token", json.dumps(search))

    def test_authentication_helper_is_reused_without_valuation_calls(self):
        self.search()
        with patch.object(audit, "get_oauth_token", return_value="synthetic-test-token") as token, \
                patch.object(audit.requests, "get", self.get), \
                patch("ebay_api_client.fetch_lowest_active_bin", side_effect=AssertionError("No V4 pricing")):
            result = audit.fetch_ebay_candidates(
                auction_id="48980", lot_id="8078618", query="synthetic & variant", limit=7,
                filters="buyingOptions:{FIXED_PRICE},conditionIds:{3000}", sort="price", marketplace_id="EBAY_CA",
            )
        self.assertEqual(result["status"], "READY")
        token.assert_called_once()

    def test_invalid_requests_do_not_call_auth_or_transport(self):
        for change in ({"limit": 0}, {"limit": 51}, {"limit": True}, {"query": ""},
                       {"auction_id": ""}, {"lot_id": "lot-number"}, {"filters": {}}, {"sort": ""}):
            args = dict(auction_id="48980", lot_id="8078618", query="synthetic"); args.update(change)
            token, get = Mock(), Mock()
            with self.subTest(change=change), self.assertRaises(audit.EvidenceError):
                audit.fetch_ebay_candidates(**args, token_provider=token, http_get=get)
            token.assert_not_called(); get.assert_not_called()

    def test_auth_failure_stays_in_queue_without_candidates(self):
        get = Mock()
        result = audit.fetch_ebay_candidates(auction_id="48980", lot_id="8078618", query="synthetic",
                                             token_provider=lambda: None, http_get=get)
        entry = self.build([result])["lots"][0]
        self.assertEqual(entry["outcome"], "ERROR")
        self.assertEqual(entry["search"]["error"]["code"], "AUTH_UNAVAILABLE")
        self.assertEqual(entry["candidates"], [])
        self.assertIsNone(entry["search"]["retrieved_at"])
        self.assertEqual(self.counts(), (0, 0)); get.assert_not_called()

    def test_empty_and_unrequested_lots_remain_visible(self):
        for body in ({"total": 0}, {"total": 0, "itemSummaries": []}):
            page = self.build([self.search(body)])
            self.assertEqual(len(page["lots"]), 1)
            self.assertEqual(page["lots"][0]["outcome"], "EMPTY")
            self.assertEqual(page["lots"][0]["candidates"], [])
        self.assertEqual(self.build()["lots"][0]["outcome"], "NOT_REQUESTED")
        self.assertEqual(self.counts(), (0, 0))

    def test_mixed_page_keeps_ready_empty_failed_and_unrequested_lots(self):
        source = copy.deepcopy(self.crowe)
        catalog = source["catalog"]
        for index in range(1, 4):
            lot = copy.deepcopy(catalog["lots"][0])
            lid = str(8078618 + index)
            lot.update(lot_id=lid, source_record_key="AuctionLot." + lid, lot_number=str(8000 + index))
            lot["raw_fields"].update(auction_lot_id=lid, lot_number=str(8000 + index))
            catalog["lots"].append(lot)
        catalog["pagination"]["returned_count"] = 4
        searches = [self.search(), self.search({"total": 0}, lot_id="8078619"),
                    self.search(status=503, lot_id="8078620")]
        page = self.build(searches, source)
        self.assertEqual([lot["outcome"] for lot in page["lots"]], ["READY", "EMPTY", "ERROR", "NOT_REQUESTED"])
        self.assertEqual(self.counts(), (1, 0))

    def test_empty_catalog_is_an_explicit_empty_selected_page(self):
        source = copy.deepcopy(self.crowe)
        source["detail"] = None; source["retrieved_at"]["detail"] = None
        source["catalog"]["lots"] = []
        source["catalog"]["pagination"].update(total=0, returned_count=0)
        page = self.build(crowe=source)
        self.assertEqual(page["lots"], [])
        self.assertEqual(page["pagination"]["total"], 0)
        self.assertEqual(self.counts(), (0, 0))

    def test_http_failures_and_redirects_are_explicit_without_retries(self):
        for status in (301, 401, 403, 429, 500):
            with self.subTest(status=status):
                result = self.search({"error": "synthetic"}, status=status)
                self.assertEqual(result["http_status"], status)
                self.assertEqual(self.build([result])["lots"][0]["outcome"], "ERROR")
                self.assertEqual(result["items"], [])
                self.get.assert_called_once(); self.reply.close.assert_called_once()

    def test_unexpected_final_url_is_rejected(self):
        self.search()
        self.reply.url = "https://unapproved.invalid/redirect"
        result = audit.fetch_ebay_candidates(auction_id="48980", lot_id="8078618", query="synthetic",
                                             http_get=self.get, token_provider=lambda: "test")
        self.assertEqual(result["error"]["code"], "UNEXPECTED_REDIRECT")
        self.assertEqual(result["items"], [])

    def test_timeout_is_visible_without_exception_text(self):
        result = audit.fetch_ebay_candidates(
            auction_id="48980", lot_id="8078618", query="synthetic",
            token_provider=lambda: "test", http_get=Mock(side_effect=requests.Timeout("private transport text")),
        )
        self.assertEqual(self.build([result])["lots"][0]["outcome"], "ERROR")
        self.assertEqual(result["error"]["code"], "TRANSPORT_ERROR")
        self.assertNotIn("private transport text", json.dumps(result))

    def test_stream_failure_closes_response_and_discards_candidates(self):
        self.search()
        self.reply.iter_content = Mock(side_effect=requests.ConnectionError("interrupted body"))
        with patch.object(audit.requests, "get", return_value=self.reply):
            result = audit.fetch_ebay_candidates(
                auction_id="48980", lot_id="8078618", query="synthetic & variant", limit=7,
                filters="buyingOptions:{FIXED_PRICE},conditionIds:{3000}", sort="price",
                token_provider=lambda: "test", marketplace_id="EBAY_CA",
            )
        self.assertEqual(result["error"]["code"], "TRANSPORT_ERROR")
        self.assertEqual(result["items"], [])
        self.assertEqual(self.reply.close.call_count, 2)

    def test_missing_or_duplicate_ids_invalidate_entire_search(self):
        for bad in ({"title": "No ID"}, {"itemId": ""}, {"itemId": None}, {"itemId": 42}, item()):
            with self.subTest(bad=bad):
                result = self.search({"total": 2, "itemSummaries": [item(), bad]})
                self.assertEqual(result["status"], "ERROR")
                self.assertEqual(result["items"], [])
                self.assertEqual(self.build([result])["lots"][0]["candidates"], [])
        self.assertEqual(self.counts(), (0, 0))

    def test_malformed_non_json_oversized_and_api_error_responses(self):
        cases = [("not json", "application/json"), ({}, "application/json"),
                 ({"total": 1}, "application/json"), ({"total": 1, "itemSummaries": []}, "application/json"),
                 ({"total": 0}, "text/html"), ('{"total":NaN}', "application/json"),
                 ('{"total":1e999}', "application/json"),
                 ({"errors": [{"errorId": 123, "message": "omit", "parameters": [{"value": "private"}]}]}, "application/json")]
        for body, content_type in cases:
            with self.subTest(body=body):
                result = self.search(body, content_type=content_type)
                self.assertEqual(self.build([result])["lots"][0]["outcome"], "ERROR")
                self.assertNotIn("private", json.dumps(result))
        with patch.object(audit, "MAX_RESPONSE_BYTES", 5):
            result = self.search()
            self.assertEqual(result["error"]["code"], "RESPONSE_TOO_LARGE")
        self.assertEqual(self.counts(), (0, 0))

    def test_overlimit_candidates_are_not_silently_truncated(self):
        result = self.search({"total": 2, "itemSummaries": [item(), item("v1|B|0")]}, limit=1)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["items"], [])

    def test_search_diagnostics_and_exact_context_are_preserved(self):
        result = self.search({"total": 1, "limit": 7, "offset": 0, "itemSummaries": [item()],
                              "warnings": [{"errorId": 111, "domain": "API_BROWSE", "category": "REQUEST", "message": "omit"}]})
        context = self.build([result])["lots"][0]["search"]
        self.assertEqual(context["request"]["params"]["q"], "synthetic & variant")
        self.assertEqual(context["response_metadata"]["warnings"], [{"errorId": 111, "domain": "API_BROWSE", "category": "REQUEST"}])
        self.assertNotIn("message", context["response_metadata"]["warnings"][0])

    def test_only_relevant_listing_fields_are_retained(self):
        extra = dict(item(), seller={"username": "synthetic-excluded"}, unrelated="excluded")
        search = self.search({"total": 1, "itemSummaries": [extra]})
        candidate = self.build([search])["lots"][0]["candidates"][0]
        self.assertEqual(candidate["listing"]["item"], item())
        self.assertNotIn("synthetic-excluded", json.dumps(self.store.get_evidence(candidate["evidence_id"])))

    def test_conflicting_crowe_identities_are_rejected_before_writes(self):
        for mutate in (
            lambda c: c["catalog"]["lots"][0].update(auction_id="999"),
            lambda c: c["catalog"]["lots"][0].update(lot_id=""),
            lambda c: c["catalog"]["lots"][0]["raw_fields"].update(auction_lot_id="999"),
            lambda c: c["detail"]["auction"].update(auction_id="999"),
            lambda c: c["detail"]["lots"][0].update(lot_number="wrong"),
            lambda c: c["catalog"]["source"].update(url="https://bids.crauctions.com/auctions/999"),
            lambda c: c["catalog"]["source"]["query_arguments"]["filter"].update(auction_id="999"),
            lambda c: c["catalog"]["source"].update(query_key='lots({"filter":{"auction_id":"999"}})'),
            lambda c: c["catalog"]["pagination"].update(returned_count=2),
            lambda c: c["retrieved_at"].update(catalog=None),
        ):
            source = copy.deepcopy(self.crowe); mutate(source)
            store = Mock()
            with self.assertRaises(audit.EvidenceError):
                self.build([self.search()], source, store)
            store.add_evidence.assert_not_called()

    def test_search_target_and_item_identity_validated_before_any_write(self):
        valid = self.search({"total": 2, "itemSummaries": [item(), item("v1|B|0")]})
        for mutate in (
            lambda s: s["target"].update(auction_id="999"),
            lambda s: s["target"].update(lot_id="999"),
            lambda s: s["items"][1].pop("itemId"),
            lambda s: s.update(status="ERROR", error={"code": "synthetic"}),
            lambda s: s["request"].update(url="https://unapproved.invalid"),
        ):
            search = copy.deepcopy(valid); mutate(search)
            store = Mock()
            with self.assertRaises(audit.EvidenceError):
                self.build([search], store=store)
            store.add_evidence.assert_not_called()

    def test_acquisition_failure_does_not_return_partial_source(self):
        get = Mock(side_effect=requests.Timeout("offline"))
        with self.assertRaises(AcquisitionError):
            audit.acquire_crowe_for_review(CATALOG_URL, auction_id="48980", query_arguments=self.args, http_get=get)
        get.assert_called_once()

    def test_snapshot_storage_errors_propagate_and_retry_is_idempotent(self):
        search = self.search()
        failing = Mock(); failing.add_evidence.side_effect = StorageError("synthetic disk failure")
        with self.assertRaises(StorageError):
            self.build([search], store=failing)
        first = self.build([search]); second = self.build([search])
        self.assertEqual(first, second)
        self.assertEqual(self.counts(), (1, 0))

    def test_reordering_and_refresh_do_not_transfer_or_rewrite_decisions(self):
        result = self.search({"total": 2, "itemSummaries": [item(), item("v1|B|0")]})
        before = self.build([result])
        first = before["lots"][0]["candidates"][0]
        rel = Relationship(**first["relationship"])
        event = self.store.record_decision(event_id="human-1", reviewer_id="owner", evidence_id=first["evidence_id"],
                                          decision="ACCEPT", expected_current_event_id=None)
        original = self.store.get_evidence(first["evidence_id"])
        result["items"].reverse()
        refreshed = self.build([result])
        reordered = refreshed["lots"][0]["candidates"]
        self.assertEqual(reordered[1]["relationship"], first["relationship"])
        self.assertNotEqual(reordered[1]["evidence_id"], first["evidence_id"])
        self.assertEqual(self.store.latest_decision(rel, "owner"), event)
        self.assertIsNone(self.store.latest_decision(Relationship(**reordered[0]["relationship"]), "owner"))
        self.assertEqual(self.store.get_evidence(first["evidence_id"]), original)
        self.assertEqual(self.counts(), (4, 1))

    def test_same_display_number_across_auctions_and_same_listing_across_lots(self):
        first = self.build([self.search()])["lots"][0]["candidates"][0]
        for aid, lid in (("48981", "8078618"), ("48980", "8078619")):
            source = copy.deepcopy(self.crowe)
            source["detail"] = None; source["retrieved_at"]["detail"] = None
            catalog = source["catalog"]
            catalog["auction"]["auction_id"] = aid
            catalog["source"]["url"] = "https://bids.crauctions.com/auctions/" + aid
            catalog["source"]["query_arguments"]["filter"]["auction_id"] = aid
            catalog["source"]["query_key"] = "lots(" + json.dumps(catalog["source"]["query_arguments"]) + ")"
            catalog["source"]["auction_query_key"] = "auction(" + json.dumps({"auction_id": aid}) + ")"
            lot = catalog["lots"][0]
            lot.update(auction_id=aid, lot_id=lid, source_record_key="AuctionLot." + lid)
            lot["raw_fields"].update(auction_id=aid, auction_lot_id=lid)
            candidate = self.build([self.search(auction_id=aid, lot_id=lid)], source)["lots"][0]["candidates"][0]
            self.assertNotEqual(first["relationship"], candidate["relationship"])
            self.assertEqual(first["relationship"]["listing_id"], candidate["relationship"]["listing_id"])
        self.assertEqual(self.counts(), (3, 0))

    def test_inputs_history_and_legacy_files_are_unchanged(self):
        files = {"comp_audit.csv": b"original\r\n", "auction_manifest.csv": b"original manifest\n",
                 "profitable_lots.csv": b"original financial outputs\n",
                 "audit_decisions.jsonl": b'{"decision":"ACCEPT"}\n',
                 "historical_reconciliations.jsonl": b'{"legacy":true}\n'}
        for name, contents in files.items():
            (self.root / name).write_bytes(contents)
        source_before = copy.deepcopy(self.crowe)
        search = self.search(); search_before = copy.deepcopy(search)
        self.build([search])
        self.assertEqual(self.crowe, source_before); self.assertEqual(search, search_before)
        self.assertEqual(self.counts(), (1, 0))
        for name, contents in files.items():
            self.assertEqual((self.root / name).read_bytes(), contents)


if __name__ == "__main__":
    unittest.main()
