"""Audit UI Component - Phase 2 High-Velocity Review & Decision Capture

Updated with rapid Lot Navigation controls (Next/Prev buttons) and an expanded,
scrollable Lot List queue with live verification indicators.
"""

from datetime import datetime, timezone
import json
import os
import sys

# Ensure project root directory is in sys.path when running from subdirectories
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.audit_logger import get_verified_lots, log_decision
from core.risk_engine import evaluate_lot_risk
import pandas as pd
import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="Auction Underwriting Audit UI",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 High-Velocity Comp Audit & Decision Capture")
st.caption(
    "Review active eBay match candidates, capture audit decisions, tag noisy matches, and track verification status."
)

DATA_FILE = "comp_audit.csv"

if not os.path.exists(DATA_FILE):
    st.error(
        f"❌ '{DATA_FILE}' not found. Run 'python inventory_analyzer4.py' first to generate audit candidates."
    )
    st.stop()

try:
    df = pd.read_csv(DATA_FILE)
except Exception as e:
    st.error(f"❌ Failed to load '{DATA_FILE}': {e}")
    st.stop()

if df.empty:
    st.warning("⚠️ 'comp_audit.csv' is empty.")
    st.stop()

# Ensure required fallback columns exist
if "item_id" not in df.columns:
    df["item_id"] = df.apply(
        lambda r: f"comp_{r.get('crowe_lot', '0')}_{r.get('comp_rank', '0')}",
        axis=1,
    )


def load_audit_decisions():
    """Reads all logged decisions from disk to lock out cards instantly."""
    log_path = os.path.join("data", "audit_decisions.jsonl")
    decisions = {}
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    item_key = str(data.get("ebay_item_id"))
                    decisions[item_key] = {
                        "decision": data.get("decision"),
                        "reason": data.get("rejection_reason"),
                    }
        except Exception:
            pass
    return decisions


audit_decisions = load_audit_decisions()
verified_set = get_verified_lots()

all_lots = [str(l) for l in df["crowe_lot"].unique()]

# Initialize lot queue index in Session State
if "lot_index" not in st.session_state:
    st.session_state.lot_index = 0

# Ensure index stays within bounds
if st.session_state.lot_index >= len(all_lots):
    st.session_state.lot_index = 0
if st.session_state.lot_index < 0:
    st.session_state.lot_index = len(all_lots) - 1

# Format sidebar labels with live verification badges
lot_labels = []
for lot_id in all_lots:
    is_v = str(lot_id) in verified_set
    badge = "🟢" if is_v else "⚠️"
    lot_labels.append(f"{badge} Lot #{lot_id}")

st.sidebar.header("📋 Manifest Queue")
st.sidebar.caption(f"Total Lots: {len(all_lots)}")

# Sidebar Expanded Scrollable Radio List Box
selected_label = st.sidebar.radio(
    "Select Lot to Audit",
    options=lot_labels,
    index=st.session_state.lot_index,
    key="lot_queue_radio",
    label_visibility="collapsed",
)

# Sync sidebar radio pick back to session state index
st.session_state.lot_index = lot_labels.index(selected_label)
selected_lot = all_lots[st.session_state.lot_index]

lot_df = df[df["crowe_lot"].astype(str) == str(selected_lot)].copy()
lot_title = str(lot_df["crowe_title"].iloc[0])

# Attach decision state to dataframe
lot_df["item_id_str"] = lot_df.apply(
    lambda r: str(
        r.get("item_id", f"comp_{selected_lot}_{r.get('comp_rank', '0')}")
    ),
    axis=1,
)
lot_df["logged_decision"] = lot_df["item_id_str"].map(
    lambda x: audit_decisions.get(x, {}).get("decision")
)
lot_df["logged_reason"] = lot_df["item_id_str"].map(
    lambda x: audit_decisions.get(x, {}).get("reason")
)

# Dynamic Valuation Recalculation
accepted_df = lot_df[lot_df["logged_decision"] == "ACCEPT"]
valid_df = lot_df[lot_df["logged_decision"] != "REJECT"]

if not accepted_df.empty:
    floor_price = float(accepted_df["ebay_price"].min())
elif not valid_df.empty:
    floor_price = float(valid_df["ebay_price"].min())
else:
    floor_price = 0.0

evaluated_lot = evaluate_lot_risk(
    {"lot_id": selected_lot, "floor_price": floor_price},
    verified_lots_set=verified_set,
)

is_verified = evaluated_lot["is_verified"]

st.divider()

# Top High-Velocity Queue Navigation Bar
nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])

with nav_col1:
    if st.button("⬅️ Previous Lot", use_container_width=True):
        st.session_state.lot_index = (
            st.session_state.lot_index - 1
        ) % len(all_lots)
        st.rerun()

with nav_col2:
    st.markdown(
        f"<h3 style='text-align: center; margin:0;'>Item {st.session_state.lot_index + 1} of {len(all_lots)}</h3>",
        unsafe_allow_html=True,
    )

with nav_col3:
    if st.button("Next Lot ➡️", use_container_width=True, type="primary"):
        st.session_state.lot_index = (
            st.session_state.lot_index + 1
        ) % len(all_lots)
        st.rerun()

st.divider()

# Target Lot Header & Status Badging
header_col1, header_col2 = st.columns([3, 1])

with header_col1:
    st.subheader(f"Lot #{selected_lot}: {lot_title}")

with header_col2:
    if is_verified:
        st.success("🟢 STATUS: [VERIFIED]")
    else:
        st.warning("⚠️ STATUS: [UNVERIFIED]")

# Display recalculated bid metrics
m1, m2, m3 = st.columns(3)
m1.metric("Adjusted Market Floor", f"${floor_price:.2f}")
m2.metric("Target Max Hammer Bid", evaluated_lot["target_bid_display"])
m3.metric(
    "Verification Status", "VERIFIED" if is_verified else "UNVERIFIED"
)

st.divider()
st.markdown("### Candidate eBay Comps for Review")

num_comps = len(lot_df)
cols = st.columns(min(num_comps, 5) if num_comps > 0 else 1)

REJECTION_REASONS = [
    "WRONG_CATEGORY",
    "ACCESSORY_ONLY",
    "MODEL_MISMATCH",
    "CONDITION_DIFFERENCE",
    "BUNDLE_MISMATCH",
    "OTHER",
]

for idx, (_, row) in enumerate(lot_df.iterrows()):
    comp_rank = row.get("comp_rank", idx + 1)
    ebay_title = str(row.get("ebay_title", "Unknown Title"))
    ebay_price = float(row.get("ebay_price", 0.0))
    ebay_url = str(row.get("item_url", "#"))
    ebay_item_id = str(row.get("item_id_str"))
    image_url = row.get("image_url", None)

    logged_dec = row.get("logged_decision")
    logged_rea = row.get("logged_reason")

    col = cols[idx % len(cols)]

    with col:
        st.markdown(f"#### Rank #{comp_rank}")

        if logged_dec == "REJECT":
            st.error(f"🚫 REJECTED\n\n`{logged_rea or 'REJECTED'}`")
        elif logged_dec == "ACCEPT":
            st.success("✅ ACCEPTED COMP")
        elif logged_dec == "UNSURE":
            st.warning("❓ MARKED UNSURE")

        if pd.notna(image_url) and image_url:
            st.image(image_url, use_container_width=True)
        else:
            st.caption("📷 [No Image Available]")

        st.info(f"**{ebay_title}**")
        st.metric(label="Listed Price", value=f"${ebay_price:.2f}")
        st.markdown(f"[🔗 View Listing on eBay]({ebay_url})")

        query_str = row.get("query_string", lot_title)

        if logged_dec in ["ACCEPT", "REJECT", "UNSURE"]:
            st.caption("🔒 Decision recorded.")
        else:
            if st.button(
                "✅ Accept",
                key=f"accept_{selected_lot}_{comp_rank}",
                type="primary",
            ):
                success = log_decision(
                    lot_id=str(selected_lot),
                    ebay_item_id=ebay_item_id,
                    query_string=str(query_str),
                    decision="ACCEPT",
                    rejection_reason=None,
                    listed_price=ebay_price,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                if success:
                    st.toast(
                        f"Logged ACCEPT for Lot #{selected_lot} (Rank #{comp_rank})",
                        icon="✅",
                    )
                    st.rerun()

            with st.popover(
                "🚫 Reject", key=f"reject_popover_{selected_lot}_{comp_rank}"
            ):
                st.markdown("**Select Rejection Reason:**")
                reason = st.radio(
                    "Reason",
                    REJECTION_REASONS,
                    key=f"reason_radio_{selected_lot}_{comp_rank}",
                    label_visibility="collapsed",
                )
                if st.button(
                    "Confirm Rejection",
                    key=f"confirm_reject_{selected_lot}_{comp_rank}",
                ):
                    success = log_decision(
                        lot_id=str(selected_lot),
                        ebay_item_id=ebay_item_id,
                        query_string=str(query_str),
                        decision="REJECT",
                        rejection_reason=reason,
                        listed_price=ebay_price,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                    if success:
                        st.toast(
                            f"Logged REJECT [{reason}] for Lot #{selected_lot}",
                            icon="🚫",
                        )
                        st.rerun()

            if st.button(
                "❓ Unsure",
                key=f"unsure_{selected_lot}_{comp_rank}",
                type="secondary",
            ):
                success = log_decision(
                    lot_id=str(selected_lot),
                    ebay_item_id=ebay_item_id,
                    query_string=str(query_str),
                    decision="UNSURE",
                    rejection_reason=None,
                    listed_price=ebay_price,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                if success:
                    st.toast(
                        f"Logged UNSURE for Lot #{selected_lot}", icon="❓"
                    )
                    st.rerun()

st.divider()

# Bottom Navigation Bar
bottom_col1, bottom_col2, bottom_col3 = st.columns([1, 2, 1])
with bottom_col1:
    if st.button(
        "⬅️ Previous Lot", key="bottom_prev", use_container_width=True
    ):
        st.session_state.lot_index = (
            st.session_state.lot_index - 1
        ) % len(all_lots)
        st.rerun()

with bottom_col3:
    if st.button(
        "Next Lot ➡️",
        key="bottom_next",
        use_container_width=True,
        type="primary",
    ):
        st.session_state.lot_index = (
            st.session_state.lot_index + 1
        ) % len(all_lots)
        st.rerun()

st.divider()

# Audit Log Viewer
st.markdown("### Active Audit Log Summary (`data/audit_decisions.jsonl`)")
log_path = os.path.join("data", "audit_decisions.jsonl")

if os.path.exists(log_path):
    try:
        decisions_df = pd.read_json(log_path, lines=True)
        if not decisions_df.empty:
            st.dataframe(decisions_df.tail(10), use_container_width=True)
        else:
            st.caption("Audit log is currently empty.")
    except Exception as e:
        st.caption(f"No decisions logged yet or error reading log: {e}")
else:
    st.caption("No decisions logged yet.")