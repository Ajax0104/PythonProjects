"""Offline reliability checks; every file write is inside a temporary directory."""
import csv
import io
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import requests

import crowe_scraper as scraper
import inventory_analyzer4 as pipeline


def page(*lots, content_type="text/html", status=200):
    response = requests.Response()
    response.status_code = status
    response.url = "https://catalog.invalid/auction"
    response.headers["Content-Type"] = content_type
    response._content = ("<html><body>" + "".join(lots) + "</body></html>").encode()
    response.encoding = "utf-8"
    return response


def lot(lot_id, title="Test Fan", bid="2.00"):
    return f'<div class="lot-card">Lot {lot_id}: {title} In Packaging?: Yes Damaged?: No ${bid}</div>'


class IngestionGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        previous = os.getcwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, previous)
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.http = patch.object(scraper.requests, "get").start()
        self.addCleanup(patch.stopall)
        self.sleep = patch.object(scraper.time, "sleep").start()
        self.originals = {
            "auction_manifest.csv": b"lot,title,bid,projected_sale\r\n99,OLD,1,0\r\n",
            "comp_audit.csv": b"existing audit\x00\r\n",
            "profitable_lots.csv": b"existing profits\r\n",
            "data/audit_decisions.jsonl": b'{"decision":"ACCEPT"}\n',
        }
        Path("data").mkdir()
        for name, content in self.originals.items():
            Path(name).write_bytes(content)

    def assert_originals_unchanged(self):
        for name, content in self.originals.items():
            self.assertEqual(Path(name).read_bytes(), content, name)
        self.assertEqual(list(Path('.').glob('.auction_manifest.csv.*.tmp')), [])

    def failed_pipeline(self, responses, message):
        self.http.side_effect = responses
        with patch.object(pipeline, "estimate_market_value") as price, \
             patch.object(pipeline, "LotItem") as valuation, \
             patch.object(pipeline, "Manifest") as manifest:
            with self.assertRaisesRegex(scraper.IngestionError, message):
                pipeline.main()
            price.assert_not_called()
            valuation.assert_not_called()
            manifest.assert_not_called()
        self.assert_originals_unchanged()

    def test_complete_catalog_and_csv_contract(self):
        self.http.side_effect = [page(lot(1)), page(lot(1), lot(2, "Second Fan", "3.00"))]
        rows = scraper.fetch_crowe_catalog(total_pages=2)
        self.assertEqual([r['lot'] for r in rows], ['1', '2'])
        self.assertEqual(rows[0]['packaging'], 'Yes')
        self.assertEqual(rows[0]['damaged'], 'No')
        scraper.export_to_manifest(rows)
        self.assertEqual(Path('auction_manifest.csv').read_bytes(),
            b'lot,title,bid,projected_sale\r\n1,Test Fan,2.00,0.00\r\n2,Second Fan,3.00,0.00\r\n')
        self.assertEqual(self.http.call_count, 2)
        self.assertIn('page=2&items=50', self.http.call_args.args[0])

    def test_empty_catalog_stops_pipeline(self):
        self.failed_pipeline([page()], 'no parseable lots')

    def test_failed_page_after_retries_preserves_outputs(self):
        self.failed_pipeline([page(lot(1))] + [requests.Timeout('fixture')] * 3,
                             'Page 2 failed after 3 attempts')
        self.assertEqual(self.http.call_count, 4)
        self.assertEqual(self.sleep.call_count, 2)

    def test_http_error_after_retries(self):
        self.failed_pipeline([page(status=503) for _ in range(3)], 'failed after 3 attempts')

    def test_invalid_responses_stop_pipeline(self):
        for response in [page('Access denied'), page('{"error":"blocked"}', content_type='application/json'),
                         page('<div class="lot-card">Lot 1: Missing bid</div>'), page(lot(1, title=''))]:
            with self.subTest(body=response.text):
                self.failed_pipeline([response], 'Page 1')

    def test_unparseable_lot_among_valid_lots_fails(self):
        self.failed_pipeline([page(lot(1), '<div class="lot-card">Lot 2: No bid</div>')],
                             'unparseable lot IDs: 2')

    def test_repeated_page_cannot_publish_partial_catalog(self):
        self.failed_pipeline([page(lot(1)), page(lot(1))], 'adds no new lots')

    def test_empty_export_preserves_manifest(self):
        with self.assertRaisesRegex(scraper.IngestionError, 'No lot data'):
            scraper.export_to_manifest([])
        self.assert_originals_unchanged()

    def test_staging_write_failure_preserves_outputs(self):
        with patch.object(scraper.csv.DictWriter, 'writerows', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(scraper.IngestionError, 'Could not publish'):
                scraper.export_to_manifest([{'lot': '1', 'title': 'Fan', 'bid': '2', 'projected_sale': '0'}])
        self.assert_originals_unchanged()

    def test_atomic_replace_failure_stops_pipeline(self):
        self.http.side_effect = [page(lot(i)) for i in range(1, 19)]
        with patch.object(scraper.os, 'replace', side_effect=OSError('replace denied')), \
             patch.object(pipeline, 'estimate_market_value') as price, \
             patch.object(pipeline, 'LotItem') as valuation:
            with self.assertRaisesRegex(scraper.IngestionError, 'Could not publish'):
                pipeline.main()
            price.assert_not_called()
            valuation.assert_not_called()
        self.assert_originals_unchanged()

    def test_transient_request_failure_recovers(self):
        self.http.side_effect = [requests.Timeout('fixture'), page(lot(1))]
        rows = scraper.fetch_crowe_catalog(total_pages=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.http.call_count, 2)

    def test_successful_pipeline_retains_pricing_and_export_contract(self):
        self.http.side_effect = [page(lot(i)) for i in range(1, 19)]
        comp = {'ebay_title': 'Fan', 'ebay_price': 100, 'item_url': 'https://example.invalid/1', 'image_url': ''}
        with patch.object(pipeline, 'estimate_market_value', return_value=(100, [comp])) as price:
            pipeline.main()
        self.assertEqual(price.call_count, 18)
        with open('profitable_lots.csv', newline='') as f:
            reader = csv.DictReader(f)
            winners = list(reader)
            self.assertEqual(reader.fieldnames, ['lot','title','current_bid','max_allowable_bid','projected_sale','net_profit','margin'])
        self.assertEqual(len(winners), 18)
        self.assertEqual(winners[0]['max_allowable_bid'], '45.19')
        with open('comp_audit.csv', newline='') as f:
            reader = csv.DictReader(f)
            self.assertEqual(len(list(reader)), 18)
            self.assertEqual(reader.fieldnames, ['crowe_lot','crowe_title','comp_rank','ebay_title','ebay_price','item_url','image_url'])
        self.assertEqual(Path('data/audit_decisions.jsonl').read_bytes(), self.originals['data/audit_decisions.jsonl'])


if __name__ == '__main__':
    unittest.main()
