"""
Risk Engine - V4 Valuation & Safety Flag Processor
Calculates target bids and decorates metrics with audit verification flags.
"""

from typing import Any, Dict, List, Optional
from core.audit_logger import get_verified_lots, is_lot_verified


def calculate_max_hammer_bid(
    floor_price: float, margin: float = 0.35, buyer_premium: float = 0.22
) -> float:
    """V4 Standard Max Hammer Bid Calculation.

    Net estimated resale = floor_price * 0.87 - 5.00
    Max Hammer Bid = Net * (1 - margin) / (1 + buyer_premium)
    """
    if floor_price <= 0:
        return 0.0

    estimated_net = (floor_price * 0.87) - 5.00
    if estimated_net <= 0:
        return 0.0

    max_bid = (estimated_net * (1.0 - margin)) / (1.0 + buyer_premium)
    return round(max(0.0, max_bid), 2)


def evaluate_lot_risk(
    lot_data: Dict[str, Any], verified_lots_set: Optional[set] = None
) -> Dict[str, Any]:
    """Evaluates pricing for a lot record and attaches 'is_verified' and formatted bid outputs.

    Args:
        lot_data: Dict containing lot fields (e.g. 'lot_id', 'floor_price').
        verified_lots_set: Optional pre-loaded set of accepted lot IDs for fast batch lookup.

    Returns:
        Dict updated with 'is_verified', 'max_hammer_bid', and 'target_bid_display'.
    """
    result = dict(lot_data)
    lot_id = str(
        result.get("lot_id")
        or result.get("crowe_lot")
        or result.get("lot")
        or ""
    )
    floor_price = float(
        result.get("floor_price")
        or result.get("revised_floor")
        or result.get("market_floor")
        or 0.0
    )

    # Determine verification status
    if verified_lots_set is not None:
        is_verified = lot_id in verified_lots_set
    else:
        is_verified = is_lot_verified(lot_id) if lot_id else False

    max_bid = calculate_max_hammer_bid(floor_price)

    # Attach safety flag string
    bid_display = f"${max_bid:.2f}"
    if not is_verified:
        bid_display = f"[UNVERIFIED] ${max_bid:.2f}"

    result["is_verified"] = is_verified
    result["max_hammer_bid"] = max_bid
    result["target_bid_display"] = bid_display

    return result


def process_manifest_risk(
    manifest_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Batch processes manifest records, attaching V4 valuation metrics and safety flags."""
    verified_set = get_verified_lots()
    processed = []
    for row in manifest_rows:
        evaluated = evaluate_lot_risk(row, verified_lots_set=verified_set)
        processed.append(evaluated)
    return processed