"""Structural fixture tests. No HTTP clients or network access are required."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from crowe_source_parser import (
    SourceParseError, extract_apollo_state, parse_catalog, parse_lot_detail,
)

FIXTURES = Path(__file__).parent / 'fixtures' / 'crowe'


def html(state):
    return '<script>window.__APOLLO_STATE__ = ' + json.dumps(state) + ';</script>'


class CroweParserTests(unittest.TestCase):
    def catalog_context(self, name='historical'):
        text = (FIXTURES / f'{name}_catalog.html').read_text()
        state = extract_apollo_state(text)
        aid = '48980' if name == 'historical' else '49187'
        auction = state['Auction.' + aid]
        query = next(k for k in auction if k.startswith('lots('))
        args = json.loads(query[5:-1])
        return state, aid, query, args

    def catalog(self, state, aid, args):
        return parse_catalog(html(state), source_url='https://bids.crauctions.com/fixture',
                             auction_id=aid, query_arguments=args)

    def detail_context(self, name='historical'):
        state = extract_apollo_state((FIXTURES / f'{name}_detail.html').read_text())
        lid = '8078618' if name == 'historical' else '8127508'
        return state, lid, state['AuctionLot.' + lid]

    def detail(self, state, lid):
        return parse_lot_detail(html(state), source_url='https://bids.crauctions.com/detail-fixture', lot_id=lid)

    def test_historical_and_active_catalogs(self):
        for name, status, total, amount in [('historical', 300, 878, 16), ('active', 200, 827, 8)]:
            with self.subTest(name=name):
                state, aid, query, args = self.catalog_context(name)
                result = self.catalog(state, aid, args)
                self.assertEqual(result['auction']['auction_status'], status)
                self.assertEqual(result['pagination'], {'page': 1, 'pageSize': 50, 'total': total, 'returned_count': 1})
                self.assertEqual(result['source']['query_arguments'], args)
                self.assertEqual(result['source']['query_key'], query)
                self.assertEqual(result['lots'][0]['prices']['winning_bid_amount'], amount)
                self.assertEqual(result['lots'][0]['raw_fields']['auction_lot_status'], 200 if name == 'historical' else 100)
                self.assertIsNone(result['lots'][0]['images'])  # Catalog isn't a full gallery.

    def test_both_detail_states_and_nested_auction(self):
        for name, count in [('historical', 5), ('active', 2)]:
            state, lid, record = self.detail_context(name)
            # A partial unrelated cache entry must not overwrite the nested auction.
            state['Auction.' + record['auction_id']] = {'auction_id': record['auction_id']}
            result = self.detail(state, lid)
            self.assertEqual(result['auction']['auction_status'], 300 if name == 'historical' else 200)
            self.assertEqual(len(result['lots'][0]['images']), count)
            self.assertEqual(result['lots'][0]['lot_id'], lid)
            self.assertEqual(result['lots'][0]['timestamps']['end_time'], record['end_time'])

    def test_exact_query_selection_ignores_mixed_cache_and_other_pages(self):
        state, aid, query, args = self.catalog_context()
        other = copy.deepcopy(args)
        other['pagination']['page'] = 2
        state['Auction.' + aid]['lots(' + json.dumps(other) + ')'] = {'total': 878, 'lots': [{'__ref': 'AuctionLot.unrelated'}]}
        state['AuctionLot.unrelated'] = {'auction_id': 'different', 'description': {'__ref': 'missing'}}
        result = self.catalog(state, aid, dict(reversed(list(args.items()))))
        self.assertEqual([r['lot_id'] for r in result['lots']], ['8078618'])
        bad = copy.deepcopy(args)
        bad['filter']['is_visible'] = False
        with self.assertRaisesRegex(SourceParseError, 'matching lots'):
            self.catalog(state, aid, bad)

    def test_descriptions_and_original_fields_are_lossless(self):
        state, lid, record = self.detail_context()
        record['title'] = 'Full title ' * 30
        record['description'] = '<p>Full &amp; untruncated \u2603 ' + 'text ' * 100 + '</p>'
        record['description_plain'] = 'Distinct supplied plain text'
        lot = self.detail(state, lid)['lots'][0]
        self.assertEqual(lot['title'], record['title'])
        self.assertEqual(lot['description_html'], record['description'])
        self.assertEqual(lot['description_plain'], record['description_plain'])
        self.assertEqual(lot['raw_fields']['description'], record['description'])
        self.assertEqual(lot['source_url'], record['public_url'])
        self.assertEqual(lot['source_record_key'], 'AuctionLot.' + lid)

    def test_price_components_remain_separate_and_uninterpreted(self):
        state, aid, query, args = self.catalog_context()
        prices = self.catalog(state, aid, args)['lots'][0]['prices']
        self.assertEqual(prices['winning_bid_amount'], 16)
        self.assertEqual(prices['bid_with_premium']['premium'], 3.2)
        self.assertEqual(prices['bid_with_premium']['total'], 19.2)
        self.assertIsNone(prices['price'])
        self.assertNotIn('premium_rate', prices)

    def test_missing_identifiers_are_unknown_not_extracted_from_description(self):
        state, lid, record = self.detail_context()
        record['description'] = '<p>Brand: Example Model: XYZ UPC: 000123</p>'
        record['upc'] = None
        lot = self.detail(state, lid)['lots'][0]
        self.assertTrue(all(value is None for value in lot['identifiers'].values()))
        self.assertIn('upc', lot['raw_fields'])
        self.assertNotIn('model', lot['raw_fields'])
        self.assertIsNone(lot['attributes'][0]['data'])
        record['upc'] = '000123'
        self.assertEqual(self.detail(state, lid)['lots'][0]['identifiers']['upc'], '000123')

    def test_gallery_order_metadata_and_references(self):
        state, lid, record = self.detail_context()
        expected = copy.deepcopy(record['images'])
        expected[0]['asset_metadata']['alt'] = 'Synthetic caption'
        state['Attachment.first'] = expected[0]
        record['images'][0] = {'__ref': 'Attachment.first'}
        result = self.detail(state, lid)['lots'][0]
        self.assertEqual(result['images'], expected)
        self.assertEqual([i['attachment_id'] for i in result['images']], ['26315457','26315458','26315459','26315460','26315461'])
        self.assertEqual(result['image_provenance'], 'unknown')

    def test_nested_auction_reference(self):
        state, lid, record = self.detail_context()
        aid = record['auction_id']
        state['Auction.' + aid] = record['auction']
        record['auction'] = {'__ref': 'Auction.' + aid}
        self.assertEqual(self.detail(state, lid)['auction']['auction_id'], aid)

    def test_absent_malformed_or_executable_state(self):
        cases = ['<p>No state</p>', '<script>window.__APOLLO_STATE__ = nope;</script>',
                 '<script>window.__APOLLO_STATE__ = {"ROOT_QUERY":{}}; alert(1)</script>',
                 '<script>window.__APOLLO_STATE__ = JSON.parse("{}");</script>',
                 '<script>window.__APOLLO_STATE__ = {"ROOT_QUERY":{},"ROOT_QUERY":{}};</script>',
                 '<script>window.__APOLLO_STATE__ = {"ROOT_QUERY":{},"x":NaN};</script>',
                 html({'ROOT_QUERY': []}), html({}), html({'ROOT_QUERY': {}}) * 2]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(SourceParseError):
                extract_apollo_state(text)

    def test_dangling_reference_and_missing_queries(self):
        state, aid, query, args = self.catalog_context()
        del state['AuctionLot.8078618']
        with self.assertRaisesRegex(SourceParseError, 'Dangling'):
            self.catalog(state, aid, args)
        state, lid, record = self.detail_context()
        state['ROOT_QUERY'] = {}
        with self.assertRaisesRegex(SourceParseError, 'matching lot'):
            self.detail(state, lid)

    def test_cyclic_image_reference(self):
        state, lid, record = self.detail_context()
        state['Attachment.a'] = {'__ref': 'Attachment.b'}
        state['Attachment.b'] = {'__ref': 'Attachment.a'}
        record['images'] = [{'__ref': 'Attachment.a'}]
        with self.assertRaisesRegex(SourceParseError, 'Cyclic'):
            self.detail(state, lid)

    def test_identity_mismatches(self):
        for field in ['auction_id', 'auction_lot_id']:
            state, aid, query, args = self.catalog_context()
            state['AuctionLot.8078618'][field] = 'wrong'
            with self.subTest(field=field), self.assertRaisesRegex(SourceParseError, 'identity mismatch'):
                self.catalog(state, aid, args)
        state, lid, record = self.detail_context()
        record['auction']['auction_id'] = 'wrong'
        with self.assertRaisesRegex(SourceParseError, 'identity mismatch'):
            self.detail(state, lid)

    def test_mandatory_fields_and_gallery_shape(self):
        for field, value in [('title', None), ('lot_number', None), ('auction', None), ('images', None),
                             ('images', [{'attachment_id': None}]), ('description', 123)]:
            state, lid, record = self.detail_context()
            record[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(SourceParseError):
                self.detail(state, lid)

    def test_pagination_contradictions_and_duplicates(self):
        for change in ['negative', 'missing', 'duplicate', 'too_many']:
            state, aid, query, args = self.catalog_context()
            result = state['Auction.' + aid][query]
            if change == 'negative': result['total'] = -1
            if change == 'missing': del result['total']
            if change == 'duplicate': result['lots'] *= 2
            if change == 'too_many': result['total'] = 0
            with self.subTest(change=change), self.assertRaises(SourceParseError):
                self.catalog(state, aid, args)

    def test_ambiguous_semantically_identical_queries(self):
        state, aid, query, args = self.catalog_context()
        state['Auction.' + aid]['lots(' + json.dumps(args, indent=1) + ')'] = state['Auction.' + aid][query]
        with self.assertRaisesRegex(SourceParseError, 'found 2'):
            self.catalog(state, aid, args)

    def test_query_boolean_is_not_numeric_one(self):
        state, aid, query, args = self.catalog_context()
        malformed_args = copy.deepcopy(args)
        malformed_args['pagination']['page'] = True
        state['Auction.' + aid]['lots(' + json.dumps(malformed_args) + ')'] = state['Auction.' + aid].pop(query)
        with self.assertRaisesRegex(SourceParseError, 'matching lots'):
            self.catalog(state, aid, args)

    def test_missing_attributes_and_invalid_attribute_shape(self):
        state, lid, record = self.detail_context()
        del record['dynamic_fields']
        self.assertIsNone(self.detail(state, lid)['lots'][0]['attributes'])
        record['dynamic_fields'] = None
        self.assertIsNone(self.detail(state, lid)['lots'][0]['attributes'])
        record['dynamic_fields'] = 'unsupported'
        with self.assertRaisesRegex(SourceParseError, 'dynamic_fields'):
            self.detail(state, lid)

    def test_zero_total_is_metadata_not_rendered_text(self):
        state, aid, query, args = self.catalog_context()
        state['Auction.' + aid][query] = {'total': 0, 'lots': []}
        result = self.catalog(state, aid, args)
        self.assertEqual(result['pagination']['total'], 0)
        self.assertEqual(result['lots'], [])

    def test_offline_and_input_not_mutated(self):
        state, aid, query, args = self.catalog_context()
        before = copy.deepcopy(args)
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            self.catalog(state, aid, args)
        self.assertEqual(args, before)

    def test_fixtures_contain_no_sensitive_cache_fields(self):
        prohibited = {'winning_bidder','basic_consignor','my_max_bid','my_max_proxy','authorization','cookie','token','session'}
        def check(value):
            if isinstance(value, dict):
                self.assertFalse(prohibited.intersection(k.lower() for k in value))
                for item in value.values(): check(item)
            elif isinstance(value, list):
                for item in value: check(item)
        for path in FIXTURES.glob('*.html'):
            check(extract_apollo_state(path.read_text()))


if __name__ == '__main__':
    unittest.main()
