"""Small state/display helpers for the internal Streamlit pilot, not V4."""
import copy
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from core.audit_evidence import build_review_page

ROOT = Path(__file__).resolve().parents[1]
MAX_SESSION_BYTES = 32 * 1024 * 1024
IMAGE_HOSTS = {"bids.crauctions.com", "as-assets.marknetalliance.com", "i.ebayimg.com"}
LINK_HOSTS = {"crowe": {"bids.crauctions.com"}, "ebay": {"www.ebay.com", "www.ebay.ca", "www.ebay.co.uk", "www.ebay.de", "www.ebay.com.au"}}


class PilotError(ValueError):
    pass


def load_config():
    path = Path(os.environ.get("AUDIT_PILOT_CONFIG", ROOT / "config/internal-audit.example.json"))
    config = json.loads(path.read_text(encoding="utf-8"))
    reviewers = config.get("reviewers", [])
    if not reviewers or len({r["id"] for r in reviewers}) != len(reviewers):
        raise PilotError("Configure distinct reviewer IDs")
    for reviewer in reviewers:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", reviewer["id"]) or not reviewer.get("label"):
            raise PilotError("Invalid reviewer attribution configuration")
    if not all(k in config for k in ("catalog_url", "auction_id", "query_arguments")):
        raise PilotError("Configure a catalog URL, auction ID and exact Apollo arguments")
    return config


def storage_paths(mode, reviewer):
    if mode not in ("demo", "live") or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", reviewer):
        raise PilotError("Invalid storage profile")
    default = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "CroweAuditPilot"
    root = Path(os.environ.get("AUDIT_PILOT_HOME", default)).expanduser().resolve()
    if root == ROOT or ROOT in root.parents:
        raise PilotError("Pilot data must be stored outside the repository")
    if (root / "demo").resolve() == (root / "live").resolve():
        raise PilotError("Demo and genuine storage locations must be separate")
    folder = root / mode
    folder.mkdir(parents=True, exist_ok=True)
    db, session = folder / "feedback.sqlite3", folder / f"session-{reviewer}.json"
    if db.is_symlink() or session.is_symlink():
        raise PilotError("Symlinked pilot data files are not supported")
    return db, session


def save_session(path, session):
    """Atomic checkpoint; an error leaves the previous file intact."""
    payload = json.dumps(session, ensure_ascii=False, allow_nan=False).encode()
    if len(payload) > MAX_SESSION_BYTES:
        raise PilotError("Session exceeds the 32 MiB pilot limit")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".session-", delete=False) as file:
            temporary = Path(file.name)
            file.write(payload); file.flush(); os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def load_session(path, mode, store):
    if not path.exists():
        return None
    if path.stat().st_size > MAX_SESSION_BYTES:
        raise PilotError("Saved session is too large")
    session = json.loads(path.read_text(encoding="utf-8"))
    if session.get("version") != 1 or session.get("mode") != mode:
        raise PilotError("Saved session has an incompatible mode or version")
    # Replay validation without network access. FeedbackStore evidence retries are
    # idempotent; reconstruct the display from the persisted source inputs.
    rebuilt = new_session(session["crowe"], mode, session["catalog_request"], store)
    for lid, source in session.get("detail_sources", {}).items():
        rebuilt["detail_sources"][lid] = source
    for lid, search in session.get("searches", {}).items():
        rebuilt["searches"][lid] = search
    rebuilt["search_history"] = session.get("search_history", {})
    rebuilt["selected_searches"] = session.get("selected_searches", {})
    ids = {entry["lot"]["lot_id"] for entry in rebuilt["page"]["lots"]}
    if (set(rebuilt["detail_sources"]) | set(rebuilt["searches"])) - ids:
        raise PilotError("Saved session refers to lots outside its queue")
    for lid in ids:
        refresh_entry(rebuilt, lid, store)
    rebuilt["selected_lot"] = session.get("selected_lot") if session.get("selected_lot") in ids else rebuilt["selected_lot"]
    rebuilt["selected_candidates"] = session.get("selected_candidates", {})
    rebuilt["revision"] = session.get("revision", 0)
    return rebuilt


def new_session(crowe, mode, catalog_request, store):
    page = build_review_page(crowe, store=store)
    return {"version": 1, "mode": mode, "catalog_request": copy.deepcopy(catalog_request),
            "crowe": copy.deepcopy(crowe), "detail_sources": {}, "searches": {}, "page": page,
            "search_history": {}, "selected_searches": {},
            "selected_lot": page["lots"][0]["lot"]["lot_id"] if page["lots"] else None,
            "selected_candidates": {}, "revision": 0}


def remember_search(session, lid, search):
    history = session["search_history"].setdefault(lid, [])
    history.append(copy.deepcopy(search))
    session["selected_searches"][lid] = len(history) - 1
    session["searches"][lid] = search


def refresh_entry(session, lid, store):
    source = session["detail_sources"].get(lid, session["crowe"])
    if source["catalog"]["source"]["query_arguments"] != session["crowe"]["catalog"]["source"]["query_arguments"]:
        raise PilotError("Selected detail no longer matches the configured catalog context")
    search = session["searches"].get(lid)
    page = build_review_page(source, searches=[search] if search else [], store=store)
    replacement = next((entry for entry in page["lots"] if entry["lot"]["lot_id"] == lid), None)
    if replacement is None:
        raise PilotError("Selected lot is absent from the returned catalog page")
    for index, entry in enumerate(session["page"]["lots"]):
        if entry["lot"]["lot_id"] == lid:
            session["page"]["lots"][index] = replacement
            return
    raise PilotError("Selected lot is outside the review queue")


def safe_url(value, hosts):
    if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme == "https" and parsed.hostname in hosts and parsed.username is None
                and parsed.password is None and parsed.port in (None, 443)):
            return value
    except ValueError:
        pass
    return None


def image_url(attachment):
    """Prefer one medium variant; never fetch or iterate through a gallery."""
    if not isinstance(attachment, dict):
        return None
    variants = attachment.get("asset_url_image_variants") or {}
    cached = attachment.get("cached_assets") or []
    choices = []
    for variant in ("medium", "small", "thumb", "large", "original"):
        choices.extend(asset.get("url") for asset in cached if isinstance(asset, dict) and asset.get("variant") == variant)
        if isinstance(variants, dict):
            choices.append(variants.get(variant))
    choices.extend([attachment.get("imageUrl"), attachment.get("url")])
    return next((url for value in choices if (url := safe_url(value, IMAGE_HOSTS))), None)


def listing_image(listing):
    images = [listing.get("image")] + (listing.get("thumbnailImages") or []) + (listing.get("additionalImages") or [])
    return next((image for image in images if image_url(image)), next((image for image in images if isinstance(image, dict) and image), None))


class _Description(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag in ("p", "div", "br", "li") and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def description(lot):
    if lot.get("description_plain"):
        return lot["description_plain"]
    parser = _Description()
    parser.feed(lot.get("description_html") or "")
    return "".join(parser.parts).strip()


def money(value):
    if not isinstance(value, dict) or value.get("value") is None:
        return "Unknown"
    return f"{value['value']} {value.get('currency') or '(currency unknown)'}"


def demo_artwork(index):
    # Clearly labeled illustrations, not reconstructed source photographs.
    colors = ["#dbeafe", "#d1fae5", "#fef3c7", "#ede9fe", "#ffe4e6"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="480" viewBox="0 0 800 480">
      <rect width="800" height="480" rx="24" fill="{colors[index % len(colors)]}"/>
      <rect x="240" y="80" width="320" height="240" rx="12" fill="white" stroke="#334155" stroke-width="5"/>
      <path d="M270 280 L350 180 L420 250 L490 150 L535 280 Z" fill="#64748b"/>
      <text x="400" y="370" text-anchor="middle" font-size="30" fill="#0f172a">DEMO illustration {index + 1}</text>
      <text x="400" y="415" text-anchor="middle" font-size="23" fill="#334155">Not a source photograph</text>
    </svg>'''
