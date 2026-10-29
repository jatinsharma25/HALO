"""Renders the EyeSpy architecture diagram to PNG using matplotlib —
no external image tools needed, everything here is already in the venv."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D

FIG_W, FIG_H = 20, 11
fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=200)
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis("off")
fig.patch.set_facecolor("white")

# ── palette ──────────────────────────────────────────────────────────────
NAVY = "#1c2b3a"
GRAY = "#6b7280"
WHITE = "#ffffff"

LAYERS = {
    "sources": {"fill": "#eaf3fc", "edge": "#4a90d9", "title": "#1f4e79"},
    "ingest":  {"fill": "#f3eafc", "edge": "#9b6fd9", "title": "#5b2e91"},
    "ai":      {"fill": "#e9f7ef", "edge": "#4caf7d", "title": "#1f7a4d"},
    "app":     {"fill": "#fdf0e3", "edge": "#e08a3c", "title": "#a85c00"},
    "output":  {"fill": "#eaf3fc", "edge": "#4a90d9", "title": "#1f4e79"},
}


def layer_container(x, y, w, h, style, title, title_size=15.5):
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.15",
        linewidth=1.6, linestyle=(0, (5, 3)),
        edgecolor=style["edge"], facecolor=style["fill"], zorder=1,
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h - 0.28, title, ha="center", va="top",
             fontsize=title_size, fontweight="bold", color=style["title"], zorder=2,
             linespacing=1.25)


def item_box(cx, cy, w, h, title, sub, edge):
    box = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.015,rounding_size=0.1",
        linewidth=1.3, edgecolor=edge, facecolor=WHITE, zorder=3,
    )
    ax.add_patch(box)
    ax.text(cx, cy + h * 0.15, title, ha="center", va="center",
             fontsize=10.3, fontweight="bold", color=NAVY, wrap=True, zorder=4)
    ax.text(cx, cy - h * 0.28, sub, ha="center", va="center",
             fontsize=8.4, color=GRAY, wrap=True, zorder=4, linespacing=1.4)


def h_arrow(x1, x2, y, color=NAVY):
    ax.add_patch(FancyArrowPatch((x1, y), (x2, y), arrowstyle="-|>",
                 mutation_scale=14, linewidth=1.4, color=color, zorder=5))


def v_arrow(x, y1, y2, color=NAVY):
    ax.add_patch(FancyArrowPatch((x, y1), (x, y2), arrowstyle="-|>",
                 mutation_scale=14, linewidth=1.4, color=color, zorder=5))


# ── title ────────────────────────────────────────────────────────────────
ax.text(FIG_W / 2, FIG_H - 0.35, "EyeSpy — System Architecture",
         ha="center", va="top", fontsize=20, fontweight="bold", color=NAVY)
ax.text(FIG_W / 2, FIG_H - 0.85,
         "Person-class detection only · deterministic scoring · dual-signed evidence · hash-chained audit",
         ha="center", va="top", fontsize=10.5, color=GRAY, style="italic")

TOP = FIG_H - 1.25
BOTTOM = 0.4
MID_H = TOP - BOTTOM

# ── Video Sources (left column) ─────────────────────────────────────────
SRC_X, SRC_W = 0.3, 2.6
layer_container(SRC_X, BOTTOM, SRC_W, MID_H, LAYERS["sources"], "Video Sources", title_size=13.5)
src_items = [
    ("Existing CCTV", "IP / RTSP cameras\nindoor & outdoor"),
    ("USB Cameras /\nDashcams", "device index,\nlow-cost deployment"),
    ("Video Files", "pre-recorded,\nloops as live feed"),
]
src_cy = [TOP - 1.55, TOP - 3.55, TOP - 5.55]
for (t, s), cy in zip(src_items, src_cy):
    item_box(SRC_X + SRC_W / 2, cy, 2.2, 1.55, t, s, LAYERS["sources"]["edge"])

# ── three stacked pipeline layers ────────────────────────────────────────
GAP = 0.9
PIPE_X = SRC_X + SRC_W + 0.7
PIPE_W = 12.8
LAYER_H = (MID_H - 2 * GAP) / 3

layer_y = [BOTTOM + 2 * (LAYER_H + GAP), BOTTOM + (LAYER_H + GAP), BOTTOM]

# -- Ingestion layer --
layer_container(PIPE_X, layer_y[0], PIPE_W, LAYER_H, LAYERS["ingest"], "Data Ingestion & Preprocessing")
ing_items = [
    ("Frame Capture", "OpenCV, real-time,\nauto-reconnect on drop"),
    ("Frame\nPreprocessing", "resize to fixed\n1280×720 working res."),
    ("Camera Health\nMonitor", "blackout · frozen ·\nsevere blur (sustained)"),
]
n = len(ing_items)
step = PIPE_W / n
for i, (t, s) in enumerate(ing_items):
    cx = PIPE_X + step * (i + 0.5)
    item_box(cx, layer_y[0] + LAYER_H / 2 - 0.15, step - 0.5, LAYER_H - 0.75, t, s, LAYERS["ingest"]["edge"])
    if i < n - 1:
        h_arrow(cx + (step - 0.5) / 2, cx + step - (step - 0.5) / 2, layer_y[0] + LAYER_H / 2 - 0.15)

# -- AI & Analytics layer --
layer_container(PIPE_X, layer_y[1], PIPE_W, LAYER_H, LAYERS["ai"], "AI & Analytics")
ai_items = [
    ("YOLOv8n Detection", "person-class ONLY\n(COCO class 0)"),
    ("Centroid Tracking", "anonymous, camera-local\nIDs · entry/exit count"),
    ("Behaviour & Health\nRules", "zone · after-hours · loiter · fall\nabandoned · fire/smoke · line-\ncrossing · crowd"),
    ("Correlator &\nScoring Engine", "dedup 5-min window ·\ndeterministic score + why"),
]
n = len(ai_items)
step = PIPE_W / n
for i, (t, s) in enumerate(ai_items):
    cx = PIPE_X + step * (i + 0.5)
    item_box(cx, layer_y[1] + LAYER_H / 2 - 0.15, step - 0.45, LAYER_H - 0.75, t, s, LAYERS["ai"]["edge"])
    if i < n - 1:
        h_arrow(cx + (step - 0.45) / 2, cx + step - (step - 0.45) / 2, layer_y[1] + LAYER_H / 2 - 0.15)

# -- Application & Decision layer --
layer_container(PIPE_X, layer_y[2], PIPE_W, LAYER_H, LAYERS["app"], "Application & Decision")
app_items = [
    ("Web Dashboard", "live redacted feed,\nschematic, incident feed"),
    ("Evidence Engine", "redact → hash →\nsign (HMAC + Ed25519)"),
    ("Notifications", "Telegram\n(per-camera, configurable)"),
    ("Human\nVerification", "RBAC: Admin / Operator /\nResponder · ack→resolve"),
]
n = len(app_items)
step = PIPE_W / n
for i, (t, s) in enumerate(app_items):
    cx = PIPE_X + step * (i + 0.5)
    item_box(cx, layer_y[2] + LAYER_H / 2 - 0.15, step - 0.45, LAYER_H - 0.75, t, s, LAYERS["app"]["edge"])
    if i < n - 1:
        h_arrow(cx + (step - 0.45) / 2, cx + step - (step - 0.45) / 2, layer_y[2] + LAYER_H / 2 - 0.15)

# vertical arrows between stacked layers, full gap so they read clearly
v_arrow(PIPE_X + 1.4, layer_y[0] - 0.05, layer_y[0] - GAP + 0.15)
v_arrow(PIPE_X + 1.4, layer_y[1] - 0.05, layer_y[1] - GAP + 0.15)

# arrow: sources -> ingestion layer
h_arrow(SRC_X + SRC_W + 0.05, PIPE_X - 0.05, layer_y[0] + LAYER_H / 2 - 0.15)

# ── Output & Storage (right column) ─────────────────────────────────────
OUT_X = PIPE_X + PIPE_W + 0.7
OUT_W = 2.6
layer_container(OUT_X, BOTTOM, OUT_W, MID_H, LAYERS["output"], "Output & Storage", title_size=13.5)
out_items = [
    ("SQLite", "incidents, observations,\naudit log (Postgres\nmigration planned)"),
    ("JWT Auth", "python-jose + bcrypt ·\nrole-based access"),
    ("Evidence Store", "redacted preview +\nrole-protected original"),
    ("Hash-Chained\nAudit Log", "every action appends\none verifiable link"),
]
out_cy = [TOP - 1.35, TOP - 3.05, TOP - 4.85, TOP - 6.65]
for (t, s), cy in zip(out_items, out_cy):
    item_box(OUT_X + OUT_W / 2, cy, 2.2, 1.55, t, s, LAYERS["output"]["edge"])

# arrow: application layer -> output
h_arrow(PIPE_X + PIPE_W + 0.05, OUT_X - 0.05, layer_y[2] + LAYER_H / 2 - 0.15)

# ── footer note ──────────────────────────────────────────────────────────
ax.text(FIG_W / 2, BOTTOM - 0.18,
        "No face recognition · no biometric identity · no automated response — every incident is closed by a human.",
        ha="center", va="top", fontsize=9.5, color=GRAY, style="italic")

plt.tight_layout()
out_path = r"C:\Users\MRITTI~1\AppData\Local\Temp\claude\e--securevistaworking\c3c7e46a-a267-4108-ab9d-c270fffc83ff\scratchpad\eyespy-architecture.png"
plt.savefig(out_path, dpi=200, facecolor="white", bbox_inches="tight")
print("saved:", out_path)
