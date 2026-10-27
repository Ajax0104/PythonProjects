"""Backtest Engine - Phase 3 Replay & Performance Validation

Replays historical auction outcomes against V4 risk engine calculations
and logged audit decisions to evaluate valuation accuracy, margin deltas,
and capital safety metrics.
"""

from dataclasses import asdict, dataclass
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root directory is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.risk_engine import calculate_max_hammer_bid
import pandas as pd

DEFAULT_HISTORICAL_FILE = os.path.join(
    "data", "historical_reconciliations.jsonl"
)
DEFAULT_AUDIT_LOG_FILE = os.path.join("data", "audit_decisions.jsonl")


@dataclass
class HistoricalRecord:
    auction_id: str
    lot_id: str
    item_title: str
    actual_hammer_price: float
    actual_invoice_total: float
    realized_resale_price: Optional[float] = None
    realized_shipping_cost: Optional[float] = 0.0
    realized_net_profit: Optional[float] = None


def generate_sample_historical_data(
    filepath: str = DEFAULT_HISTORICAL_FILE,
) -> None:
    """Generates sample historical reconciliation data if no dataset exists."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    sample_records = [
        {
            "auction_id": "CROWE-2026-10-26",
            "lot_id": "8000",
            "item_title": "Blue and White Flower Canvas Wall Art 12x16",
            "actual_hammer_price": 2.00,
            "actual_invoice_total": 2.44,
            "realized_resale_price": 10.50,
            "realized_shipping_cost": 0.00,
            "realized_net_profit": 10.50 * 0.87 - 5.00 - 2.44,  # $1.70
        },
        {
            "auction_id": "CROWE-2026-10-26",
            "lot_id": "8001",
            "item_title": "Panasonic WhisperCeiling Exhaust Fan",
            "actual_hammer_price": 45.00,
            "actual_invoice_total": 54.90,
            "realized_resale_price": 135.00,
            "realized_shipping_cost": 0.00,
            "realized_net_profit": 135.00 * 0.87 - 5.00 - 54.90,  # $57.55
        },
        {
            "auction_id": "CROWE-2026-10-26",
            "lot_id": "8002",
            "item_title": "Overpriced Decorative Mirror",
            "actual_hammer_price": 30.00,
            "actual_invoice_total": 36.60,
            "realized_resale_price": 25.00,
            "realized_shipping_cost": 0.00,
            "realized_net_profit": 25.00 * 0.87 - 5.00 - 36.60,  # -$19.85
        },
    ]

    with open(filepath, "w", encoding="utf-8") as f:
        for rec in sample_records:
            f.write(json.dumps(rec) + "\n")


def load_accepted_floor_prices(
    audit_log_file: str = DEFAULT_AUDIT_LOG_FILE,
) -> Dict[str, float]:
    """Extracts the lowest ACCEPTED comp listed_price per lot_id from audit log."""
    accepted_floors: Dict[str, float] = {}

    if not os.path.exists(audit_log_file):
        return accepted_floors

    try:
        with open(audit_log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("decision") == "ACCEPT":
                    lot_id = str(data.get("lot_id"))
                    price = float(data.get("listed_price", 0.0))
                    if price > 0:
                        if (
                            lot_id not in accepted_floors
                            or price < accepted_floors[lot_id]
                        ):
                            accepted_floors[lot_id] = price
    except Exception as e:
        print(f"[BacktestEngine Warning] Failed to read audit decisions: {e}")

    return accepted_floors


def run_backtest(
    historical_file: str = DEFAULT_HISTORICAL_FILE,
    audit_log_file: str = DEFAULT_AUDIT_LOG_FILE,
) -> pd.DataFrame:
    """Executes backtest replay comparing V4 max bids against historical invoice outcomes.

    Returns:
        pd.DataFrame: Lot-by-lot performance report.
    """
    if not os.path.exists(historical_file):
        print(
            f"[BacktestEngine] Creating initial sample dataset at {historical_file}..."
        )
        generate_sample_historical_data(historical_file)

    # 1. Load data
    accepted_floors = load_accepted_floor_prices(audit_log_file)

    records: List[Dict[str, Any]] = []
    with open(historical_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print("[BacktestEngine Error] Historical dataset is empty.")
        return pd.DataFrame()

    results: List[Dict[str, Any]] = []

    # Summary aggregators
    accurate_valuations = 0
    margin_deltas: List[float] = []
    safe_skips_count = 0
    profitable_wins_count = 0

    for rec in records:
        lot_id = str(rec.get("lot_id"))
        title = rec.get("item_title", "Unknown")
        hammer = float(rec.get("actual_hammer_price", 0.0))
        invoice = float(rec.get("actual_invoice_total", hammer * 1.22))

        realized_resale = rec.get("realized_resale_price")
        if realized_resale is not None:
            realized_resale = float(realized_resale)

        realized_profit = rec.get("realized_net_profit")
        if realized_profit is None and realized_resale is not None:
            realized_profit = (realized_resale * 0.87) - 5.00 - invoice
        elif realized_profit is not None:
            realized_profit = float(realized_profit)

        # 2. Determine V4 Underwriting Floor & Max Bid
        # Use audited floor if available; fall back to realized resale or actual hammer baseline
        v4_floor = accepted_floors.get(
            lot_id, realized_resale if realized_resale else hammer * 2.5
        )
        v4_max_bid = calculate_max_hammer_bid(v4_floor)

        # 3. Projected Net Profit at Max Bid
        projected_net = (v4_floor * 0.87) - 5.00 - (v4_max_bid * 1.22)

        # 4. Performance Logic
        would_win = v4_max_bid >= hammer
        is_safe_skip = v4_max_bid < hammer

        # Check accuracy: realized resale within ±10% of V4 floor comp
        is_accurate = False
        if realized_resale and v4_floor > 0:
            variance = abs(realized_resale - v4_floor) / v4_floor
            if variance <= 0.10:
                is_accurate = True
                accurate_valuations += 1

        # Margin delta calculation
        if realized_profit is not None:
            delta = projected_net - realized_profit
            margin_deltas.append(delta)

        if is_safe_skip:
            safe_skips_count += 1

        if would_win and (realized_profit or 0.0) > 0:
            profitable_wins_count += 1

        results.append(
            {
                "lot_id": lot_id,
                "title": title[:30] + "..." if len(title) > 30 else title,
                "v4_floor": round(v4_floor, 2),
                "v4_max_bid": v4_max_bid,
                "actual_hammer": hammer,
                "actual_invoice": round(invoice, 2),
                "realized_resale": round(realized_resale, 2)
                if realized_resale
                else None,
                "realized_profit": round(realized_profit, 2)
                if realized_profit is not None
                else None,
                "would_win": would_win,
                "is_safe_skip": is_safe_skip,
                "valuation_accurate": is_accurate,
            }
        )

    results_df = pd.DataFrame(results)
    total_lots = len(results_df)

    accuracy_pct = (
        (accurate_valuations / total_lots) * 100.0 if total_lots > 0 else 0.0
    )
    avg_margin_delta = (
        sum(margin_deltas) / len(margin_deltas) if margin_deltas else 0.0
    )

    # 5. Executive Summary Printout
    print("\n" + "=" * 65)
    print(" 📊 PHASE 3: UNDERWRITING BACKTEST & REPLAY REPORT")
    print("=" * 65)
    print(f" Total Lots Analyzed        : {total_lots}")
    print(f" Valuation Accuracy (±10%)  : {accuracy_pct:.1f}%")
    print(f" Avg Underwriting Margin Δ  : ${avg_margin_delta:+.2f}")
    print(f" Safe Capital Skips Count   : {safe_skips_count}")
    print(f" Profitable Wins Count      : {profitable_wins_count}")
    print("=" * 65 + "\n")

    return results_df


if __name__ == "__main__":
    df = run_backtest()
    print(df.to_string(index=False))