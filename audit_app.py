import json
import os
import pandas as pd
import streamlit as st

NOISE_FILE = "noise_rules.json"


def save_noise_terms(new_terms):
    """Appends new negative keywords to persistent noise dictionary."""
    existing_terms = set()
    if os.path.exists(NOISE_FILE):
        try:
            with open(NOISE_FILE, "r") as f:
                existing_terms = set(json.load(f))
        except Exception:
            existing_terms = set()

    # Only add terms longer than 3 characters
    existing_terms.update([t.lower() for t in new_terms if len(t) > 3])

    with open(NOISE_FILE, "w") as f:
        json.dump(sorted(list(existing_terms)), f, indent=2)

st.set_page_config(
    page_title="Auction Underwriting Audit Dashboard", layout="wide"
)

st.title("🎯 Auction Underwriting: Visual Comp Audit & Feedback")
st.caption(
    "Review live eBay comps, discard irrelevant hits, and recalculate market floors in real-time."
)

# 1. Load Audit CSV
try:
    df = pd.read_csv("comp_audit.csv")
except Exception:
    st.error(
        "❌ Could not find 'comp_audit.csv'. Run 'python inventory_analyzer4.py' first to generate audit data."
    )
    st.stop()

if df.empty:
    st.warning("'comp_audit.csv' is empty.")
    st.stop()

# 2. Sidebar Navigation
lots = df["crowe_lot"].unique()
selected_lot = st.sidebar.selectbox("Select Crowe Lot ID", lots)

# Filter data for selected lot
lot_df = df[df["crowe_lot"] == selected_lot].copy()
lot_title = lot_df["crowe_title"].iloc[0]

st.subheader(f"Catalog Lot {selected_lot}: {lot_title}")

# 3. Interactive Comp Card Layout
st.markdown("### Top Active eBay Comps")
cols = st.columns(min(len(lot_df), 5))

active_prices = []
discarded_keywords = []

for idx, (_, row) in enumerate(lot_df.iterrows()):
    col = cols[idx % len(cols)]
    with col:
        st.markdown(f"**Rank #{row['comp_rank']}**")

        if pd.notna(row.get("image_url")) and row["image_url"]:
            st.image(row["image_url"], use_container_width=True)
        else:
            st.caption("📷 No image available")

        st.info(row["ebay_title"])
        st.metric(label="Listing Price", value=f"${row['ebay_price']:.2f}")
        st.markdown(f"[🔗 View Listing on eBay]({row['item_url']})")

        # Interactive Feedback Button
        discard_key = f"discard_{selected_lot}_{idx}"
        if st.checkbox(f"Discard Comp #{row['comp_rank']}", key=discard_key):
            st.error("Status: Discarded")
            # Extract title words to build negative keyword log
            words = [
                w.lower()
                for w in row["ebay_title"].split()
                if len(w) > 3 and w.lower() not in lot_title.lower()
            ]
            discarded_keywords.extend(words)
        else:
            st.success("Status: Active")
            active_prices.append(row["ebay_price"])

st.divider()

# 4. Live Recalculation Engine
st.markdown("### Valuation Impact")
if active_prices:
    # Uses lowest remaining active price as market floor
    revised_floor = min(active_prices)
    original_floor = min(lot_df["ebay_price"])

    m1, m2, m3 = st.columns(3)
    m1.metric("Original Floor Price", f"${original_floor:.2f}")
    m2.metric(
        "Revised Market Floor",
        f"${revised_floor:.2f}",
        delta=f"${revised_floor - original_floor:.2f}",
    )
    m3.metric("Active Comps Remaining", f"{len(active_prices)} / {len(lot_df)}")

    # Calculate Max Hammer Bid (35% target margin floor)
    # Formula: (Floor * 0.87 - Fees) / 1.22
    estimated_net = revised_floor * 0.87 - 5.00  # standard eBay fee & ship buffer
    max_hammer_bid = round(max(0.0, estimated_net * (1 - 0.35) / 1.22), 2)

    st.success(f"**Updated Max Hammer Bid:** ${max_hammer_bid:.2f}")

else:
    st.error(
        "⚠️ All comps for this lot were discarded. System will default to category fallback valuation."
    )

# 5. Export Discarded Keywords for Model Training
if discarded_keywords:
    st.divider()
    st.markdown("### Noise Keyword Extractor")
    st.write(
        "The following candidate noise terms were detected from discarded comps:"
    )
    unique_noise = sorted(list(set(discarded_keywords)))
    st.code(" ".join([f"-{term}" for term in unique_noise]))
    st.caption(
        "Copy these parameters directly into clean_title_for_search() or ebay_api_client.py negative keyword lists."
    )