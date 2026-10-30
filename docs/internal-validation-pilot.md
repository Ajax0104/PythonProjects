# Internal tablet audit pilot

This is an internal product-comparable validation tool for the owner and auction
buyer. It is independent of V4, manifests and `comp_audit.csv`. It does not value
lots, recommend bids or designate lots VERIFIED. The earlier Streamlit apps remain
unchanged and are not used by this pilot.

## Daily use: owner and reviewer

1. On the configured Windows host, double-click **`launch_internal_audit.cmd`**.
   A browser opens at `http://localhost:8501`. Leave the launcher window open.
2. The app starts in **Offline demo**. Open the sidebar using the top-left arrow
   to choose your reviewer attribution and, when configured, **Genuine review**.
   The selected reviewer and mode remain visible in the main view.
3. In genuine mode, open **Session setup and recovery** and click **Load configured
   catalog page**. Loading a new queue retains saved judgments and evidence in
   SQLite, but replaces that reviewer's active queue checkpoint.
4. Use the queue selector or **Previous lot / Next lot**. Click **Load lot photos
   and description** for selected-lot detail evidence. This uses the existing
   bounded adapter: one catalog request plus one selected detail request.
5. Open **Search for comparable candidates**, edit the query and click **Fetch
   candidates**. A rerender, navigation action or judgment save does not repeat
   this search. Earlier retrieved sets remain selectable in **Retrieved candidate
   sets**, including empty and failed searches.
6. Compare the source description and ordered photographs with one eBay listing.
   Use **Previous candidate / Next candidate**, the photo selector and **Inspect
   larger photograph**. Prices are active asking prices; shipping is separate and
   missing shipping is displayed as **Unknown**, never zero.
7. Select **ACCEPT**, **REJECT** or **UNSURE**, optionally add notes, and save.
   REJECT requires a structured reason. The current judgment and save timestamp
   appear after a confirmed save. Edit and use **Save correction** to append a new
   judgment; **Review history** also exposes the evidence reviewed in each event.
8. If another window saved first, the app reloads the latest judgment and asks you
   to reconsider before saving again. If a save is not confirmed, retry: the
   submission ID is retained to reconcile an uncertain commit without duplicates.

ACCEPT means only "suitable product comparable." It does not establish resale
value, physical condition, profitability or a bid. Progress counts judgments on
the currently displayed evidence snapshots, separately from their decisions.
An earlier judgment is clearly flagged when refreshed evidence differs.

The demo uses sanitized Crowe fixtures, synthetic eBay records and visibly labeled
illustrations. Source links are disabled there. Its search form can demonstrate
READY, EMPTY and ERROR outcomes. Demo judgments never use the genuine database.

Close the launcher window or press Ctrl+C there to stop the host. A tablet cannot
connect while the host is stopped or asleep. Unsaved form drafts are not guaranteed
to survive closing the browser; committed judgments are stored separately.

## One-time Windows host setup

Use the existing Python environment if it already has the dependencies. The
launcher searches, in order: `AUDIT_PYTHON`, repository `.venv`, repository `venv`,
Windows `py -3`, then `python`. Paths are quoted and the launcher changes to its
own repository directory, including when the path contains spaces.

Tested here: Python 3.12, Streamlit 1.66.1. The launcher checks for Streamlit
1.66.1 or newer, requests and python-dotenv. It reports missing dependencies and
does not install software automatically. A host operator can prepare an environment
once, if necessary:

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install "streamlit>=1.66.1,<2" requests python-dotenv
```

No terminal commands are needed for subsequent daily launches. The Windows batch
logic was reviewed and its dependency/Streamlit CLI options checked on Linux;
actual Windows double-click execution, firewall behavior and default-browser
opening still require the host smoke test below.

Optional Windows user environment settings (configure once through Environment
Variables or an operator-managed launcher shortcut):

| Setting | Purpose |
| --- | --- |
| `AUDIT_PYTHON` | Full path to the preferred Python executable, without surrounding quotes |
| `AUDIT_PILOT_CONFIG` | Path to an operator-maintained catalog/reviewer configuration JSON |
| `AUDIT_PILOT_HOME` | Persistent writable data directory outside the repository |
| `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | Existing eBay OAuth helper's credentials; never commit them |

The existing eBay helper also supports its ignored local environment files. Do not
put credentials in the catalog JSON. Missing credentials or failed authentication
produce an explicit error while Crowe evidence remains usable. There is no mock
or category-price fallback in genuine mode.

## Catalog and reviewer configuration

The default `config/internal-audit.example.json` describes the historically checked
auction #8166 (internal ID `48980`), selected page 1 and its exact Apollo filter,
order, pagination and search arguments. This completed auction is a historical
example, not evidence of current live-auction behavior.

For another auction, the host operator copies the example outside the repository
and sets `AUDIT_PILOT_CONFIG`. Supply the actual catalog URL, internal auction ID
and complete query arguments observed for that selected page. Active auctions can
have different filters. Do not guess them. A manually configured different page
must have matching URL and query context. The pilot never sweeps an auction.

Keep reviewer IDs stable and distinct; labels may be friendly names. The selector
is attribution, not authentication. Changing an ID does not migrate old history.
Changing the configuration does not silently replace a restored queue: the app
shows the loaded auction separately from the configuration for the next load.
The reviewers do not edit raw JSON to navigate lots or candidates.

## Storage and recovery

By default, Windows data lives under `%LOCALAPPDATA%\CroweAuditPilot`; Linux uses
`~/.local/share/CroweAuditPilot`. An explicit `AUDIT_PILOT_HOME` overrides this.
Data inside the repository and symlinked feedback/session files are rejected.

```text
CroweAuditPilot/
  demo/feedback.sqlite3
  demo/session-owner.json
  demo/session-buyer.json
  live/feedback.sqlite3
  live/session-owner.json
  live/session-buyer.json
```

Feedback uses the unchanged `FeedbackStore`: five-part source identities,
immutable evidence, independent reviewer histories, append-only corrections,
optimistic concurrency and stable event IDs. Live-mode candidates use original
Browse API item IDs. No rank/title/URL-derived identity or legacy log is used.

Per-reviewer JSON checkpoints retain the selected page, selected lot/candidate,
detail snapshots, all retrieved search sets and current outcomes. They are written
to a staged file, flushed, and atomically replaced. Recovery validates and rebuilds
the queue offline through the merged integration, using idempotent evidence writes.
Wrong-mode/corrupt checkpoints are disclosed rather than substituted with demo or
legacy data. A SQLite save and a queue checkpoint are separate operations: queue
failure does not erase a committed judgment. A visible warning identifies failure
to checkpoint; the previous file remains available.

Use one active window per reviewer for queue editing: two windows attributed to
the same reviewer have safe optimistic judgment conflicts, but their **queue
checkpoint is last-writer-wins**. Different reviewers have separate checkpoints.
Checkpoints are limited to 32 MiB, with an explicit warning when exceeded. No
automatic cleanup, schema migration, cross-auction queue archive or backup service
is included. Back up the whole data directory while the app is stopped. Disk
durability, access controls and backups remain host responsibilities.

## Tablet access on a private LAN (optional)

The normal launcher binds **127.0.0.1 only**. It is not remotely accessible.
For a trusted private network, use **`launch_internal_audit_lan.cmd`** and explicitly
answer Yes to its warning. It binds `0.0.0.0:8501` for that run. Refusal, cancellation
or a failed prompt does not opt in.

**This application has no user authentication. Anyone who can reach the port can
see evidence and act as either reviewer.** Use only a trusted private LAN. Do not
forward router ports, publish internet addresses, use tunnels or expose it on a
public/untrusted network. If Windows Firewall prompts, allow only the intended
private network and constrain access to the trusted subnet. No firewall rules are
installed by these launchers.

On the tablet, open `http://<host-private-IP>:8501` and bookmark it. `localhost` on
the tablet refers to the tablet itself, not the Windows host. Keep the host awake.
The LAN link is HTTP, not TLS; do not treat it as secure remote access.

## Images and responsive layout

The app uses native Streamlit columns and controls, supported key classes and two
scoped responsive selectors to stack the evidence panels below 950 CSS pixels.
The sidebar starts collapsed so the photographs get the browser width. Launcher
typography uses an 18px base; review buttons have a 48px minimum height.

Only HTTPS image URLs on the existing known source hosts are displayed:
`bids.crauctions.com`, `as-assets.marknetalliance.com`, `i.ebayimg.com`. Userinfo,
nonstandard ports and unrelated hosts are rejected. One reasonable variant is
selected at a time; galleries are not bulk-downloaded. The browser loads remote
URLs directly; the server does not proxy images or broaden acquisition access.
The image and source links remain available when browser blocking, expiry or
missing variants prevent display. Browser-side image failures cannot reliably be
detected by AppTest; a visible fallback explanation is always provided.

No stock/packaging classification or physical condition is inferred from photo
order. Descriptions display as plain text, with scripts/styles stripped when the
source only provides HTML. Source condition attributes retain unknown/null values.

## Validation and manual acceptance checklist

```sh
/workspace/pythonprojects-venv/bin/python -B -m unittest discover -s tests -p test_internal_validation_ui.py -v
/workspace/pythonprojects-venv/bin/python -B -m unittest discover -s tests -v
```

Automated tests use AppTest, mocked source responses and temporary stores. They
block socket connections and test both demo and genuine-mode paths without live
credentials. The existing regression suite is included.

Headless Chromium was actually used against the localhost offline demo at
1440×1100 (desktop), 1180×820 (tablet landscape), 820×1180 (tablet portrait) and
600×1000. Screenshots were inspected: two columns at the wide sizes, stacked
columns at the narrow sizes, no document-width overflow, 18.9px evidence text,
and minimum 48px review buttons. These are desktop-browser viewport simulations,
not physical iPad/Android or touch-device certification. Review screenshots are
generated artifacts outside the repository.

Before a real pilot, the owner and buyer should verify:

- [ ] Windows double-click opens the browser from a repository path containing spaces.
- [ ] Local launcher is unreachable from the tablet; LAN launcher requires opt-in.
- [ ] Both reviewers can find the sidebar and their attribution remains obvious.
- [ ] Desktop and landscape show large, readable side-by-side evidence.
- [ ] Portrait stacks cleanly; scrolling, pinch zoom, keyboard and photo dialog work.
- [ ] Touch navigation, rejection reasons, notes and Save are comfortable without precision taps.
- [ ] Actual Crowe images load or show understandable fallback behavior.
- [ ] An authentic eBay query returns real IDs/links and separate currency/shipping values.
- [ ] Closing/reopening the app restores the queue and corrected judgment history.
- [ ] A second window's competing correction triggers the conflict explanation.

Live eBay authentication/search, current Crowe structures, remote image delivery,
Windows execution and real tablet ergonomics remain unverified in this increment.
No new network permissions, public deployment, financial-model changes or commercial
frontend architecture are part of this pilot.
