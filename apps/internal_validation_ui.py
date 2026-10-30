"""Internal product-match review pilot. Run with Streamlit; independent of V4."""
import copy
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from core import audit_evidence as evidence
from core import audit_pilot as pilot
from core import audit_pilot_demo as demo
from core.feedback_store import FeedbackStore, Relationship, StaleDecisionError


REASON_LABELS = {
    "CONDITION_DIFFERENCE": "Condition differs", "MODEL_VARIANT_MISMATCH": "Model or variant differs",
    "WRONG_CATEGORY": "Wrong product category", "QUANTITY_BUNDLE_MISMATCH": "Quantity or bundle differs",
    "ACCESSORY_MISMATCH": "Accessory mismatch", "OTHER": "Other mismatch",
}


def checkpoint(session, path):
    try:
        pilot.save_session(path, session)
        st.session_state["checkpoint_error"] = None
    except Exception as error:
        st.session_state["checkpoint_error"] = f"Queue recovery could not be saved ({type(error).__name__}). Keep this window open; committed judgments are still in SQLite."


@st.dialog("Inspect photograph", width="large")
def enlarge(image, caption):
    st.image(image, width="stretch", caption=caption, alt=caption)


def photograph(attachment, *, demo_mode, index, key):
    url = pilot.image_url(attachment)
    if demo_mode and attachment:
        image, caption = pilot.demo_artwork(index), "DEMO illustration — not a source photograph"
    else:
        image, caption = url, "Source image — no condition or image-type inference"
    if image is None:
        st.info("Photograph unavailable or its URL is not approved for display. Use the source listing link.")
        return
    try:
        st.image(image, width="stretch", caption=caption, alt=caption)
        if st.button("Inspect larger photograph", key=key, width="stretch"):
            enlarge(image, caption)
    except Exception:
        st.warning("Photograph could not be displayed. The review controls and source link remain available.")
    if not demo_mode:
        st.caption("External images may be blocked or expire. If this image does not load, open the source listing.")
        st.link_button("Open this image in a new tab", url)


def source_link(label, value, source, demo_mode):
    url = pilot.safe_url(value, pilot.LINK_HOSTS[source])
    if demo_mode:
        st.caption("Source links disabled in the synthetic demo.")
    elif url:
        st.link_button(label, url)
    else:
        st.caption("Source link unavailable or not approved.")


def render_crowe(entry, profile, demo_mode):
    snapshot = entry["lot"]
    selected = snapshot["detail"] or snapshot["catalog"]
    lot = selected["lot"]
    st.subheader("Original Crowe lot")
    st.text(lot.get("title") or "Title unavailable")
    st.caption(f"Auction {snapshot['auction_id']} · Internal lot {snapshot['lot_id']} · Displayed lot {snapshot['lot_number']}")
    source_link("Open Crowe lot", lot.get("source_url") or selected["source"]["url"], "crowe", demo_mode)
    st.caption(f"Source received: {selected['retrieved_at']}")
    gallery = lot.get("images")
    if not gallery and lot.get("primary_image"):
        gallery = [lot["primary_image"]]
        st.info("Catalog thumbnail only; full gallery unavailable.")
    if gallery:
        key = f"{profile}.photo.{snapshot['lot_id']}"
        if st.session_state.get(key, 0) >= len(gallery):
            st.session_state[key] = 0
        index = st.selectbox("Crowe photograph", range(len(gallery)), key=key,
                             format_func=lambda n: f"Photo {n + 1} of {len(gallery)}")
        photograph(gallery[index], demo_mode=demo_mode, index=index, key=key + ".large")
        st.caption(f"Attachment ID: {gallery[index].get('attachment_id', 'unavailable')}")
    else:
        st.info("Photographs unavailable. Load lot photos and description in genuine mode if a source link is available.")
    st.markdown("**Full source description**")
    st.text(pilot.description(lot) or "Description unavailable.")
    st.markdown("**Source condition and packaging attributes**")
    attributes = lot.get("attributes") or []
    if not attributes:
        st.text("Structured condition/packaging unavailable. Check the source description for observations.")
    for attribute in attributes:
        value = attribute.get("data")
        st.text(f"{attribute.get('label') or 'Source attribute'}: {json.dumps(value, ensure_ascii=False) if value is not None else 'Unknown'}")
    with st.expander("Source identity, status and raw price fields"):
        st.json({"auction": selected["auction"], "raw_fields": lot.get("raw_fields"), "source": selected["source"]})


def feedback_controls(candidate, store, reviewer, profile):
    relation = Relationship(**candidate["relationship"])
    current = store.latest_decision(relation, reviewer)
    view = profile + ".review." + hashlib.sha256(json.dumps(candidate["relationship"], sort_keys=True).encode()).hexdigest()
    versions = st.session_state.setdefault("shown_versions", {})
    expected = versions.get(view, current["event_id"] if current else None)
    if current:
        st.info(f"Current judgment: {current['decision']} · saved {current['recorded_at']}")
        if current["evidence_id"] != candidate["evidence_id"]:
            st.warning("This judgment belongs to earlier evidence for the same lot and listing. The current snapshot has not been reviewed by you.")
    else:
        st.info("No judgment saved by this reviewer for this lot and listing.")
    st.caption("ACCEPT means suitable product comparable only. It does not establish resale value, physical condition or a bid.")
    with st.form(view + ".form"):
        decisions = ["ACCEPT", "REJECT", "UNSURE"]
        decision = st.radio("Your judgment", decisions, horizontal=True,
                            index=decisions.index(current["decision"]) if current else 2, key=view + ".decision")
        reasons = st.multiselect("Reasons (required for REJECT)", list(REASON_LABELS),
                                 format_func=REASON_LABELS.get, default=current["reasons"] if current else [], key=view + ".reasons")
        notes = st.text_area("Reviewer notes (optional)", value=(current["notes"] or "") if current else "", key=view + ".notes")
        submitted = st.form_submit_button("Save correction" if current else "Save judgment", type="primary", width="stretch")
    if submitted:
        if decision == "REJECT" and not reasons:
            st.error("Choose at least one structured rejection reason before saving.")
        else:
            payload = dict(reviewer_id=reviewer, evidence_id=candidate["evidence_id"], decision=decision,
                           reasons=sorted(reasons), notes=notes or None)
            signature = json.dumps(payload, sort_keys=True)
            pending_key = view + ".pending"
            pending = st.session_state.get(pending_key)
            if not pending or pending["signature"] != signature:
                pending = {"signature": signature, "event_id": str(uuid4()), "expected": expected}
                st.session_state[pending_key] = pending
            # No redundant event for an unchanged, already-reviewed snapshot.
            identical = current and all(current.get(k) == v for k, v in payload.items())
            if identical and current["event_id"] == expected:
                st.info("This exact judgment is already saved.")
                st.session_state.pop(pending_key, None)
            else:
                try:
                    saved = store.record_decision(event_id=pending["event_id"], expected_current_event_id=pending["expected"], **payload)
                    versions[view] = saved["event_id"]
                    st.session_state.pop(pending_key, None)
                    st.session_state["save_notice"] = ("success", f"Saved {saved['decision']}. Previous judgments remain in history.")
                    st.rerun()
                except StaleDecisionError:
                    st.session_state.pop(pending_key, None)
                    latest = store.latest_decision(relation, reviewer)
                    versions[view] = latest["event_id"] if latest else None
                    st.session_state["save_notice"] = ("warning", "Another save changed this judgment. Latest state reloaded; review it before submitting your correction again.")
                    st.rerun()
                except Exception as error:
                    st.error(f"Save not confirmed ({type(error).__name__}). Your draft and submission ID are retained; retry to reconcile safely.")
    versions[view] = current["event_id"] if current else None
    with st.expander("Review history for this reviewer"):
        history = store.history(relation, reviewer)
        if history:
            st.json(history)
            event_id = st.selectbox("Inspect evidence from a saved event", [event["event_id"] for event in history], key=view + ".history")
            selected_event = next(event for event in history if event["event_id"] == event_id)
            st.json(store.get_evidence(selected_event["evidence_id"]))
        else:
            st.caption("No previous judgments.")


def render_ebay(entry, session, path, store, reviewer, profile, demo_mode):
    st.subheader("One eBay comparable at a time")
    lid = entry["lot"]["lot_id"]
    candidates = entry["candidates"]
    outcome = entry["outcome"]
    if not candidates:
        messages = {"NOT_REQUESTED": "NOT_REQUESTED — enter a query and explicitly fetch candidates.",
                    "EMPTY": "EMPTY — the search returned no candidates. This lot remains in your queue.",
                    "ERROR": "ERROR — candidate retrieval failed. No substitute candidates were created."}
        st.warning(messages.get(outcome, "No candidates available."))
        if entry["search"]:
            code = (entry["search"].get("error") or {}).get("code")
            if code in ("AUTH_UNAVAILABLE", "AUTH_ERROR"):
                st.error("eBay credentials or authentication are unavailable. Crowe evidence remains available; ask the host operator to check the eBay setup.")
            st.json({"error": entry["search"].get("error"), "http_status": entry["search"].get("http_status")})
        return
    ids = [candidate["relationship"]["listing_id"] for candidate in candidates]
    key = f"{profile}.candidate.{lid}"
    saved_id = session["selected_candidates"].get(lid)
    if st.session_state.get(key) not in ids:
        st.session_state[key] = saved_id if saved_id in ids else ids[0]

    def choose(delta=0):
        current = st.session_state[key]
        selected = ids[max(0, min(len(ids) - 1, ids.index(current) + delta))]
        st.session_state[key] = selected
        session["selected_candidates"][lid] = selected
        checkpoint(session, path)

    selected = st.selectbox("Selected comparable", ids, key=key, on_change=choose,
                            format_func=lambda value: f"Candidate {ids.index(value) + 1} of {len(ids)} · {value}")
    position = ids.index(selected)
    with st.container(horizontal=True):
        st.button("Previous candidate", key=key + ".prev", on_click=choose, args=(-1,), disabled=position == 0)
        st.button("Next candidate", key=key + ".next", on_click=choose, args=(1,), disabled=position == len(ids) - 1)
    candidate = candidates[position]
    listing = candidate["listing"]["item"]
    st.text(listing.get("title") or "Title unavailable")
    st.caption(f"Marketplace itemId: {selected}")
    source_link("Open eBay listing", listing.get("itemWebUrl"), "ebay", demo_mode)
    if attachment := pilot.listing_image(listing):
        photograph(attachment, demo_mode=demo_mode, index=position, key=key + ".large")
    else:
        st.info("Listing image unavailable.")
    st.markdown("**Active asking price — not a sold price**")
    st.text(pilot.money(listing.get("price")))
    shipping = listing.get("shippingOptions") or []
    if not shipping:
        st.text("Shipping: Unknown")
    for option in shipping:
        st.text("Shipping: " + pilot.money(option.get("shippingCost") if isinstance(option, dict) else None))
    st.text("Listing condition: " + (listing.get("condition") or "Unknown"))
    st.caption("Listing evidence received: " + candidate["listing"]["retrieved_at"])
    with st.expander("Exact search and response context"):
        st.json(entry["search"])
    feedback_controls(candidate, store, reviewer, profile)


def main():
    st.set_page_config(page_title="Internal Comparable Review", page_icon="🔎", layout="wide", initial_sidebar_state="collapsed")
    # Supported key classes scope modest styling. The two responsive selectors
    # supplement Streamlit's native <=640px stacking for tablet portrait widths.
    st.html('''<style>
      .st-key-pilot_shell {font-size:1.1rem;}
      .st-key-pilot_shell button {min-height:48px; padding:0.6rem 1rem;}
      .st-key-pilot_shell p, .st-key-pilot_shell label {font-size:1.05rem; line-height:1.55;}
      .st-key-pilot_shell pre {font-family:inherit; font-size:1.05rem; line-height:1.55; white-space:pre-wrap;}
      @media (max-width: 950px) {
        .st-key-evidence_pair [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]) {flex-direction:column;}
        .st-key-evidence_pair [data-testid="stColumn"] {width:100%; flex:1 1 100%;}
      }
    </style>''')
    try:
        config = pilot.load_config()
        mode_label = st.sidebar.radio("Data mode", ["Offline demo", "Genuine review"], key="data_mode")
        mode = "demo" if mode_label == "Offline demo" else "live"
        reviewers = {row["id"]: row["label"] for row in config["reviewers"]}
        reviewer = st.sidebar.selectbox("Reviewer attribution", list(reviewers), format_func=reviewers.get, key="reviewer")
        st.sidebar.caption("Attribution only — this selector is not security authentication.")
        db_path, session_path = pilot.storage_paths(mode, reviewer)
        with FeedbackStore(db_path) as store, st.container(key="pilot_shell"):
            store.initialize()
            profile = f"{mode}:{reviewer}"
            state_key = "pilot_session:" + profile
            st.title("Internal comparable review")
            st.caption(f"Reviewer: {reviewers[reviewer]} · Open the sidebar to change attribution or data mode.")
            if mode == "demo":
                st.warning("OFFLINE DEMO — sanitized Crowe fixtures and synthetic eBay listings. Illustrations are not source photos. All judgments go to a separate demo database.")
            else:
                st.info("GENUINE REVIEW — source evidence and human judgments. No synthetic fallback.")
            if state_key not in st.session_state:
                try:
                    session = pilot.load_session(session_path, mode, store)
                    if session is None and mode == "demo":
                        session = pilot.new_session(demo.source(), mode, {}, store)
                        lid = session["selected_lot"]
                        pilot.remember_search(session, lid, demo.search("48980", lid, "floral canvas 12 x 16"))
                        pilot.refresh_entry(session, lid, store)
                        checkpoint(session, session_path)
                    st.session_state[state_key] = session
                except Exception as error:
                    st.error(f"Saved queue could not be restored ({type(error).__name__}). No legacy data was substituted. Committed judgments remain in SQLite.")
                    st.session_state[state_key] = None
            session = st.session_state[state_key]
            if notice := st.session_state.pop("save_notice", None):
                getattr(st, notice[0])(notice[1])
            if st.session_state.get("checkpoint_error"):
                st.warning(st.session_state["checkpoint_error"])
            if session:
                st.caption(f"Loaded auction: {session['page']['auction'].get('title', 'Title unavailable')} · ID {session['page']['auction']['auction_id']} · Page {session['page']['pagination']['page']}")
            with st.expander("Session setup and recovery"):
                st.caption("Configured next load: " + config.get("label", "Explicitly configured selected catalog page"))
                st.caption(f"Database: {db_path}\nQueue checkpoint: {session_path}")
                st.caption("Loading a page starts a new queue. Existing judgments and evidence remain in SQLite. Each reviewer has a separate queue checkpoint.")
                if st.button("Load configured catalog page" if mode == "live" else "Reset demo queue", key="load_page"):
                    try:
                        with st.spinner("Loading selected catalog page…"):
                            request = {key: config[key] for key in ("catalog_url", "auction_id", "query_arguments")}
                            source = evidence.acquire_crowe_for_review(**request) if mode == "live" else demo.source()
                            updated = pilot.new_session(source, mode, request if mode == "live" else {}, store)
                            updated["revision"] = (session or {}).get("revision", 0) + 1
                            st.session_state[state_key] = updated
                            checkpoint(updated, session_path)
                            st.rerun()
                    except Exception as error:
                        st.error(f"Catalog load failed ({type(error).__name__}). The previous queue, if any, has been retained.")
            if session is None:
                st.info("Open Session setup and recovery, then load the configured catalog page. No network request runs until you press that button.")
                return
            entries = session["page"]["lots"]
            if not entries:
                st.info("This selected catalog page contains no lots.")
                return
            ids = [entry["lot"]["lot_id"] for entry in entries]
            by_id = {entry["lot"]["lot_id"]: entry for entry in entries}
            lot_key = profile + ".lot_choice"
            if st.session_state.get(lot_key) not in ids or st.session_state.get(profile + ".revision") != session["revision"]:
                st.session_state[lot_key] = session["selected_lot"]
                st.session_state[profile + ".revision"] = session["revision"]

            def move_lot(delta=0):
                selected = ids[max(0, min(len(ids) - 1, ids.index(st.session_state[lot_key]) + delta))]
                st.session_state[lot_key] = selected
                session["selected_lot"] = selected
                checkpoint(session, session_path)

            lid = st.selectbox("Review queue", ids, key=lot_key, on_change=move_lot,
                               format_func=lambda value: f"Lot {by_id[value]['lot']['lot_number']} · {by_id[value]['lot']['catalog']['lot']['title']}")
            index = ids.index(lid)
            with st.container(horizontal=True):
                st.button("Previous lot", key="previous_lot", on_click=move_lot, args=(-1,), disabled=index == 0)
                st.button("Next lot", key="next_lot", on_click=move_lot, args=(1,), disabled=index == len(ids) - 1)
                st.write(f"Lot {index + 1} of {len(ids)} on this page")
            total = sum(len(entry["candidates"]) for entry in entries)
            reviewed = 0
            for entry in entries:
                for candidate in entry["candidates"]:
                    latest = store.latest_decision(Relationship(**candidate["relationship"]), reviewer)
                    reviewed += bool(latest and latest["evidence_id"] == candidate["evidence_id"])
            st.progress(reviewed / total if total else 0, text=f"Your current-snapshot judgments: {reviewed} / {total} candidates · {sum(not entry['candidates'] for entry in entries)} lots without candidates")
            entry = by_id[lid]
            st.subheader(f"Lot {entry['lot']['lot_number']} · {entry['lot']['catalog']['lot']['title']}")
            search_history = session["search_history"].get(lid, [])
            if search_history:
                run_key = profile + ".search_run." + lid
                if st.session_state.pop(run_key + ".reset", False) or st.session_state.get(run_key) not in range(len(search_history)):
                    st.session_state[run_key] = session["selected_searches"].get(lid, len(search_history) - 1)
                selected_run = st.selectbox("Retrieved candidate sets", range(len(search_history)), key=run_key,
                                            format_func=lambda i: f"Search {i + 1} · {search_history[i]['status']} · {search_history[i]['attempted_at']}")
                if selected_run != session["selected_searches"].get(lid):
                    updated = copy.deepcopy(session)
                    updated["selected_searches"][lid] = selected_run
                    updated["searches"][lid] = copy.deepcopy(search_history[selected_run])
                    pilot.refresh_entry(updated, lid, store)
                    st.session_state[state_key] = updated; checkpoint(updated, session_path); st.rerun()
            if mode == "live" and st.button("Load lot photos and description", key="load_detail"):
                try:
                    with st.spinner("Loading selected lot evidence…"):
                        detail_url = entry["lot"]["catalog"]["lot"].get("source_url")
                        updated = copy.deepcopy(session)
                        updated["detail_sources"][lid] = evidence.acquire_crowe_for_review(
                            **session["catalog_request"], detail_url=detail_url, lot_id=lid)
                        pilot.refresh_entry(updated, lid, store)
                        st.session_state[state_key] = updated; checkpoint(updated, session_path); st.rerun()
                except Exception as error:
                    st.error(f"Lot evidence load failed ({type(error).__name__}). Previously loaded evidence is retained.")
            with st.expander("Search for comparable candidates", expanded=not entry["candidates"]), st.form(profile + ".search." + lid):
                query = st.text_input("Search query", value=entry["search"]["request"]["params"]["q"] if entry["search"] else entry["lot"]["catalog"]["lot"]["title"], key=profile + ".query." + lid)
                limit = st.number_input("Maximum candidates", min_value=1, max_value=50, value=config.get("ebay", {}).get("limit", 20), step=1)
                demo_outcome = st.selectbox("Demo search outcome", ["READY", "EMPTY", "ERROR"]) if mode == "demo" else None
                search_now = st.form_submit_button("Fetch candidates" if mode == "live" else "Load synthetic candidates", width="stretch")
            if search_now:
                try:
                    with st.spinner("Retrieving selected-lot candidates…"):
                        result = demo.search(entry["lot"]["auction_id"], lid, query, limit, demo_outcome) if mode == "demo" else evidence.fetch_ebay_candidates(
                            auction_id=entry["lot"]["auction_id"], lot_id=lid, query=query, limit=limit,
                            filters=config.get("ebay", {}).get("filters"), sort=config.get("ebay", {}).get("sort"),
                            marketplace_id=config.get("ebay", {}).get("marketplace_id", "EBAY_US"))
                        updated = copy.deepcopy(session); pilot.remember_search(updated, lid, result)
                        pilot.refresh_entry(updated, lid, store)
                        st.session_state[profile + ".search_run." + lid + ".reset"] = True
                        st.session_state[state_key] = updated; checkpoint(updated, session_path); st.rerun()
                except Exception as error:
                    st.error(f"Search was not completed ({type(error).__name__}). No substitute candidates were created; earlier evidence is retained.")
            with st.container(key="evidence_pair"):
                left, right = st.columns(2, gap="medium")
                with left:
                    render_crowe(entry, profile, mode == "demo")
                with right:
                    render_ebay(entry, session, session_path, store, reviewer, profile, mode == "demo")
    except Exception as error:
        st.error(f"Pilot could not open its configuration or storage ({type(error).__name__}). Check the local operating instructions. No save is confirmed.")


if __name__ == "__main__":
    main()
