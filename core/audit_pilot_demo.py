"""Explicit offline demo only. This module never opens a database or real transport."""
import copy
import json
from pathlib import Path

import requests

from core.audit_evidence import fetch_ebay_candidates
from crowe_source_parser import parse_catalog, parse_lot_detail

FIXTURES = Path(__file__).resolve().parents[1] / "tests/fixtures/crowe"
CATALOG_URL = "https://bids.crauctions.com/auctions/48980?page=1&items=50"
ARGS = {"filter": {"auction_id": "48980", "auction_lot_status": [200, 300], "is_visible": True,
                   "limit_visibility_by_pick_up_locs": True},
        "order": [{"column": "lot_number", "direction": "asc"}],
        "pagination": {"page": 1, "pageSize": 50}, "search": {"text": ""}}


def source():
    catalog = parse_catalog((FIXTURES / "historical_catalog.html").read_text(),
                            source_url=CATALOG_URL, auction_id="48980", query_arguments=ARGS)
    detail = parse_lot_detail((FIXTURES / "historical_detail.html").read_text(),
                              source_url="https://bids.crauctions.com/auctions/48980/lot/8078618", lot_id="8078618")
    other = copy.deepcopy(catalog["lots"][0])
    other.update(lot_id="8078619", lot_number="8001", source_record_key="AuctionLot.8078619",
                 title="DEMO — second lot with missing evidence", description_plain=None, description_html=None,
                 images=None, primary_image=None, attributes=None)
    other["raw_fields"].update(auction_lot_id="8078619", lot_number="8001", title=other["title"])
    catalog["lots"].append(other)
    catalog["pagination"]["returned_count"] = 2
    return {"catalog": catalog, "detail": detail,
            "retrieved_at": {"catalog": "2026-10-29T12:00:00Z", "detail": "2026-10-29T12:01:00Z"}}


def search(auction_id, lot_id, query, limit=20, outcome="READY"):
    items = [{"itemId": "demo|listing-A|0", "itemWebUrl": "https://www.ebay.com/itm/demo-A",
              "title": "DEMO — framed floral canvas, blue and white, 12 × 16 inches",
              "image": {"imageUrl": "https://example.invalid/demo-A.png"}, "condition": "Used",
              "price": {"value": "10.00", "currency": "USD"},
              "shippingOptions": [{"shippingCost": {"value": "3.25", "currency": "USD"}}]},
             {"itemId": "demo|listing-B|0", "itemWebUrl": "https://www.ebay.com/itm/demo-B",
              "title": "DEMO — alternate floral print; dimensions need review", "condition": "New",
              "price": {"value": "8.00", "currency": "USD"}}][:limit]

    def get(url, *, params, **kwargs):
        response = requests.Response()
        response.url = requests.Request("GET", url, params=params).prepare().url
        response.status_code = 503 if outcome == "ERROR" else 200
        response.headers["Content-Type"] = "application/json"
        response._content = json.dumps({"total": len(items) if outcome == "READY" else 0,
                                        "itemSummaries": items if outcome == "READY" else []}).encode()
        response._content_consumed = True
        return response

    return fetch_ebay_candidates(auction_id=auction_id, lot_id=lot_id, query=query, limit=limit,
                                 filters="buyingOptions:{FIXED_PRICE}", sort="price",
                                 http_get=get, token_provider=lambda: "offline-demo-only")
