import streamlit as st
from PIL import Image, ImageDraw, ImageOps
import io
import base64
import json
from html import escape
import streamlit.components.v1 as components

st.set_page_config(page_title="Profile Picture Studio", layout="wide")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CIRCLE_SIZE = 360     # interactive center circle (display px)
THUMB_SIZE = 88       # side filmstrip thumbnails (display px)
BOARD_THUMB = 150     # comparison-board circle thumbnails

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "current_index" not in st.session_state:
    st.session_state.current_index = 0
if "favorites" not in st.session_state:
    st.session_state.favorites = {}        # filename -> circular PIL image
if "img_settings" not in st.session_state:
    st.session_state.img_settings = {}     # filename -> {offset_x, offset_y, zoom} (source-pixel units)


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------
def crop_circle_from_settings(pil_img: Image.Image, settings: dict, size: int = 400) -> Image.Image:
    """Compute the final circular crop from per-image pan/zoom settings."""
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
    """High-res base64 for the interactive center circle."""
    img = Image.open(io.BytesIO(file_bytes))
    img = ImageOps.exif_transpose(img)
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


@st.cache_data(show_spinner=False)
def file_thumb_b64(file_bytes: bytes, _key: str, max_dim: int = 220) -> str:
    """Small base64 thumbnail for the filmstrip side slots."""
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


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("📸 Profile Picture Comparison Studio")
st.caption(
    "Drag the photo inside the circle to pan · scroll or use ＋ / − to zoom · "
    "click side frames or press ← / → to flip through your queue."
)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload all the photos you are debating between",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("💡 Studio is ready. Upload a collection of pictures above to begin!")
    st.stop()

# Initialise per-file settings
for f in uploaded_files:
    if f.name not in st.session_state.img_settings:
        st.session_state.img_settings[f.name] = {"offset_x": 0.0, "offset_y": 0.0, "zoom": 1.0}

# Active filmstrip queue: every uploaded file that is NOT pinned to the board
active_queue = [f for f in uploaded_files if f.name not in st.session_state.favorites]
n_active = len(active_queue)

if n_active > 0:
    st.session_state.current_index = max(0, min(st.session_state.current_index, n_active - 1))
else:
    st.session_state.current_index = 0


# ---------------------------------------------------------------------------
# Hidden bridge buttons — clicked by the iframe JS to drive backend state
# ---------------------------------------------------------------------------
if n_active > 0:
    if st.button(
        "__ppbridge::prev", key="bridge_prev",
        disabled=(st.session_state.current_index == 0),
    ):
        st.session_state.current_index -= 1
        st.rerun()
    if st.button(
        "__ppbridge::next", key="bridge_next",
        disabled=(st.session_state.current_index == n_active - 1),
    ):
        st.session_state.current_index += 1
        st.rerun()
    for idx in range(n_active):
        if st.button(f"__ppbridge::focus::{idx}", key=f"bridge_focus_{idx}"):
            st.session_state.current_index = idx
            st.rerun()

# Commit pan/zoom state passed via URL query param
if st.button("__ppbridge::commit", key="bridge_commit"):
    raw = st.query_params.get("pp_st")
    if raw:
        try:
            payload = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
            name = payload.get("name")
            if name and name in st.session_state.img_settings:
                st.session_state.img_settings[name] = {
                    "offset_x": float(payload.get("ox", 0.0)),
                    "offset_y": float(payload.get("oy", 0.0)),
                    "zoom":     float(payload.get("z", 1.0)),
                }
        except Exception:
            pass
        try:
            del st.query_params["pp_st"]
        except Exception:
            pass
    st.rerun()

# Save the current active image to the comparison board
if st.button("__ppbridge::save", key="bridge_save"):
    if n_active > 0:
        cur = active_queue[st.session_state.current_index]
        settings = st.session_state.img_settings[cur.name]
        circle = crop_circle_from_settings(Image.open(cur), settings, size=400)
        st.session_state.favorites[cur.name] = circle
    st.rerun()

# Unpin (return) bridges — one per favorite slot, by index
for u_idx in range(len(st.session_state.favorites)):
    if st.button(f"__ppbridge::unpin::{u_idx}", key=f"bridge_unpin_{u_idx}"):
        keys = list(st.session_state.favorites.keys())
        if u_idx < len(keys):
            del st.session_state.favorites[keys[u_idx]]
        st.rerun()


# ---------------------------------------------------------------------------
# Main filmstrip + interactive circle (single HTML/JS component)
# ---------------------------------------------------------------------------
if n_active > 0:
    current_index = st.session_state.current_index
    current_file = active_queue[current_index]

    active_b64 = file_main_b64(current_file.getvalue(), current_file.name)
    active_W, active_H = file_dims(current_file.getvalue(), current_file.name)
    active_settings = st.session_state.img_settings[current_file.name]

    # Build the four side slots: deltas -2, -1, +1, +2 relative to current
    side_slots = []
    for delta in (-2, -1, 1, 2):
        ni = current_index + delta
        if 0 <= ni < n_active:
            f = active_queue[ni]
            side_slots.append({
                "delta": delta,
                "exists": True,
                "idx": ni,
                "name": f.name,
                "b64": file_thumb_b64(f.getvalue(), f.name),
            })
        else:
            side_slots.append({"delta": delta, "exists": False})

    payload = {
        "circle_size": CIRCLE_SIZE,
        "thumb_size": THUMB_SIZE,
        "active": {
            "name": current_file.name,
            "b64": active_b64,
            "W": active_W,
            "H": active_H,
            "settings": active_settings,
        },
        "side_slots": side_slots,
        "prev_disabled": current_index == 0,
        "next_disabled": current_index == n_active - 1,
    }
    payload_json = json.dumps(payload)

    iframe_html = """<!DOCTYPE html><html><head><style>
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
body { background: transparent; }

.pp-wrap {
    display: flex; align-items: center; justify-content: center;
    gap: 12px;
    padding: 18px 8px 8px 8px;
}
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

.pp-sides {
    flex: 0 0 auto;
    display: flex; align-items: center; gap: 10px;
}

.pp-side {
    flex: 0 0 auto;
    width: __TS__px; height: __TS__px;
    border-radius: 50%; overflow: hidden;
    cursor: pointer;
    border: 3px solid #d8d8d8;
    background: #fff;
    transition: transform .15s ease, border-color .15s ease, opacity .15s ease;
}
.pp-side:nth-child(1) { opacity: .55; transform: scale(.85); }
.pp-side:nth-child(2) { opacity: .85; transform: scale(.95); }
.pp-sides.pp-right .pp-side:nth-child(1) { opacity: .85; transform: scale(.95); }
.pp-sides.pp-right .pp-side:nth-child(2) { opacity: .55; transform: scale(.85); }
.pp-side img { width: 100%; height: 100%; object-fit: cover; display: block; -webkit-user-drag: none; user-select: none; }
.pp-side:hover { border-color: #888; transform: scale(1.04); opacity: 1; }
.pp-side.pp-empty {
    background: transparent; border: 2px dashed #d8d8d8; cursor: default;
    opacity: .35;
}
.pp-side.pp-empty:hover { transform: scale(.85); border-color: #d8d8d8; opacity: .35; }

.pp-center {
    flex: 0 0 auto;
    width: __CS__px; height: __CS__px;
    border-radius: 50%; overflow: hidden;
    background: #111;
    position: relative;
    border: 5px solid #FF4B4B;
    box-shadow: 0 0 36px rgba(255, 75, 75, .35);
    cursor: grab;
    user-select: none;
    touch-action: none;
}
.pp-center.pp-grabbing { cursor: grabbing; }
.pp-center img {
    position: absolute;
    left: 50%; top: 50%;
    max-width: none; max-height: none;
    will-change: transform;
    pointer-events: none;
    -webkit-user-drag: none;
    user-select: none;
}
.pp-zoom-controls {
    position: absolute; right: 12px; bottom: 12px;
    display: flex; flex-direction: column; gap: 8px;
    z-index: 5;
}
.pp-zoom-btn {
    width: 38px; height: 38px;
    border-radius: 50%; border: none;
    background: rgba(0,0,0,0.62); color: #fff;
    font-size: 22px; font-weight: 700;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    line-height: 1; padding: 0;
    transition: background .15s ease, transform .1s ease;
}
.pp-zoom-btn:hover { background: rgba(0,0,0,0.82); }
.pp-zoom-btn:active { transform: scale(.92); }

.pp-name {
    text-align: center;
    margin-top: 6px;
    font-size: 12px; color: #666;
}

.pp-save-row {
    display: flex; justify-content: center; padding: 10px 0 4px 0;
}
.pp-save-btn {
    background: #FF4B4B; color: #fff;
    border: none; border-radius: 8px;
    padding: 10px 26px; font-size: 15px; font-weight: 600;
    cursor: pointer;
    box-shadow: 0 2px 8px rgba(255,75,75,.3);
    transition: background .15s ease, transform .1s ease;
}
.pp-save-btn:hover { background: #ff2c2c; }
.pp-save-btn:active { transform: scale(.97); }
</style></head>
<body>
<div class="pp-wrap" id="ppWrap">
    <div class="pp-arrow" id="ppArrowLeft" title="Previous (← Arrow Key)">◀</div>
    <div class="pp-sides pp-left" id="ppSidesLeft"></div>
    <div>
        <div class="pp-center" id="ppCenter">
            <img id="ppImg" src="" alt="" />
            <div class="pp-zoom-controls">
                <button class="pp-zoom-btn" id="ppZoomIn"  title="Zoom in (scroll up)">＋</button>
                <button class="pp-zoom-btn" id="ppZoomOut" title="Zoom out (scroll down)">−</button>
            </div>
        </div>
        <div class="pp-name" id="ppNameTag"></div>
    </div>
    <div class="pp-sides pp-right" id="ppSidesRight"></div>
    <div class="pp-arrow" id="ppArrowRight" title="Next (→ Arrow Key)">▶</div>
</div>
<div class="pp-save-row">
    <button class="pp-save-btn" id="ppSaveBtn">⭐ Save to Comparison Board</button>
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
    const dx = offsetX * es;
    const dy = offsetY * es;
    imgEl.style.transform = 'translate(calc(-50% + ' + dx + 'px), calc(-50% + ' + dy + 'px))';
}

function clickBridge(label) {
    const btns = parentDoc.querySelectorAll('button');
    for (const b of btns) {
        if ((b.textContent || '').trim() === label) {
            if (b.disabled) return false;
            b.click();
            return true;
        }
    }
    return false;
}

let commitTimer = null;
function commitState(immediate) {
    const doCommit = () => {
        const obj = { name: active.name, ox: offsetX, oy: offsetY, z: zoom };
        try {
            const enc = btoa(JSON.stringify(obj));
            const url = new URL(window.parent.location.href);
            url.searchParams.set('pp_st', enc);
            window.parent.history.replaceState({}, '', url);
        } catch (e) {}
        clickBridge('__ppbridge::commit');
    };
    if (immediate) {
        if (commitTimer) { clearTimeout(commitTimer); commitTimer = null; }
        doCommit();
    } else {
        if (commitTimer) clearTimeout(commitTimer);
        commitTimer = setTimeout(doCommit, 280);
    }
}

// --- Drag to pan (mouse) ---
let dragging = false;
let lastX = 0, lastY = 0;
let didMove = false;

centerEl.addEventListener('mousedown', (e) => {
    if (e.target.classList && e.target.classList.contains('pp-zoom-btn')) return;
    dragging = true; didMove = false;
    lastX = e.clientX; lastY = e.clientY;
    centerEl.classList.add('pp-grabbing');
    e.preventDefault();
});
window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    const es = (CS / baseMin) * zoom;
    offsetX += dx / es;
    offsetY += dy / es;
    didMove = true;
    render();
});
window.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    centerEl.classList.remove('pp-grabbing');
    if (didMove) commitState(true);
});

// --- Drag to pan (touch) ---
centerEl.addEventListener('touchstart', (e) => {
    if (e.touches.length !== 1) return;
    dragging = true; didMove = false;
    lastX = e.touches[0].clientX; lastY = e.touches[0].clientY;
}, { passive: false });
centerEl.addEventListener('touchmove', (e) => {
    if (!dragging || e.touches.length !== 1) return;
    const dx = e.touches[0].clientX - lastX;
    const dy = e.touches[0].clientY - lastY;
    lastX = e.touches[0].clientX; lastY = e.touches[0].clientY;
    const es = (CS / baseMin) * zoom;
    offsetX += dx / es;
    offsetY += dy / es;
    didMove = true;
    render();
    e.preventDefault();
}, { passive: false });
centerEl.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    if (didMove) commitState(true);
});

// --- Scroll wheel zoom ---
centerEl.addEventListener('wheel', (e) => {
    e.preventDefault();
    const before = zoom;
    zoom = Math.max(1.0, Math.min(4.0, zoom - e.deltaY * 0.0018));
    if (zoom !== before) {
        render();
        commitState(false);
    }
}, { passive: false });

// --- +/- buttons ---
document.getElementById('ppZoomIn').addEventListener('click', (e) => {
    e.stopPropagation();
    zoom = Math.min(4.0, zoom + 0.25);
    render();
    commitState(true);
});
document.getElementById('ppZoomOut').addEventListener('click', (e) => {
    e.stopPropagation();
    zoom = Math.max(1.0, zoom - 0.25);
    render();
    commitState(true);
});

// --- Arrows ---
const arrowL = document.getElementById('ppArrowLeft');
const arrowR = document.getElementById('ppArrowRight');
arrowL.classList.toggle('pp-disabled', !!DATA.prev_disabled);
arrowR.classList.toggle('pp-disabled', !!DATA.next_disabled);
arrowL.addEventListener('click', () => {
    if (arrowL.classList.contains('pp-disabled')) return;
    commitState(true);
    setTimeout(() => clickBridge('__ppbridge::prev'), 60);
});
arrowR.addEventListener('click', () => {
    if (arrowR.classList.contains('pp-disabled')) return;
    commitState(true);
    setTimeout(() => clickBridge('__ppbridge::next'), 60);
});

// --- Side thumbnails ---
function buildSide(slot) {
    if (!slot.exists) {
        const el = document.createElement('div');
        el.className = 'pp-side pp-empty';
        return el;
    }
    const el = document.createElement('div');
    el.className = 'pp-side';
    el.title = slot.name;
    const img = document.createElement('img');
    img.src = 'data:image/jpeg;base64,' + slot.b64;
    img.alt = '';
    el.appendChild(img);
    el.addEventListener('click', () => {
        commitState(true);
        setTimeout(() => clickBridge('__ppbridge::focus::' + slot.idx), 60);
    });
    return el;
}
const sidesLeft  = document.getElementById('ppSidesLeft');
const sidesRight = document.getElementById('ppSidesRight');
const leftSlots  = DATA.side_slots.filter(s => s.delta < 0).sort((a,b) => a.delta - b.delta); // -2, -1
const rightSlots = DATA.side_slots.filter(s => s.delta > 0).sort((a,b) => a.delta - b.delta); // +1, +2
leftSlots .forEach(s => sidesLeft .appendChild(buildSide(s)));
rightSlots.forEach(s => sidesRight.appendChild(buildSide(s)));

// --- Save button ---
document.getElementById('ppSaveBtn').addEventListener('click', () => {
    commitState(true);
    setTimeout(() => clickBridge('__ppbridge::save'), 100);
});

// --- Keyboard navigation (← / →) ---
function handleKey(e) {
    const t = e.target;
    const tag = (t && t.tagName) ? t.tagName.toLowerCase() : '';
    if (tag === 'input' || tag === 'textarea' || (t && t.isContentEditable)) return;
    if (e.key === 'ArrowLeft') {
        e.preventDefault();
        commitState(true);
        setTimeout(() => clickBridge('__ppbridge::prev'), 60);
    } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        commitState(true);
        setTimeout(() => clickBridge('__ppbridge::next'), 60);
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
            } catch (err) { /* cross-origin */ }
        });
    } catch (err) {}
}
attachToIframes();
if (!parentDoc.__ppIframeKeyObs) {
    parentDoc.__ppIframeKeyObs = true;
    new MutationObserver(attachToIframes)
        .observe(parentDoc.body, { childList: true, subtree: true });
}

// --- Hide the Streamlit bridge buttons (parent doc) ---
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
    new MutationObserver(hideBridgeButtons)
        .observe(parentDoc.body, { childList: true, subtree: true });
}

// First paint
render();

// Try to focus the iframe so arrow keys work without needing a click first
try { window.focus(); } catch (e) {}
</script>
</body></html>
"""
    iframe_html = (iframe_html
                   .replace("__CS__", str(CIRCLE_SIZE))
                   .replace("__TS__", str(THUMB_SIZE))
                   .replace("__PAYLOAD__", payload_json))

    # height = circle + name caption + save row + outer padding
    components.html(iframe_html, height=CIRCLE_SIZE + 140)

else:
    st.success("🎉 Every photo is pinned to the board! Compare your finalists below and pick a winner.")


# ---------------------------------------------------------------------------
# Comparison board: fixed-size, side-by-side, scrollable, no matter how many
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### ⚖️ Comparison Board")

if st.session_state.favorites:
    cards = []
    for i, (name, img) in enumerate(st.session_state.favorites.items()):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        safe_dl = "profile_" + ("".join(c for c in name if c.isalnum() or c in "._-") or "image") + ".png"
        cards.append(
            f'<div class="pp-card">'
            f'<img class="pp-card-img" src="data:image/png;base64,{b64}" alt="" />'
            f'<div class="pp-card-name">{escape(name)}</div>'
            f'<div class="pp-card-actions">'
            f'<a class="pp-card-act" href="data:image/png;base64,{b64}" '
            f'download="{escape(safe_dl)}" title="Download PNG">💾</a>'
            f'<span class="pp-card-act pp-card-unpin" data-idx="{i}" title="Return to queue">↩</span>'
            f'</div>'
            f'</div>'
        )

    board_html = """<!DOCTYPE html><html><head><style>
body { margin: 0; padding: 4px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: transparent; }
.pp-strip {
    display: flex; flex-direction: row; flex-wrap: nowrap;
    gap: 16px; overflow-x: auto; padding: 8px 4px 14px 4px;
    scrollbar-width: thin;
}
.pp-strip::-webkit-scrollbar { height: 8px; }
.pp-strip::-webkit-scrollbar-thumb { background: #bbb; border-radius: 4px; }
.pp-card {
    flex: 0 0 auto;
    width: __BT__px;
    text-align: center;
}
.pp-card-img {
    width: __BT__px; height: __BT__px;
    border-radius: 50%; object-fit: cover;
    border: 3px solid #eee; background: #fff;
    display: block;
}
.pp-card-name {
    font-size: 11px; color: #444; margin-top: 6px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pp-card-actions {
    display: flex; justify-content: center; gap: 10px; margin-top: 6px;
}
.pp-card-act {
    display: inline-flex; align-items: center; justify-content: center;
    width: 32px; height: 32px;
    border-radius: 50%; background: #f4f4f4;
    text-decoration: none; cursor: pointer;
    font-size: 14px; color: #333;
    border: 1px solid #ddd;
    transition: background .15s ease, transform .1s ease;
}
.pp-card-act:hover { background: #e8e8e8; transform: scale(1.07); }
.pp-card-act:active { transform: scale(.95); }
</style></head>
<body>
<div class="pp-strip">__CARDS__</div>
<script>
const parentDoc = window.parent.document;
function clickBridge(label) {
    const btns = parentDoc.querySelectorAll('button');
    for (const b of btns) {
        if ((b.textContent || '').trim() === label) {
            if (b.disabled) return false;
            b.click(); return true;
        }
    }
    return false;
}
document.querySelectorAll('.pp-card-unpin').forEach(el => {
    el.addEventListener('click', () => {
        clickBridge('__ppbridge::unpin::' + el.getAttribute('data-idx'));
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
    board_html = (board_html
                  .replace("__BT__", str(BOARD_THUMB))
                  .replace("__CARDS__", "".join(cards)))
    components.html(board_html, height=BOARD_THUMB + 100)
else:
    st.info("Your comparison board is empty. Hit **Save to Comparison Board** to pin your favorites here.")
