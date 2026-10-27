"""Audit Logger Module - Phase 1 Persistence Layer

Logs user review decisions (ACCEPT, REJECT, UNSURE) to a persistent JSON Lines
file.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import os
from typing import Optional, Set

LOG_FILE_PATH = os.path.join("data", "audit_decisions.jsonl")


class Decision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    UNSURE = "UNSURE"


class RejectionReason(str, Enum):
    WRONG_CATEGORY = "WRONG_CATEGORY"
    ACCESSORY_ONLY = "ACCESSORY_ONLY"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    CONDITION_DIFFERENCE = "CONDITION_DIFFERENCE"
    OTHER = "OTHER"


@dataclass
class AuditEvent:
    lot_id: str
    ebay_item_id: str
    query_string: str
    decision: str
    listed_price: float
    rejection_reason: Optional[str] = None
    timestamp: Optional[str] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def log_decision(
    lot_id: str,
    ebay_item_id: str,
    query_string: str,
    decision: str,
    rejection_reason: Optional[str] = None,
    listed_price: float = 0.0,
    timestamp: Optional[str] = None,
) -> bool:
    """Logs a review decision to data/audit_decisions.jsonl."""
    try:
        os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)

        event = AuditEvent(
            lot_id=str(lot_id),
            ebay_item_id=str(ebay_item_id),
            query_string=str(query_string),
            decision=str(decision).upper(),
            rejection_reason=str(rejection_reason)
            if rejection_reason
            else None,
            listed_price=float(listed_price),
            timestamp=timestamp,
        )

        record = asdict(event)

        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        return True
    except Exception as e:
        print(f"[AuditLogger Error] Failed to log decision: {e}")
        return False


def get_verified_lots() -> Set[str]:
    """Reads data/audit_decisions.jsonl and returns lot_ids that have an ACCEPT decision."""
    verified_lots: Set[str] = set()
    if not os.path.exists(LOG_FILE_PATH):
        return verified_lots

    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("decision") == Decision.ACCEPT.value:
                    verified_lots.add(str(data.get("lot_id")))
    except Exception as e:
        print(f"[AuditLogger Error] Failed to read audit decisions: {e}")

    return verified_lots


def is_lot_verified(lot_id: str) -> bool:
    """Checks if a specific lot_id has received an ACCEPT decision."""
    return str(lot_id) in get_verified_lots()