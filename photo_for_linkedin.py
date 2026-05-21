import streamlit as st
from PIL import Image, ImageDraw, ImageOps
import io
import base64
import json
from html import escape
import streamlit.components.v1 as components

st.set_page_config(page_title="Me zo?", layout="wide")

# ---------------------------------------------------------------------------
# Global CSS — hide the uploader's file list & pagination, etc.
# ---------------------------------------------------------------------------
st.markdown("""
<style>
[data-testid="stFileUploader"] [data-testid="stFileUploaderFileList"],
[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"],
[data-testid="stFileUploader"] [data-testid="stFileUploaderFileData"],
[data-testid="stFileUploader"] [data-testid="stFileUploaderPagination"],
[data-testid="stFileUploader"] section ~ * { display: none !important; }
/* Buttons whose label starts with the bridge marker — belt-and-braces hide */
.pp-anchor { scroll-margin-top: 24px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CIRCLE_SIZE = 360
THUMB_SIZE = 88
PICK_THUMB = 64
POSTER_NAME = "Your Future Self"

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _init_state():
    defaults = {
        "current_index":      0,
        "favorites":          {},      # filename -> circular PIL image
        "img_settings":       {},      # filename -> {offset_x, offset_y, zoom}
        "deleted":            set(),
        "preview_idx":        0,
        "winner_celebrated":  False,
        "last_deleted":       None,    # {"name","was_favorite","fav_img","from_lineup"}
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
_init_state()

# ---------------------------------------------------------------------------
# Surface a "just saved" toast from a previous run (only on first save)
# ---------------------------------------------------------------------------
if st.session_state.pop("show_save_toast", False):
    st.toast("Scroll down for the LinkedIn preview 👇", icon="✨")


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------
def crop_circle_from_settings(pil_img: Image.Image, settings: dict, size: int = 400) -> Image.Image:
    img = ImageOps.exif_transpose(pil_img)
    W, H = img.size
    zoom = max(1.0, float(settings.get("zoom", 1.0)))
    offset_x = float(settings.get("offset_x", 0.0))
    offset_y = float(settings.get("offset_y", 0.0))

    base_min = min(W, H)
    crop_size = base_min / zoom

    max_off_x = (W - crop_size) / 2.0
    max_off_y = (H - crop_size) / 2.0
    offset_x = max(-max_off_x, min(max_off_x, offset_x))
    offset_y = max(-max_off_y, min(max_off_y, offset_y))

    center_x = W / 2.0 - offset_x
    center_y = H / 2.0 - offset_y

    side = int(round(crop_size))
    left = int(round(center_x - crop_size / 2.0))
    top = int(round(center_y - crop_size / 2.0))
    left = max(0, min(left, W - side))
    top = max(0, min(top, H - side))

    cropped = img.crop((left, top, left + side, top + side)).convert("RGB")
    cropped = cropped.resize((size, size), Image.Resampling.LANCZOS)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size))
    out.paste(cropped, (0, 0), mask=mask)
    return out


@st.cache_data(show_spinner=False)
def file_main_b64(file_bytes: bytes, _key: str, max_dim: int = 1400) -> str:
    img = Image.open(io.BytesIO(file_bytes))
    img = ImageOps.exif_transpose(img)
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


@st.cache_data(show_spinner=False)
def file_thumb_b64(file_bytes: bytes, _key: str, max_dim: int = 220) -> str:
    img = Image.open(io.BytesIO(file_bytes))
    img = ImageOps.exif_transpose(img)
    img.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode("ascii")


@st.cache_data(show_spinner=False)
def file_dims(file_bytes: bytes, _key: str):
    img = Image.open(io.BytesIO(file_bytes))
    img = ImageOps.exif_transpose(img)
    return img.size


def pil_to_png_b64(pil_img: Image.Image) -> str:
    b = io.BytesIO()
    pil_img.save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    "<h1 style='font-size:64px; font-weight:800; margin:0 0 10px 0; letter-spacing:-0.5px; line-height:1.05;'>"
    "✨ Me zo?"
    "</h1>"
    "<p style='font-size:26px; font-weight:700; color:#0a66c2; margin:0 0 8px 0; letter-spacing:.2px;'>"
    "Small picture, big deal."
    "</p>"
    "<p style='font-style:italic; color:#333; font-size:20px; margin:0;'>"
    "Here to help you choose the best version of yourself.<sup>*</sup>"
    "</p>"
    "<p style='color:#888; font-size:16px; margin:4px 0 0 0;'>"
    "* Results limited to whichever face you actually own."
    "</p>"
    "<p style='font-size:17px; color:#222; margin:18px 0 0 0; line-height:1.55;'>"
    "Drop in a few photos, frame each one inside the LinkedIn circle "
    "(drag to pan, scroll to zoom), shortlist your favourites, and preview "
    "them on a real-looking profile and post."
    "</p>",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Upload  (label collapsed so Streamlit's "Drag and drop files here" stands alone)
# ---------------------------------------------------------------------------
uploaded_files = st.file_uploader(
    label="upload",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

st.caption(
    "🔒 Your photos stay in your browser only — nothing is saved. "
)

if not uploaded_files:
    st.stop()

# Initialise per-file settings
for f in uploaded_files:
    if f.name not in st.session_state.img_settings:
        st.session_state.img_settings[f.name] = {"offset_x": 0.0, "offset_y": 0.0, "zoom": 1.0}

active_queue = [
    f for f in uploaded_files
    if f.name not in st.session_state.favorites
    and f.name not in st.session_state.deleted
]
n_active = len(active_queue)

if n_active > 0:
    st.session_state.current_index = max(0, min(st.session_state.current_index, n_active - 1))
else:
    st.session_state.current_index = 0

n_fav = len(st.session_state.favorites)
if n_fav > 0:
    st.session_state.preview_idx = max(0, min(st.session_state.preview_idx, n_fav - 1))
else:
    st.session_state.preview_idx = 0
    st.session_state.winner_celebrated = False

total_alive = sum(1 for f in uploaded_files if f.name not in st.session_state.deleted)
n_saved = n_fav
n_deleted = len(st.session_state.deleted)


# ---------------------------------------------------------------------------
# Single bridge button — every iframe action flows through here via URL params.
# (We used to render one button per action; with N photos that paginated, which
# is exactly what produced the "Showing page X of Y" + the giant gap.)
# ---------------------------------------------------------------------------
def _file_by_name(name):
    for f in uploaded_files:
        if f.name == name:
            return f
    return None

def _handle_cmd(cmd: dict):
    a = cmd.get("a")
    if a == "focus":
        i = int(cmd.get("i", 0))
        if 0 <= i < n_active:
            st.session_state.current_index = i
    elif a == "prev" and n_active > 1:
        st.session_state.current_index = (st.session_state.current_index - 1) % n_active
    elif a == "next" and n_active > 1:
        st.session_state.current_index = (st.session_state.current_index + 1) % n_active
    elif a == "save" and n_active > 0:
        cur = active_queue[st.session_state.current_index]
        settings = st.session_state.img_settings[cur.name]
        circle = crop_circle_from_settings(Image.open(cur), settings, size=400)
        was_empty = len(st.session_state.favorites) == 0
        st.session_state.favorites[cur.name] = circle
        st.session_state.preview_idx = list(st.session_state.favorites.keys()).index(cur.name)
        if was_empty:
            # Subtle peek down (only on the very first save) + toast pip
            st.session_state.show_save_toast = True
            st.session_state.scroll_peek = True
    elif a == "delete" and n_active > 0:
        cur = active_queue[st.session_state.current_index]
        st.session_state.last_deleted = {
            "name": cur.name,
            "was_favorite": cur.name in st.session_state.favorites,
            "fav_img": st.session_state.favorites.get(cur.name),
            "from_lineup": False,
        }
        st.session_state.deleted.add(cur.name)
        st.session_state.favorites.pop(cur.name, None)
    elif a == "pick":
        i = int(cmd.get("i", 0))
        if 0 <= i < n_fav:
            st.session_state.preview_idx = i
    elif a == "pick_prev" and n_fav > 1:
        st.session_state.preview_idx = (st.session_state.preview_idx - 1) % n_fav
    elif a == "pick_next" and n_fav > 1:
        st.session_state.preview_idx = (st.session_state.preview_idx + 1) % n_fav
    elif a == "commit":
        name = cmd.get("n")
        if name and name in st.session_state.img_settings:
            st.session_state.img_settings[name] = {
                "offset_x": float(cmd.get("ox", 0.0)),
                "offset_y": float(cmd.get("oy", 0.0)),
                "zoom":     float(cmd.get("z", 1.0)),
            }


if st.button("__ppbridge::cmd", key="bridge_cmd"):
    raw = st.query_params.get("pp_cmd")
    if raw:
        try:
            _handle_cmd(json.loads(base64.urlsafe_b64decode(raw.encode()).decode()))
        except Exception:
            pass
        try:
            del st.query_params["pp_cmd"]
        except Exception:
            pass
    st.rerun()


# ---------------------------------------------------------------------------
# Photo-count line
# ---------------------------------------------------------------------------
count_parts = [f"📷 **{total_alive}** photo{'s' if total_alive != 1 else ''}"]
if n_active:  count_parts.append(f"**{n_active}** in queue")
if n_saved:   count_parts.append(f"**{n_saved}** in the lineup")
if n_deleted: count_parts.append(f"**{n_deleted}** discarded")
st.markdown(" · ".join(count_parts))

# Undo last delete
ld = st.session_state.last_deleted
if ld:
    undo_col, _ = st.columns([3, 7])
    with undo_col:
        if st.button(f"↩ Undo deleting **{ld['name']}**", key="undo_delete_btn"):
            st.session_state.deleted.discard(ld["name"])
            if ld.get("was_favorite") and ld.get("fav_img") is not None:
                st.session_state.favorites[ld["name"]] = ld["fav_img"]
            st.session_state.last_deleted = None
            st.rerun()


# ---------------------------------------------------------------------------
# Tip line
# ---------------------------------------------------------------------------
if n_active > 0:
    st.markdown(
        "💡 **Tip** · scroll wheel or **＋ / −** to zoom · "
        "click side frames or press **← / →** to flip through your queue."
    )


# ---------------------------------------------------------------------------
# Main filmstrip + interactive circle
# ---------------------------------------------------------------------------
if n_active > 0:
    current_index = st.session_state.current_index
    current_file = active_queue[current_index]

    active_b64 = file_main_b64(current_file.getvalue(), current_file.name)
    active_W, active_H = file_dims(current_file.getvalue(), current_file.name)
    active_settings = st.session_state.img_settings[current_file.name]

    side_slots = []
    for delta in (-2, -1, 1, 2):
        if n_active <= 1:
            side_slots.append({"delta": delta, "exists": False})
            continue
        ni = (current_index + delta) % n_active
        if ni == current_index:
            side_slots.append({"delta": delta, "exists": False})
        else:
            f = active_queue[ni]
            side_slots.append({
                "delta": delta, "exists": True, "idx": ni, "name": f.name,
                "b64": file_thumb_b64(f.getvalue(), f.name),
            })

    payload = {
        "circle_size": CIRCLE_SIZE,
        "thumb_size":  THUMB_SIZE,
        "active": {
            "name": current_file.name,
            "b64":  active_b64,
            "W": active_W, "H": active_H,
            "settings": active_settings,
        },
        "side_slots": side_slots,
        "nav_enabled": n_active > 1,
    }
    payload_json = json.dumps(payload)

    iframe_html = """<!DOCTYPE html><html><head><style>
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: transparent; }

.pp-wrap { display: flex; align-items: center; justify-content: center; gap: 12px; padding: 18px 8px 8px 8px; }
.pp-arrow {
    flex: 0 0 auto;
    width: 52px; height: 220px;
    display: flex; align-items: center; justify-content: center;
    font-size: 34px; color: #444; cursor: pointer;
    background: #fff; border: 1px solid #ccc; border-radius: 12px;
    user-select: none;
    transition: background .15s ease, border-color .15s ease;
}
.pp-arrow:hover { background: #f4f4f4; border-color: #888; }
.pp-arrow.pp-disabled { opacity: .25; cursor: not-allowed; }

.pp-sides { flex: 0 0 auto; display: flex; align-items: center; gap: 10px; }
.pp-side {
    flex: 0 0 auto;
    width: __TS__px; height: __TS__px;
    border-radius: 50%; overflow: hidden;
    cursor: pointer; background: #fff;
    border: 3px solid #d8d8d8;
    transition: transform .15s ease, border-color .15s ease, opacity .15s ease;
}
.pp-sides.pp-left  .pp-side:nth-child(1) { opacity: .55; transform: scale(.85); }
.pp-sides.pp-left  .pp-side:nth-child(2) { opacity: .85; transform: scale(.95); }
.pp-sides.pp-right .pp-side:nth-child(1) { opacity: .85; transform: scale(.95); }
.pp-sides.pp-right .pp-side:nth-child(2) { opacity: .55; transform: scale(.85); }
.pp-side img { width: 100%; height: 100%; object-fit: cover; display: block; -webkit-user-drag: none; user-select: none; }
.pp-side:hover { border-color: #888; transform: scale(1.04); opacity: 1; }
.pp-side.pp-empty { background: transparent; border: 2px dashed #d8d8d8; cursor: default; opacity: .25; }
.pp-side.pp-empty:hover { transform: scale(.85); border-color: #d8d8d8; opacity: .25; }

.pp-center {
    flex: 0 0 auto;
    width: __CS__px; height: __CS__px;
    border-radius: 50%; overflow: hidden;
    background: #111; position: relative;
    border: 5px solid #0a66c2;
    box-shadow: 0 0 36px rgba(10, 102, 194, .35);
    cursor: grab; user-select: none; touch-action: none;
}
.pp-center.pp-grabbing { cursor: grabbing; }
.pp-center img {
    position: absolute; left: 50%; top: 50%;
    max-width: none; max-height: none;
    will-change: transform; pointer-events: none;
    -webkit-user-drag: none; user-select: none;
}

.pp-grid { position: absolute; inset: 0; pointer-events: none; opacity: 0; transition: opacity .18s ease; z-index: 2; }
.pp-center.pp-grabbing .pp-grid { opacity: 1; }
.pp-grid-line { position: absolute; background: rgba(255, 255, 255, 0.85); box-shadow: 0 0 4px rgba(0, 0, 0, 0.55); }
.pp-grid-h { left: 0; right: 0; height: 1px; }
.pp-grid-v { top: 0;  bottom: 0; width: 1px; }

.pp-name { text-align: center; margin-top: 10px; font-size: 13px; color: #555; font-weight: 500; }

.pp-controls { display: flex; justify-content: center; align-items: center; gap: 28px; padding: 12px 0 4px 0; flex-wrap: wrap; }
.pp-zoom-group { display: flex; align-items: center; gap: 8px; }
.pp-zoom-btn {
    width: 42px; height: 42px; border-radius: 50%;
    border: 1px solid #ccc; background: #fff; color: #333;
    font-size: 22px; font-weight: 700; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    line-height: 1; padding: 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    transition: background .15s ease, transform .1s ease, border-color .15s ease;
}
.pp-zoom-btn:hover { background: #f4f4f4; border-color: #888; }
.pp-zoom-btn:active { transform: scale(.93); }
.pp-zoom-label { font-size: 12px; color: #888; margin-right: 4px; }

.pp-action-group { display: flex; align-items: center; gap: 10px; }
.pp-save-btn, .pp-delete-btn {
    border: none; border-radius: 8px;
    padding: 10px 22px; font-size: 14px; font-weight: 600; cursor: pointer;
    transition: background .15s ease, transform .1s ease, border-color .15s ease;
}
.pp-save-btn  { background: #0a66c2; color: #fff; box-shadow: 0 2px 8px rgba(10,102,194,.3); }
.pp-save-btn:hover  { background: #084a8e; }
.pp-save-btn:active { transform: scale(.97); }
.pp-delete-btn { background: #fff; color: #c0392b; border: 2px solid #c0392b; }
.pp-delete-btn:hover  { background: #fdecea; }
.pp-delete-btn:active { transform: scale(.97); }
</style></head>
<body>
<div class="pp-wrap" id="ppWrap">
    <div class="pp-arrow" id="ppArrowLeft" title="Previous (← Arrow Key)">◀</div>
    <div class="pp-sides pp-left" id="ppSidesLeft"></div>
    <div class="pp-center" id="ppCenter">
        <img id="ppImg" src="" alt="" />
        <div class="pp-grid" aria-hidden="true">
            <div class="pp-grid-line pp-grid-h" style="top:33.333%"></div>
            <div class="pp-grid-line pp-grid-h" style="top:66.666%"></div>
            <div class="pp-grid-line pp-grid-v" style="left:33.333%"></div>
            <div class="pp-grid-line pp-grid-v" style="left:66.666%"></div>
        </div>
    </div>
    <div class="pp-sides pp-right" id="ppSidesRight"></div>
    <div class="pp-arrow" id="ppArrowRight" title="Next (→ Arrow Key)">▶</div>
</div>

<div class="pp-name" id="ppNameTag"></div>

<div class="pp-controls">
    <div class="pp-zoom-group">
        <span class="pp-zoom-label">Size</span>
        <button class="pp-zoom-btn" id="ppZoomOut" title="Zoom out">−</button>
        <button class="pp-zoom-btn" id="ppZoomIn"  title="Zoom in">＋</button>
    </div>
    <div class="pp-action-group">
        <button class="pp-save-btn"   id="ppSaveBtn">🎬 Add to lineup</button>
        <button class="pp-delete-btn" id="ppDeleteBtn">🗑 Discard</button>
    </div>
</div>

<script>
const DATA = __PAYLOAD__;
const parentDoc = window.parent.document;

const CS = DATA.circle_size;
const active = DATA.active;
const W = active.W, H = active.H;
const baseMin = Math.min(W, H);

let zoom    = active.settings.zoom     || 1.0;
let offsetX = active.settings.offset_x || 0.0;
let offsetY = active.settings.offset_y || 0.0;

const centerEl  = document.getElementById('ppCenter');
const imgEl     = document.getElementById('ppImg');
const nameTagEl = document.getElementById('ppNameTag');

imgEl.src = 'data:image/jpeg;base64,' + active.b64;
nameTagEl.textContent = active.name;

function clampOffsets() {
    const cropSrc = baseMin / zoom;
    const maxOX = Math.max(0, (W - cropSrc) / 2);
    const maxOY = Math.max(0, (H - cropSrc) / 2);
    offsetX = Math.max(-maxOX, Math.min(maxOX, offsetX));
    offsetY = Math.max(-maxOY, Math.min(maxOY, offsetY));
}
function render() {
    clampOffsets();
    const es = (CS / baseMin) * zoom;
    imgEl.style.width  = (W * es) + 'px';
    imgEl.style.height = (H * es) + 'px';
    const dx = offsetX * es, dy = offsetY * es;
    imgEl.style.transform = 'translate(calc(-50% + ' + dx + 'px), calc(-50% + ' + dy + 'px))';
}

function findBridge() {
    const btns = parentDoc.querySelectorAll('button');
    for (const b of btns) {
        if ((b.textContent || '').trim() === '__ppbridge::cmd') return b;
    }
    return null;
}
function dispatch(cmd) {
    try {
        const enc = btoa(JSON.stringify(cmd));
        const url = new URL(window.parent.location.href);
        url.searchParams.set('pp_cmd', enc);
        window.parent.history.replaceState({}, '', url);
        window.parent.dispatchEvent(new PopStateEvent('popstate'));
    } catch (e) {}
    const b = findBridge();
    if (b && !b.disabled) b.click();
}

let commitTimer = null;
function commitState(immediate) {
    const doCommit = () => {
        dispatch({a: 'commit', n: active.name, ox: offsetX, oy: offsetY, z: zoom});
    };
    if (immediate) {
        if (commitTimer) { clearTimeout(commitTimer); commitTimer = null; }
        doCommit();
    } else {
        if (commitTimer) clearTimeout(commitTimer);
        commitTimer = setTimeout(doCommit, 280);
    }
}

// Drag-to-pan (mouse)
let dragging = false, lastX = 0, lastY = 0, didMove = false;
centerEl.addEventListener('mousedown', (e) => {
    dragging = true; didMove = false;
    lastX = e.clientX; lastY = e.clientY;
    centerEl.classList.add('pp-grabbing');
    e.preventDefault();
});
window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const dx = e.clientX - lastX, dy = e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    const es = (CS / baseMin) * zoom;
    offsetX += dx / es; offsetY += dy / es;
    didMove = true; render();
});
window.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    centerEl.classList.remove('pp-grabbing');
    if (didMove) commitState(true);
});

// Touch
centerEl.addEventListener('touchstart', (e) => {
    if (e.touches.length !== 1) return;
    dragging = true; didMove = false;
    lastX = e.touches[0].clientX; lastY = e.touches[0].clientY;
}, { passive: false });
centerEl.addEventListener('touchmove', (e) => {
    if (!dragging || e.touches.length !== 1) return;
    const dx = e.touches[0].clientX - lastX, dy = e.touches[0].clientY - lastY;
    lastX = e.touches[0].clientX; lastY = e.touches[0].clientY;
    const es = (CS / baseMin) * zoom;
    offsetX += dx / es; offsetY += dy / es;
    didMove = true; render();
    e.preventDefault();
}, { passive: false });
centerEl.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    if (didMove) commitState(true);
});

// Wheel zoom
centerEl.addEventListener('wheel', (e) => {
    e.preventDefault();
    const before = zoom;
    zoom = Math.max(1.0, Math.min(4.0, zoom - e.deltaY * 0.0018));
    if (zoom !== before) { render(); commitState(false); }
}, { passive: false });

// +/- buttons
document.getElementById('ppZoomIn').addEventListener('click', () => {
    zoom = Math.min(4.0, zoom + 0.25); render(); commitState(true);
});
document.getElementById('ppZoomOut').addEventListener('click', () => {
    zoom = Math.max(1.0, zoom - 0.25); render(); commitState(true);
});

// Arrows
const arrowL = document.getElementById('ppArrowLeft');
const arrowR = document.getElementById('ppArrowRight');
arrowL.classList.toggle('pp-disabled', !DATA.nav_enabled);
arrowR.classList.toggle('pp-disabled', !DATA.nav_enabled);
arrowL.addEventListener('click', () => {
    if (arrowL.classList.contains('pp-disabled')) return;
    commitState(true);
    setTimeout(() => dispatch({a: 'prev'}), 100);
});
arrowR.addEventListener('click', () => {
    if (arrowR.classList.contains('pp-disabled')) return;
    commitState(true);
    setTimeout(() => dispatch({a: 'next'}), 100);
});

// Side thumbnails
function buildSide(slot) {
    if (!slot.exists) {
        const el = document.createElement('div'); el.className = 'pp-side pp-empty'; return el;
    }
    const el = document.createElement('div'); el.className = 'pp-side'; el.title = slot.name;
    const img = document.createElement('img');
    img.src = 'data:image/jpeg;base64,' + slot.b64; img.alt = '';
    el.appendChild(img);
    el.addEventListener('click', () => {
        commitState(true);
        setTimeout(() => dispatch({a: 'focus', i: slot.idx}), 100);
    });
    return el;
}
const sidesLeft  = document.getElementById('ppSidesLeft');
const sidesRight = document.getElementById('ppSidesRight');
DATA.side_slots.filter(s => s.delta < 0).sort((a,b) => a.delta - b.delta)
    .forEach(s => sidesLeft.appendChild(buildSide(s)));
DATA.side_slots.filter(s => s.delta > 0).sort((a,b) => a.delta - b.delta)
    .forEach(s => sidesRight.appendChild(buildSide(s)));

// Save / Discard
document.getElementById('ppSaveBtn').addEventListener('click', () => {
    commitState(true);
    setTimeout(() => dispatch({a: 'save'}), 120);
});
document.getElementById('ppDeleteBtn').addEventListener('click', () => {
    dispatch({a: 'delete'});
});

// Keyboard
function handleKey(e) {
    const t = e.target;
    const tag = (t && t.tagName) ? t.tagName.toLowerCase() : '';
    if (tag === 'input' || tag === 'textarea' || (t && t.isContentEditable)) return;
    if (!DATA.nav_enabled) return;
    if (e.key === 'ArrowLeft') {
        e.preventDefault(); commitState(true);
        setTimeout(() => dispatch({a: 'prev'}), 100);
    } else if (e.key === 'ArrowRight') {
        e.preventDefault(); commitState(true);
        setTimeout(() => dispatch({a: 'next'}), 100);
    }
}
document.addEventListener('keydown', handleKey);
if (!parentDoc.__ppKeyMain) {
    parentDoc.__ppKeyMain = true;
    parentDoc.addEventListener('keydown', handleKey);
}
function attachToIframes() {
    try {
        parentDoc.querySelectorAll('iframe').forEach(frame => {
            try {
                const fdoc = frame.contentDocument;
                if (fdoc && fdoc !== document && !fdoc.__ppKeyAttached) {
                    fdoc.__ppKeyAttached = true;
                    fdoc.addEventListener('keydown', handleKey);
                }
            } catch (err) {}
        });
    } catch (err) {}
}
attachToIframes();
if (!parentDoc.__ppIframeKeyObs) {
    parentDoc.__ppIframeKeyObs = true;
    new MutationObserver(attachToIframes).observe(parentDoc.body, { childList: true, subtree: true });
}

// Hide the single Streamlit bridge button
function hideBridgeButtons() {
    parentDoc.querySelectorAll('button').forEach(b => {
        const t = (b.textContent || '').trim();
        if (t.startsWith('__ppbridge::')) {
            const wrap = b.closest('div[data-testid="stButton"]') || b.parentElement;
            if (wrap) wrap.style.display = 'none';
        }
    });
}
hideBridgeButtons();
if (!parentDoc.__ppBridgeObs) {
    parentDoc.__ppBridgeObs = true;
    new MutationObserver(hideBridgeButtons).observe(parentDoc.body, { childList: true, subtree: true });
}

render();
try { window.focus(); } catch (e) {}
</script>
</body></html>
"""
    iframe_html = (iframe_html
                   .replace("__CS__", str(CIRCLE_SIZE))
                   .replace("__TS__", str(THUMB_SIZE))
                   .replace("__PAYLOAD__", payload_json))
    components.html(iframe_html, height=CIRCLE_SIZE + 180)


# ---------------------------------------------------------------------------
# 👑 Winner celebration
# ---------------------------------------------------------------------------
if n_active == 0 and n_fav == 1:
    if not st.session_state.winner_celebrated:
        st.balloons()
        st.session_state.winner_celebrated = True

    _winner_name, _winner_pic = next(iter(st.session_state.favorites.items()))
    _w_b64 = pil_to_png_b64(_winner_pic)
    st.markdown(f"""
    <div style="text-align:center; padding:18px 0 6px 0;">
        <div style="display:inline-block; position:relative; padding-top: 50px;">
            <div style="position:absolute; top:-6px; left:50%; transform:translateX(-50%); font-size:60px;
                        text-shadow: 0 4px 10px rgba(255,200,0,.45);">👑</div>
            <img src="data:image/png;base64,{_w_b64}"
                 style="width:220px; height:220px; border-radius:50%;
                        border: 6px solid #f7c531; box-shadow: 0 0 50px rgba(255,200,0,.55);" />
        </div>
        <h2 style="margin:14px 0 4px 0; color:#b8860b;">We have a winner.</h2>
        <p style="color:#555; margin:0;">Looks like the people have spoken. Time to flex.</p>
    </div>
    """, unsafe_allow_html=True)
else:
    st.session_state.winner_celebrated = False


# ---------------------------------------------------------------------------
# LinkedIn-style mock-up section
# ---------------------------------------------------------------------------
st.markdown('<div id="pp-preview-anchor" class="pp-anchor"></div>', unsafe_allow_html=True)
st.markdown("---")
st.markdown("### 🌐 How it would look on your LinkedIn profile")

if n_fav == 0:
    st.info(
        "Nothing in the lineup yet. Hit **🎬 Add to lineup** on a photo above "
        "and your future LinkedIn self will show up here."
    )
else:
    fav_items = list(st.session_state.favorites.items())
    favs_b64 = [(n, pil_to_png_b64(img)) for n, img in fav_items]
    sel_idx = st.session_state.preview_idx

    # -- Picture selector (now with arrows; clicks/arrows route through the cmd bridge)
    pick_thumbs_html = ""
    for i, (n, b64) in enumerate(favs_b64):
        is_active = (i == sel_idx)
        cls = "pp-pick" + (" pp-pick-active" if is_active else "")
        short = n if len(n) <= 18 else n[:15] + "…"
        pick_thumbs_html += (
            f'<div class="{cls}" data-action="pick" data-idx="{i}" title="{escape(n)}">'
            f'<img src="data:image/png;base64,{b64}" alt="" draggable="false" />'
            f'<div class="pp-pick-name">{escape(short)}</div>'
            f'</div>'
        )

    nav_disabled = "pp-disabled" if n_fav <= 1 else ""
    selector_html = """<!DOCTYPE html><html><head><style>
* { box-sizing: border-box; }
body { margin: 0; padding: 10px 4px 6px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: transparent; }
.pp-pick-row { display: flex; align-items: center; gap: 10px; overflow-x: auto; padding: 4px; scrollbar-width: thin; }
.pp-pick-row::-webkit-scrollbar { height: 8px; }
.pp-pick-row::-webkit-scrollbar-thumb { background: #bbb; border-radius: 4px; }
.pp-pick-arrow {
    flex: 0 0 auto;
    width: 36px; height: __PT__px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; color: #555; cursor: pointer;
    background: #fff; border: 1px solid #ccc; border-radius: 8px;
    user-select: none;
    transition: background .15s ease, border-color .15s ease;
}
.pp-pick-arrow:hover { background: #f4f4f4; border-color: #888; }
.pp-pick-arrow.pp-disabled { opacity: .25; cursor: not-allowed; }
.pp-pick {
    flex: 0 0 auto; width: __PT__px; text-align: center; cursor: pointer;
    border: 2px solid transparent; border-radius: 8px; padding: 4px;
    transition: transform .12s ease, border-color .12s ease, background .12s ease;
}
.pp-pick img {
    width: __PT__px; height: __PT__px;
    border-radius: 50%; object-fit: cover;
    border: 2px solid #eee; background: #fff; display: block;
}
.pp-pick:hover { transform: translateY(-2px); border-color: #aaa; }
.pp-pick-active { border-color: #0a66c2; background: rgba(10,102,194,.08); transform: scale(1.05); }
.pp-pick-active img { border-color: #0a66c2; }
.pp-pick-name { font-size: 10px; color: #555; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pp-pick-active .pp-pick-name { color: #0a66c2; font-weight: 700; }
</style></head>
<body>
<div class="pp-pick-row">
    <div class="pp-pick-arrow __NAVDIS__" data-action="pick_prev" title="Previous">◀</div>
    __THUMBS__
    <div class="pp-pick-arrow __NAVDIS__" data-action="pick_next" title="Next">▶</div>
</div>
<script>
const parentDoc = window.parent.document;
function findBridge() {
    const btns = parentDoc.querySelectorAll('button');
    for (const b of btns) {
        if ((b.textContent || '').trim() === '__ppbridge::cmd') return b;
    }
    return null;
}
function dispatch(cmd) {
    try {
        const enc = btoa(JSON.stringify(cmd));
        const url = new URL(window.parent.location.href);
        url.searchParams.set('pp_cmd', enc);
        window.parent.history.replaceState({}, '', url);
        window.parent.dispatchEvent(new PopStateEvent('popstate'));
    } catch (e) {}
    const b = findBridge();
    if (b && !b.disabled) b.click();
}
document.querySelectorAll('[data-action]').forEach(el => {
    el.addEventListener('click', () => {
        if (el.classList.contains('pp-disabled')) return;
        const a = el.getAttribute('data-action');
        if (a === 'pick') dispatch({a: 'pick', i: parseInt(el.getAttribute('data-idx'), 10)});
        else if (a === 'pick_prev') dispatch({a: 'pick_prev'});
        else if (a === 'pick_next') dispatch({a: 'pick_next'});
    });
});
function hideBridgeButtons() {
    parentDoc.querySelectorAll('button').forEach(b => {
        const t = (b.textContent || '').trim();
        if (t.startsWith('__ppbridge::')) {
            const wrap = b.closest('div[data-testid="stButton"]') || b.parentElement;
            if (wrap) wrap.style.display = 'none';
        }
    });
}
hideBridgeButtons();
</script>
</body></html>
"""
    selector_html = (selector_html
                     .replace("__PT__", str(PICK_THUMB))
                     .replace("__THUMBS__", pick_thumbs_html)
                     .replace("__NAVDIS__", nav_disabled))
    components.html(selector_html, height=PICK_THUMB + 60)

    # -- Per-picture actions (return / delete / download)
    sel_name, sel_pic = fav_items[sel_idx]
    sel_b64 = favs_b64[sel_idx][1]
    act_cols = st.columns([2, 2, 2, 5])
    with act_cols[0]:
        if st.button("↩ Return to queue", key="action_return", use_container_width=True,
                     help=f"Move '{sel_name}' back to the filmstrip"):
            st.session_state.favorites.pop(sel_name, None)
            st.rerun()
    with act_cols[1]:
        if st.button("🗑 Delete", key="action_delete", use_container_width=True,
                     help=f"Discard '{sel_name}' completely"):
            st.session_state.last_deleted = {
                "name": sel_name,
                "was_favorite": True,
                "fav_img": sel_pic,
                "from_lineup": True,
            }
            st.session_state.deleted.add(sel_name)
            st.session_state.favorites.pop(sel_name, None)
            st.rerun()
    with act_cols[2]:
        _dl_bytes = io.BytesIO(); sel_pic.save(_dl_bytes, format="PNG")
        safe_dl = "profile_" + ("".join(c for c in sel_name if c.isalnum() or c in "._-") or "image") + ".png"
        st.download_button(
            "💾 Download",
            data=_dl_bytes.getvalue(),
            file_name=safe_dl,
            mime="image/png",
            key="action_dl",
            use_container_width=True,
        )

    st.markdown("&nbsp;", unsafe_allow_html=True)

    # -- Side-by-side: profile card | imagined post
    funny_desc = (
        "Spent 47 hours picking this exact profile picture (worth it) · "
        "Aspiring overachiever · "
        "Currently optimising for likes per minute · "
        "Open to opportunities, lunch invites, and unsolicited LinkedIn advice"
    )
    banner_quote = "Humbled. Grateful. Inspired. Slightly bewildered."

    profile_html = """<!DOCTYPE html><html><head><style>
* { box-sizing: border-box; }
body { margin: 0; padding: 6px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: transparent; }
.pp-li-card { background: white; border-radius: 12px; border: 1px solid #e0e0e0; overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.pp-li-banner { height: 150px; position: relative;
    background: radial-gradient(120% 60% at 50% 100%, rgba(0,0,0,.35), transparent 60%),
                linear-gradient(135deg, #ffb37a 0%, #ff6a88 30%, #7b3aaa 65%, #1f3147 100%); }
.pp-li-banner::after { content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 55px;
    background: linear-gradient(to top, rgba(15,25,45,.85), transparent),
                repeating-linear-gradient(90deg, #1f3147 0 18px, #2a3e5e 18px 34px, #1f3147 34px 52px);
    clip-path: polygon(0% 100%, 4% 70%, 8% 85%, 12% 60%, 16% 78%, 22% 50%, 28% 72%, 34% 55%, 40% 78%, 46% 45%, 52% 70%, 58% 58%, 64% 75%, 70% 50%, 76% 72%, 82% 60%, 88% 78%, 94% 55%, 100% 70%, 100% 100%);
    opacity: .85; }
.pp-li-banner-text { position: absolute; right: 16px; bottom: 12px; z-index: 2;
    color: white; font-style: italic; font-weight: 500; font-size: 13px;
    max-width: 70%; text-align: right; letter-spacing: .2px;
    text-shadow: 0 1px 6px rgba(0,0,0,0.65); }
.pp-li-banner-text small { display: block; font-size: 10px; opacity: .85; font-style: normal; margin-top: 2px; font-weight: 400; }
.pp-li-content { padding: 0 20px 18px; position: relative; }
.pp-li-pic-wrap { position: absolute; left: 20px; top: -60px;
    width: 120px; height: 120px; border-radius: 50%; border: 4px solid white;
    overflow: hidden; background: white; box-shadow: 0 4px 14px rgba(0,0,0,0.12); }
.pp-li-pic { width: 100%; height: 100%; object-fit: cover; display: block; }
.pp-li-info { padding-top: 72px; }
.pp-li-name { font-size: 22px; font-weight: 700; color: #1a1a1a; margin: 0 0 4px 0; line-height: 1.2; }
.pp-li-headline { font-size: 13px; color: #1a1a1a; margin-bottom: 8px; line-height: 1.45; }
.pp-li-meta { font-size: 12px; color: #666; margin-bottom: 4px; }
.pp-li-meta a { color: #0a66c2; text-decoration: none; font-weight: 600; }
.pp-li-connections { font-size: 12px; margin-bottom: 12px; }
.pp-li-connections a { color: #0a66c2; text-decoration: none; font-weight: 700; }
.pp-li-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.pp-li-btn { border-radius: 16px; padding: 5px 14px; font-size: 12px;
    font-weight: 600; cursor: pointer; border: 1px solid; font-family: inherit; }
.pp-li-btn-primary   { background: #0a66c2; color: white;   border-color: #0a66c2; }
.pp-li-btn-secondary { background: white;   color: #0a66c2; border-color: #0a66c2; }
.pp-li-btn-ghost     { background: white;   color: #555;    border-color: #888; }
</style></head>
<body>
<div class="pp-li-card">
    <div class="pp-li-banner">
        <div class="pp-li-banner-text">&ldquo;__BANNER__&rdquo;<small>— me, on a Tuesday</small></div>
    </div>
    <div class="pp-li-content">
        <div class="pp-li-pic-wrap">
            <img class="pp-li-pic" src="data:image/png;base64,__PIC__" alt="" />
        </div>
        <div class="pp-li-info">
            <div class="pp-li-name">__NAME__</div>
            <div class="pp-li-headline">__DESC__</div>
            <div class="pp-li-meta">Haifa, Israel · <a href="#">Contact info</a></div>
            <div class="pp-li-connections"><a href="#">500+ connections</a></div>
            <div class="pp-li-actions">
                <button class="pp-li-btn pp-li-btn-primary">Open to</button>
                <button class="pp-li-btn pp-li-btn-secondary">Add profile section</button>
                <button class="pp-li-btn pp-li-btn-ghost">More</button>
            </div>
        </div>
    </div>
</div>
</body></html>
"""
    profile_html = (profile_html
                    .replace("__BANNER__", escape(banner_quote))
                    .replace("__PIC__", sel_b64)
                    .replace("__NAME__", escape(POSTER_NAME))
                    .replace("__DESC__", escape(funny_desc)))

    # -- Post mock with a single self-comment (same photo as the poster — the joke
    # works better when it's clearly the exact same face replying to itself)
    poster_b64 = sel_b64
    commenter_b64 = poster_b64
    SELF_COMMENT = "How exciting. Couldn't have written this without you (well, myself)."

    post_text = (
        "🎓 THRILLED, humbled, grateful, and ever-so-slightly delirious to announce "
        "that I have officially earned my degree!\n\n"
        "A massive thank-you to my three best friends:\n"
        "🤖 Claude — for the late-night pep talks\n"
        "🤖 Gemini — for the brainstorms (or at least the attempts)\n"
        "🤖 GPT — for editing every word I've ever written\n\n"
        "This is just the beginning. Big things ahead. The journey continues.\n"
        "(P.S. I am, of course, open to opportunities.)\n\n"
    )
    hashtags_html = (
        '<span class="pp-post-tags">'
        '#blessed #grateful #humbled #excitedtoannounce #journey #grindset #thoughtleader'
        '</span>'
    )

    comments_html = (
        f'<div class="pp-comment">'
        f'<img class="pp-comment-avatar" src="data:image/png;base64,{commenter_b64}" alt="" />'
        f'<div class="pp-comment-body">'
        f'<div class="pp-comment-bubble">'
        f'<div class="pp-comment-meta">'
        f'<span class="pp-comment-name">{escape(POSTER_NAME)}</span>'
        f'<span class="pp-comment-degree">· (also you)</span>'
        f'</div>'
        f'<div class="pp-comment-text">{escape(SELF_COMMENT)}</div>'
        f'</div>'
        f'<div class="pp-comment-actions">'
        f'<a href="#" class="pp-c-link">Like</a>'
        f'<span class="pp-c-dot">·</span>'
        f'<a href="#" class="pp-c-link">Reply</a>'
        f'</div></div></div>'
    )

    post_html = """<!DOCTYPE html><html><head><style>
* { box-sizing: border-box; }
body { margin: 0; padding: 6px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: transparent; }
.pp-post { background: white; border-radius: 12px; border: 1px solid #e0e0e0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06); padding: 14px 14px 6px; }
.pp-post-header { display: flex; align-items: flex-start; gap: 10px; }
.pp-post-avatar { width: 44px; height: 44px; border-radius: 50%; object-fit: cover; border: 1px solid #ddd; flex: 0 0 auto; }
.pp-post-author { flex: 1 1 auto; line-height: 1.3; }
.pp-post-name { font-weight: 700; color: #1a1a1a; font-size: 13px; }
.pp-post-conn { color: #666; font-weight: 500; font-size: 12px; }
.pp-post-title { font-size: 11px; color: #666; }
.pp-post-time { font-size: 11px; color: #888; margin-top: 2px; }
.pp-post-content { font-size: 13px; line-height: 1.5; color: #1a1a1a; margin: 10px 0; white-space: pre-wrap; }
.pp-post-tags { color: #0a66c2; font-weight: 600; }
.pp-post-reactions { display: flex; align-items: center; gap: 6px; padding: 6px 0;
    border-top: 1px solid #eee; font-size: 11px; color: #666; }
.pp-react-icons { font-size: 13px; letter-spacing: -1px; margin-right: 4px; }
.pp-react-stats { margin-left: auto; }
.pp-post-actions { display: flex; justify-content: space-around; padding: 4px 0;
    border-top: 1px solid #eee; border-bottom: 1px solid #eee; }
.pp-act-btn { background: none; border: none; cursor: pointer; padding: 6px 8px;
    color: #555; font-size: 12px; font-weight: 600; border-radius: 4px; }
.pp-act-btn:hover { background: #f4f4f4; color: #0a66c2; }
.pp-post-comments { padding-top: 10px; }
.pp-comment { display: flex; gap: 10px; margin-bottom: 12px; }
.pp-comment-avatar { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; flex: 0 0 auto; border: 1px solid #ddd; }
.pp-comment-body { flex: 1 1 auto; min-width: 0; }
.pp-comment-bubble { background: #f3f5f7; border-radius: 8px; padding: 7px 11px; }
.pp-comment-meta { display: flex; align-items: baseline; gap: 4px; }
.pp-comment-name { font-weight: 700; color: #1a1a1a; font-size: 12px; }
.pp-comment-degree { font-size: 10px; color: #888; font-style: italic; }
.pp-comment-text { font-size: 12px; color: #1a1a1a; margin-top: 4px; line-height: 1.4; }
.pp-comment-actions { display: flex; gap: 6px; align-items: center; font-size: 11px; padding: 4px 11px 0; color: #888; }
.pp-c-dot { color: #bbb; }
.pp-c-link { color: #666; text-decoration: none; font-weight: 600; }
.pp-c-link:hover { color: #0a66c2; }
</style></head>
<body>
<div class="pp-post">
    <div class="pp-post-header">
        <img class="pp-post-avatar" src="data:image/png;base64,__POSTER__" alt="" />
        <div class="pp-post-author">
            <div class="pp-post-name">__NAME__ <span class="pp-post-conn">· 1st</span></div>
            <div class="pp-post-title">Aspiring overachiever · Doing things, achieving stuff</div>
            <div class="pp-post-time">3h · 🌍</div>
        </div>
    </div>
    <div class="pp-post-content">__POSTTEXT____TAGS__</div>
    <div class="pp-post-reactions">
        <span class="pp-react-icons">👍 ❤️ 🎉</span>
        <span>Endorsed by 847 people who probably skimmed it</span>
        <span class="pp-react-stats">142 comments · 23 reposts</span>
    </div>
    <div class="pp-post-actions">
        <button class="pp-act-btn">👍 Like</button>
        <button class="pp-act-btn">💬 Comment</button>
        <button class="pp-act-btn">🔄 Repost</button>
        <button class="pp-act-btn">➤ Send</button>
    </div>
    <div class="pp-post-comments">__COMMENTS__</div>
</div>
</body></html>
"""
    post_html = (post_html
                 .replace("__POSTER__", poster_b64)
                 .replace("__NAME__",   escape(POSTER_NAME))
                 .replace("__POSTTEXT__", escape(post_text))
                 .replace("__TAGS__",   hashtags_html)
                 .replace("__COMMENTS__", comments_html))

    preview_cols = st.columns(2)
    with preview_cols[0]:
        st.caption("**Profile preview**")
        components.html(profile_html, height=440)
    with preview_cols[1]:
        st.caption("**Imagined post — starring you (and your alter-ego)**")
        components.html(post_html, height=620)


# ---------------------------------------------------------------------------
# Small peek-scroll after the very first save — short hop, not a full jump
# ---------------------------------------------------------------------------
if st.session_state.pop("scroll_peek", False):
    components.html(
        """<script>
        setTimeout(() => {
            const w = window.parent;
            const dy = Math.min(360, Math.max(220, w.innerHeight * 0.45));
            w.scrollBy({top: dy, left: 0, behavior: 'smooth'});
        }, 250);
        </script>""",
        height=0,
    )
