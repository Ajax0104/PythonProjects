"""Offline adapter verification using the existing sanitized parser fixtures."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
from requests.structures import CaseInsensitiveDict

from crowe_acquisition import AcquisitionError, MAX_RESPONSE_BYTES, TIMEOUT, acquire_catalog_page
from crowe_source_parser import SourceParseError, extract_apollo_state, parse_catalog, parse_lot_detail

FIXTURES = Path(__file__).parent / 'fixtures' / 'crowe'
CATALOG_URL = 'https://bids.crauctions.com/auctions/48980-amazon-semi-load-auction-8166?page=1&items=50'
DETAIL_URL = 'https://bids.crauctions.com/auctions/48980/lot/8078618-blue-and-white-flower-canvas-wall-art-12x16'


def response(text, url=CATALOG_URL, status=200, content_type='text/html; charset=utf-8'):
    r = Mock(spec=requests.Response)
    r.status_code = status
    r.url = url
    r.history = []
    r.headers = CaseInsensitiveDict({'Content-Type': content_type})
    data = text.encode('utf-8') if isinstance(text, str) else text
    r.iter_content.return_value = iter([data])
    return r


def encode(state):
    return '<script>window.__APOLLO_STATE__ = ' + json.dumps(state) + ';</script>'


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.catalog_html = (FIXTURES / 'historical_catalog.html').read_text()
        self.detail_html = (FIXTURES / 'historical_detail.html').read_text()
        self.state = extract_apollo_state(self.catalog_html)
        query = next(k for k in self.state['Auction.48980'] if k.startswith('lots('))
        self.args = json.loads(query[5:-1])
        # Prevent any accidental real socket even if adapter injection regresses.
        no_network = patch('socket.socket', side_effect=AssertionError('Network forbidden'))
        no_network.start()
        self.addCleanup(no_network.stop)

    def acquire(self, get, **kwargs):
        return acquire_catalog_page(CATALOG_URL, auction_id='48980', query_arguments=self.args,
                                    http_get=get, **kwargs)

    def test_catalog_preserves_entire_parser_result_and_request_url(self):
        r = response(self.catalog_html)
        get = Mock(return_value=r)
        before = copy.deepcopy(self.args)
        actual = self.acquire(get)
        expected = parse_catalog(self.catalog_html, source_url=CATALOG_URL, auction_id='48980', query_arguments=self.args)
        self.assertEqual(actual, {'catalog': expected, 'detail': None})
        self.assertEqual(self.args, before)
        get.assert_called_once_with(CATALOG_URL, timeout=TIMEOUT, allow_redirects=False, stream=True, verify=True)
        r.close.assert_called_once()

    def test_optional_detail_preserves_gallery_and_prices(self):
        catalog = response(self.catalog_html)
        detail = response(self.detail_html, DETAIL_URL)
        get = Mock(side_effect=[catalog, detail])
        result = self.acquire(get, detail_url=DETAIL_URL, lot_id='8078618')
        self.assertEqual(result['detail'], parse_lot_detail(self.detail_html, source_url=DETAIL_URL, lot_id='8078618'))
        self.assertEqual(result['catalog']['lots'][0]['lot_id'], result['detail']['lots'][0]['lot_id'])
        self.assertEqual(result['detail']['source']['url'], DETAIL_URL)
        self.assertEqual(len(result['detail']['lots'][0]['images']), 5)
        self.assertEqual(result['catalog']['lots'][0]['prices']['winning_bid_amount'], 16)
        self.assertIsNone(result['detail']['lots'][0]['prices']['bid_with_premium'])
        self.assertEqual(get.call_count, 2)
        self.assertEqual([call.args[0] for call in get.call_args_list], [CATALOG_URL, DETAIL_URL])
        catalog.close.assert_called_once()
        detail.close.assert_called_once()

    def test_active_catalog_and_detail(self):
        aid, lid = '49187', '8127508'
        catalog = (FIXTURES / 'active_catalog.html').read_text()
        detail = (FIXTURES / 'active_detail.html').read_text()
        state = extract_apollo_state(catalog)
        query = next(k for k in state['Auction.' + aid] if k.startswith('lots('))
        cu = 'https://bids.crauctions.com/auctions/49187-amazon-semi-load-auction-8533'
        du = 'https://bids.crauctions.com/auctions/49187/lot/8127508-box-of-white-premium-2-ply-paper-towels-70-sheets'
        get = Mock(side_effect=[response(catalog, cu), response(detail, du)])
        result = acquire_catalog_page(cu, auction_id=aid, query_arguments=json.loads(query[5:-1]), detail_url=du, lot_id=lid, http_get=get)
        self.assertEqual(result['catalog']['pagination']['total'], 827)
        self.assertEqual(result['catalog']['source']['query_arguments']['filter']['end_time_from'], 'now')
        self.assertEqual(result['detail']['auction']['auction_status'], 200)
        self.assertEqual(len(result['detail']['lots'][0]['images']), 2)

    def test_unapproved_urls_rejected_before_transport(self):
        urls = [
            'http://bids.crauctions.com/auctions/48980',
            'https://example.com/auctions/48980',
            'https://bids.crauctions.com.evil.invalid/auctions/48980',
            'https://sub.bids.crauctions.com/auctions/48980',
            'https://bids.crauctions.com./auctions/48980',
            'https://user:password@bids.crauctions.com/auctions/48980',
            'https://bids.crauctions.com@evil.invalid/auctions/48980',
            'https://bids.crauctions.com:444/auctions/48980',
            'https://bids.crauctions.com:bad/auctions/48980',
            'https://bids.crauctions.com/auctions/48980#fragment',
            'https://bids.crauctions.com/asset/image/26315457/thumb',
            'https://bids.crauctions.com/auctions/99999',
            'https://bids.crauctions.com/auctions/48980\n',
            'https://bids.crauctions.com\\@evil.invalid/auctions/48980',
            'file:///auctions/48980', '', None,
        ]
        for url in urls:
            get = Mock()
            with self.subTest(url=url), self.assertRaises(AcquisitionError):
                acquire_catalog_page(url, auction_id='48980', query_arguments=self.args, http_get=get)
            get.assert_not_called()

    def test_invalid_detail_selection_is_preflighted(self):
        options = [{'detail_url': DETAIL_URL}, {'lot_id': '8078618'},
                   {'detail_url': 'https://evil.invalid/lot/8078618', 'lot_id': '8078618'},
                   {'detail_url': DETAIL_URL, 'lot_id': 'wrong'},
                   {'detail_url': DETAIL_URL, 'lot_id': '99999'}]
        for option in options:
            get = Mock()
            with self.subTest(option=option), self.assertRaises(AcquisitionError):
                self.acquire(get, **option)
            get.assert_not_called()

    def test_cross_host_and_same_host_redirects_rejected(self):
        for destination in ['https://evil.invalid/x', DETAIL_URL]:
            r = response('', status=302)
            r.headers['Location'] = destination
            get = Mock(return_value=r)
            with self.assertRaisesRegex(AcquisitionError, 'HTTP 200'):
                self.acquire(get)
            get.assert_called_once()
            r.close.assert_called_once()
            r.iter_content.assert_not_called()

    def test_transport_that_already_redirected_is_rejected(self):
        for url, history in [('https://evil.invalid/x', []), (CATALOG_URL, [object()])]:
            r = response(self.catalog_html, url)
            r.history = history
            with self.assertRaisesRegex(AcquisitionError, 'redirected'):
                self.acquire(Mock(return_value=r))
            r.close.assert_called_once()

    def test_http_failures_are_not_retried(self):
        for status in [204, 206, 301, 403, 404, 429, 500]:
            r = response('', status=status)
            get = Mock(return_value=r)
            with self.subTest(status=status), self.assertRaises(AcquisitionError):
                self.acquire(get)
            get.assert_called_once()
            r.close.assert_called_once()

    def test_transport_timeouts_and_errors_preserve_cause(self):
        for error in [requests.ConnectTimeout('fixture'), requests.ReadTimeout('fixture'), requests.ConnectionError('fixture'), requests.exceptions.SSLError('fixture')]:
            get = Mock(side_effect=error)
            with self.assertRaises(AcquisitionError) as raised:
                self.acquire(get)
            self.assertIs(raised.exception.__cause__, error)
            get.assert_called_once()

    def test_stream_failure_closes_response(self):
        r = response('')
        def chunks():
            yield b'<html>'
            raise requests.ReadTimeout('fixture')
        r.iter_content.return_value = chunks()
        with self.assertRaises(AcquisitionError):
            self.acquire(Mock(return_value=r))
        r.close.assert_called_once()

    def test_content_type_validation(self):
        for content_type in ['', 'application/json', 'image/jpeg', 'text/plain']:
            r = response(self.catalog_html, content_type=content_type)
            with self.subTest(content_type=content_type), self.assertRaisesRegex(AcquisitionError, 'Content-Type'):
                self.acquire(Mock(return_value=r))
            r.iter_content.assert_not_called()
            r.close.assert_called_once()
        self.acquire(Mock(return_value=response(self.catalog_html, content_type='application/xhtml+xml; charset=UTF-8')))

    def test_declared_and_streamed_size_limits(self):
        r = response('')
        r.headers['Content-Length'] = str(MAX_RESPONSE_BYTES + 1)
        with self.assertRaisesRegex(AcquisitionError, 'size limit'):
            self.acquire(Mock(return_value=r))
        r.iter_content.assert_not_called()
        r.close.assert_called_once()
        oversized_header = response('')
        oversized_header.headers['Content-Length'] = '9' * 5000
        with self.assertRaisesRegex(AcquisitionError, 'size limit'):
            self.acquire(Mock(return_value=oversized_header))
        for declared in [None, '1']:
            r = response('')
            if declared: r.headers['Content-Length'] = declared
            r.iter_content.return_value = iter([b'x' * 65536] * (MAX_RESPONSE_BYTES // 65536 + 1))
            with self.assertRaisesRegex(AcquisitionError, 'size limit'):
                self.acquire(Mock(return_value=r))
            r.close.assert_called_once()

    def test_malformed_length_and_encoding(self):
        for length in ['-1', 'abc', '1,2']:
            r = response('')
            r.headers['Content-Length'] = length
            with self.assertRaisesRegex(AcquisitionError, 'Content-Length'):
                self.acquire(Mock(return_value=r))
        for body, content_type in [(b'\xff', 'text/html; charset=utf-8'), (b'hello', 'text/html; charset=unknown-codec')]:
            with self.assertRaisesRegex(AcquisitionError, 'encoding'):
                self.acquire(Mock(return_value=response(body, content_type=content_type)))

    def test_missing_or_malformed_apollo_never_fetches_detail(self):
        for text in ['<html>Login</html>', '<script>window.__APOLLO_STATE__ = bad;</script>']:
            get = Mock(return_value=response(text))
            with self.assertRaises(SourceParseError):
                self.acquire(get, detail_url=DETAIL_URL, lot_id='8078618')
            get.assert_called_once()

    def test_parser_exception_propagates_unchanged(self):
        error = SourceParseError('specific failure')
        r = response(self.catalog_html)
        with patch('crowe_acquisition.parse_catalog', side_effect=error):
            with self.assertRaises(SourceParseError) as raised:
                self.acquire(Mock(return_value=r))
        self.assertIs(raised.exception, error)
        r.close.assert_called_once()

    def test_query_context_not_silently_replaced(self):
        self.args['pagination']['page'] = 2
        with self.assertRaisesRegex(SourceParseError, 'matching lots'):
            self.acquire(Mock(return_value=response(self.catalog_html)))

    def test_conflicting_catalog_identity(self):
        self.state['AuctionLot.8078618']['auction_id'] = '999'
        get = Mock(return_value=response(encode(self.state)))
        with self.assertRaisesRegex(SourceParseError, 'identity mismatch'):
            self.acquire(get, detail_url=DETAIL_URL, lot_id='8078618')
        get.assert_called_once()

    def test_detail_from_different_auction_rejected(self):
        state = extract_apollo_state(self.detail_html)
        state['AuctionLot.8078618']['auction_id'] = '999'
        state['AuctionLot.8078618']['auction']['auction_id'] = '999'
        get = Mock(side_effect=[response(self.catalog_html), response(encode(state), DETAIL_URL)])
        with self.assertRaisesRegex(AcquisitionError, 'identities conflict'):
            self.acquire(get, detail_url=DETAIL_URL, lot_id='8078618')
        self.assertEqual(get.call_count, 2)

    def test_detail_not_in_selected_catalog_page_not_fetched(self):
        get = Mock(return_value=response(self.catalog_html))
        with self.assertRaisesRegex(AcquisitionError, 'not on the selected catalog page'):
            self.acquire(get, detail_url='https://bids.crauctions.com/auctions/48980/lot/999', lot_id='999')
        get.assert_called_once()

    def test_detail_failure_returns_no_partial_result_or_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ['auction_manifest.csv', 'comp_audit.csv', 'profitable_lots.csv', 'audit_decisions.jsonl']]
            before = {p: b'untouched\r\n\x00' for p in paths}
            for p, data in before.items(): p.write_bytes(data)
            for detail in [response('', DETAIL_URL, status=500), response('<html>No state</html>', DETAIL_URL)]:
                get = Mock(side_effect=[response(self.catalog_html), detail])
                with patch('builtins.open', side_effect=AssertionError('Adapter must not open files')):
                    with self.assertRaises((AcquisitionError, SourceParseError)):
                        self.acquire(get, detail_url=DETAIL_URL, lot_id='8078618')
                self.assertEqual({p: p.read_bytes() for p in paths}, before)
                detail.close.assert_called_once()

    def test_default_transport_is_requests_get(self):
        with patch('crowe_acquisition.requests.get', return_value=response(self.catalog_html)) as get:
            acquire_catalog_page(CATALOG_URL, auction_id='48980', query_arguments=self.args)
        get.assert_called_once()

    def test_success_does_not_open_files(self):
        get = Mock(side_effect=[response(self.catalog_html), response(self.detail_html, DETAIL_URL)])
        with patch('builtins.open', side_effect=AssertionError('Adapter must not open files')):
            result = self.acquire(get, detail_url=DETAIL_URL, lot_id='8078618')
        self.assertEqual(result['detail']['lots'][0]['lot_id'], '8078618')

    def test_declared_exact_limit_and_missing_length_are_allowed(self):
        for length in [None, str(MAX_RESPONSE_BYTES)]:
            r = response(self.catalog_html)
            if length is not None:
                r.headers['Content-Length'] = length
            self.assertIsNotNone(self.acquire(Mock(return_value=r))['catalog'])

    def test_wrong_query_auction_prevents_request(self):
        self.args['filter']['auction_id'] = '999'
        get = Mock()
        with self.assertRaisesRegex(AcquisitionError, 'Query context'):
            self.acquire(get)
        get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
