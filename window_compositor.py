import base64
import io
import json
import math
import os
from datetime import datetime

import numpy as np
from PIL import Image

from overlay import _warp_rgba_overlay, cv2_to_pil, pil_to_cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMPOSITE_OUTPUT_DIR = os.path.join(BASE_DIR, "outputs", "composites")
_asset_rgba_cache: dict[str, np.ndarray] = {}


def _asset_rgba_array(asset: dict) -> np.ndarray:
    path = asset.get("path") or asset["id"]
    mtime = os.path.getmtime(path) if path and os.path.exists(path) else 0
    cache_key = f"{path}:{mtime}"
    cached = _asset_rgba_cache.get(cache_key)
    if cached is not None:
        return cached
    rgba = np.array(asset["image"].convert("RGBA"))
    _asset_rgba_cache[cache_key] = rgba
    return rgba


def image_to_data_uri(
    image: Image.Image,
    *,
    prefer_jpeg: bool = True,
    jpeg_quality: int = 82,
) -> str:
    buffer = io.BytesIO()
    use_jpeg = prefer_jpeg and image.mode in ("RGB", "L")
    if use_jpeg:
        save_image = image if image.mode == "RGB" else image.convert("RGB")
        save_image.save(buffer, format="JPEG", quality=jpeg_quality, optimize=False)
        mime = "image/jpeg"
    else:
        save_image = image.convert("RGBA") if image.mode not in ("RGBA", "LA") else image
        save_image.save(buffer, format="PNG", compress_level=3)
        mime = "image/png"
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_window_compositor_html(
    *,
    background_data_uri: str,
    background_width: int,
    background_height: int,
    assets: list[dict],
    initial_layers: list[dict] | None = None,
    selected_layer_id: str | None = None,
    remount_nonce: int = 0,
) -> str:
    palette_items = []
    for asset in assets:
        palette_items.append(
            {
                "id": asset["id"],
                "label": asset["label"],
                "category": asset["category"],
                "src": asset.get("data_uri") or image_to_data_uri(asset["image"]),
                "width": asset["width"],
                "height": asset["height"],
            }
        )

    payload = {
        "background": {
            "src": background_data_uri,
            "width": background_width,
            "height": background_height,
        },
        "palette": palette_items,
        "layers": initial_layers or [],
        "selectedLayerId": selected_layer_id,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    payload_json = payload_json.replace("</", "<\\/")

    return f"""
<!DOCTYPE html>
<!-- compositor-ui-v26 remount={remount_nonce} -->
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: "Segoe UI", sans-serif;
    background: #fcfbfa;
    color: #1c2434;
    -webkit-text-size-adjust: 100%;
  }}
  .wrap {{
    display: grid;
    grid-template-columns: 300px 1fr;
    gap: 16px;
    padding: 8px 4px 12px 4px;
    min-height: 680px;
  }}
  .palette {{
    border: 1px solid #e5e0d8;
    border-radius: 12px;
    background: #fff;
    padding: 12px;
    overflow-y: auto;
    max-height: 820px;
  }}
  .palette h3 {{
    margin: 0 0 10px 0;
    font-size: 0.95rem;
    color: #1c2434;
    font-weight: 600;
  }}
  .palette-group {{
    margin-bottom: 16px;
  }}
  .palette-item {{
    border: 1px solid #e5e0d8;
    border-radius: 10px;
    background: #faf9f7;
    padding: 10px;
    margin-bottom: 10px;
    cursor: grab;
    user-select: none;
    touch-action: manipulation;
  }}
  .palette-item:active {{ cursor: grabbing; }}
  .palette-item img {{
    width: 100%;
    height: 160px;
    object-fit: contain;
    display: block;
    pointer-events: none;
    background: #fff;
    border-radius: 6px;
  }}
  .palette-item span {{
    display: block;
    margin-top: 8px;
    font-size: 0.84rem;
    text-align: center;
    color: #3d4a5c;
    font-weight: 500;
  }}
  .stage-panel {{
    border: 1px solid #e5e0d8;
    border-radius: 12px;
    background: #fff;
    padding: 12px;
    min-width: 0;
  }}
  .toolbar {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
    margin-bottom: 10px;
  }}
  .toolbar button {{
    border: 1px solid #e5e0d8;
    background: #fff;
    color: #1c2434;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 0.82rem;
    cursor: pointer;
    touch-action: manipulation;
  }}
  .toolbar button.primary {{
    background: linear-gradient(180deg, #2f3848 0%, #1c2434 100%);
    color: #fff;
    border-color: #3d4a5c;
  }}
  .zoom-controls {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    margin-left: auto;
    border: 1px solid #e5e0d8;
    border-radius: 8px;
    padding: 2px 4px;
    background: #faf9f7;
  }}
  .zoom-controls button {{
    min-width: 36px;
    min-height: 36px;
    padding: 4px 8px;
    font-size: 1rem;
    font-weight: 600;
  }}
  .zoom-label {{
    min-width: 48px;
    text-align: center;
    font-size: 0.78rem;
    color: #475569;
    font-weight: 600;
  }}
  .stage-shell {{
    overflow: auto;
    border: 1px dashed #d8d2c8;
    border-radius: 10px;
    background: #f7f5f1;
    padding: 10px;
    max-height: min(72vh, 820px);
    -webkit-overflow-scrolling: touch;
    touch-action: pan-x pan-y;
  }}
  .stage-shell.is-dragging,
  .stage-shell.is-pinching {{
    touch-action: none;
  }}
  .zoom-spacer {{
    position: relative;
    overflow: visible;
  }}
  .stage {{
    position: relative;
    display: inline-block;
    transform-origin: top left;
    will-change: transform;
  }}
  .photo-clip {{
    position: absolute;
    left: 0;
    top: 0;
    overflow: hidden;
    z-index: 1;
  }}
  .layers-root {{
    position: absolute;
    inset: 0;
    z-index: 2;
  }}
  #uiOverlay {{
    position: absolute;
    left: 0;
    top: 0;
    z-index: 50;
    pointer-events: none;
  }}
  #handleOverlay {{
    position: absolute;
    inset: 0;
    z-index: 3000;
    pointer-events: none;
    overflow: visible;
  }}
  .stage-bg {{
    display: block;
    max-width: none;
    user-select: none;
    pointer-events: none;
    -webkit-user-drag: none;
  }}
  .layer {{
    position: absolute;
    cursor: move;
    user-select: none;
    touch-action: none;
    overflow: visible;
  }}
  .layer-canvas {{
    position: absolute;
    left: 0;
    top: 0;
    display: block;
    width: 100%;
    height: 100%;
    touch-action: none;
    z-index: 1;
    pointer-events: auto;
  }}
  .layer-img {{
    position: absolute;
    left: 0;
    top: 0;
    display: block;
    width: 100%;
    height: 100%;
    object-fit: fill;
    touch-action: none;
    z-index: 1;
    pointer-events: auto;
    user-select: none;
    -webkit-user-drag: none;
    backface-visibility: hidden;
    -webkit-backface-visibility: hidden;
    transform-style: preserve-3d;
  }}
  .version-badge {{
    position: absolute;
    right: 8px;
    top: 8px;
    z-index: 5000;
    padding: 2px 8px;
    border-radius: 999px;
    background: rgba(29, 78, 216, 0.92);
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    pointer-events: none;
  }}
  .corner-handle {{
    position: absolute;
    width: 14px;
    height: 14px;
    background: #fff;
    border: 2px solid #b8956a;
    border-radius: 50%;
    touch-action: none;
    pointer-events: auto;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.28);
    z-index: 1;
  }}
  .corner-handle.nw {{ cursor: nwse-resize; }}
  .corner-handle.ne {{ cursor: nesw-resize; }}
  .corner-handle.se {{ cursor: nwse-resize; }}
  .corner-handle.sw {{ cursor: nesw-resize; }}
  .edge-handle {{
    position: absolute;
    background: #fff;
    border: 2px solid #2563eb;
    border-radius: 4px;
    touch-action: none;
    pointer-events: auto;
    box-shadow: 0 1px 5px rgba(0, 0, 0, 0.22);
    z-index: 2;
  }}
  .edge-handle.top {{
    width: 22px;
    height: 8px;
    cursor: ns-resize;
  }}
  .edge-handle.right {{
    width: 8px;
    height: 22px;
    cursor: ew-resize;
  }}
  .hint {{
    margin-top: 8px;
    font-size: 0.82rem;
    color: #6b7280;
    line-height: 1.45;
  }}
  .mobile-hint {{
    display: none;
    margin-top: 6px;
    font-size: 0.82rem;
    color: #1d4ed8;
    line-height: 1.45;
  }}
  .toolbar button:disabled {{
    opacity: 0.65;
    cursor: wait;
  }}
  .status-banner {{
    display: none;
    margin-bottom: 10px;
    padding: 10px 12px;
    border-radius: 8px;
    background: #eef6ff;
    border: 1px solid #bfdbfe;
    color: #1d4ed8;
    font-size: 0.84rem;
    font-weight: 600;
  }}
  .status-banner.active {{
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .status-banner.active::before {{
    content: "";
    width: 16px;
    height: 16px;
    border: 2px solid #93c5fd;
    border-top-color: #1d4ed8;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex: 0 0 auto;
  }}
  @keyframes spin {{
    to {{ transform: rotate(360deg); }}
  }}
  @media (max-width: 768px) {{
    .wrap {{
      grid-template-columns: 1fr;
      min-height: auto;
      padding: 4px 2px 8px 2px;
    }}
    .palette {{
      max-height: none;
      overflow-x: auto;
      overflow-y: hidden;
      white-space: nowrap;
      padding: 10px 8px;
    }}
    .palette-group {{
      display: inline-block;
      vertical-align: top;
      width: 132px;
      margin-right: 10px;
      margin-bottom: 0;
      white-space: normal;
    }}
    .palette-item {{
      padding: 8px;
      margin-bottom: 8px;
    }}
    .palette-item img {{
      height: 92px;
    }}
    .toolbar button {{
      min-height: 40px;
      padding: 8px 12px;
      font-size: 0.88rem;
    }}
    .zoom-controls {{
      width: 100%;
      margin-left: 0;
      justify-content: center;
    }}
    .stage-shell {{
      max-height: min(58vh, 640px);
    }}
    .corner-handle {{
      width: 28px;
      height: 28px;
      border-width: 3px;
    }}
    .edge-handle.top {{
      width: 34px;
      height: 12px;
    }}
    .edge-handle.right {{
      width: 12px;
      height: 34px;
    }}
    .hint {{
      display: none;
    }}
    .mobile-hint {{
      display: block;
    }}
  }}
</style>
</head>
<body>
  <div class="wrap">
    <aside class="palette" id="palette"></aside>
    <section class="stage-panel">
      <div class="status-banner" id="statusBanner">🔄 합성 이미지 적용 중...</div>
      <div class="toolbar">
        <button type="button" class="primary" id="exportBtn">합성 이미지 적용</button>
        <button type="button" id="deleteBtn">선택 삭제</button>
        <button type="button" id="clearBtn">전체 초기화</button>
        <div class="zoom-controls">
          <button type="button" id="zoomOutBtn" title="축소">−</button>
          <span class="zoom-label" id="zoomLabel">100%</span>
          <button type="button" id="zoomInBtn" title="확대">+</button>
          <button type="button" id="zoomResetBtn" title="화면 맞춤">맞춤</button>
        </div>
      </div>
      <div class="stage-shell" id="stageShell">
        <div class="zoom-spacer" id="zoomSpacer">
          <div class="stage" id="stage">
            <div class="photo-clip" id="photoClip">
              <div class="version-badge">합성기 v26 · 자동저장</div>
              <img class="stage-bg" id="stageBg" alt="매장 외부 사진" />
              <div class="layers-root" id="layersRoot"></div>
              <canvas id="uiOverlay"></canvas>
            </div>
            <div id="handleOverlay"></div>
          </div>
        </div>
      </div>
      <p class="hint">배치 후 「합성 이미지 적용」을 누르면 **점선·핸들 없이** 화면 그대로 캡처해 저장합니다. 사진 밖으로 내린 시트지는 잘립니다.</p>
      <p class="mobile-hint">📱 탭으로 추가 · 모서리 원근 · **상단/우측 핸들**로 크기 조절.</p>
    </section>
  </div>
<script>
const payload = {payload_json};
const stage = document.getElementById("stage");
const photoClip = document.getElementById("photoClip");
const layersRoot = document.getElementById("layersRoot");
const uiOverlay = document.getElementById("uiOverlay");
const handleOverlay = document.getElementById("handleOverlay");
const stageBg = document.getElementById("stageBg");
const stageShell = document.getElementById("stageShell");
const zoomSpacer = document.getElementById("zoomSpacer");
const palette = document.getElementById("palette");
const exportBtn = document.getElementById("exportBtn");
const deleteBtn = document.getElementById("deleteBtn");
const clearBtn = document.getElementById("clearBtn");
const statusBanner = document.getElementById("statusBanner");
const zoomOutBtn = document.getElementById("zoomOutBtn");
const zoomInBtn = document.getElementById("zoomInBtn");
const zoomResetBtn = document.getElementById("zoomResetBtn");
const zoomLabel = document.getElementById("zoomLabel");

const MAX_STAGE_WIDTH = 1000;
const MIN_VIEW_ZOOM = 0.5;
const MAX_VIEW_ZOOM = 4;
const ZOOM_STEP = 0.25;
const STAGE_PAD = {{
  top: 0.04,
  left: 0.06,
  right: 0.06,
  bottom: 0.28,
}};
const EXPORT_JPEG_QUALITY = 0.82;

function waitNextPaint() {{
  return new Promise((resolve) => {{
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  }});
}}

async function captureVisibleSnapshot() {{
  const prevSelected = selectedLayerId;
  selectedLayerId = null;
  renderSelectionHandles();
  redrawUiOverlay();

  const badge = photoClip.querySelector(".version-badge");
  const prevBadgeVisibility = badge ? badge.style.visibility : "";
  if (badge) {{
    badge.style.visibility = "hidden";
  }}

  await waitNextPaint();

  const layout = getStageLayout();
  const w = Math.max(1, layout.photoWidth);
  const h = Math.max(1, layout.photoHeight);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", {{ alpha: false }});
  if (!ctx) {{
    if (badge) badge.style.visibility = prevBadgeVisibility;
    throw new Error("canvas unsupported");
  }}

  ctx.fillStyle = "#f7f5f1";
  ctx.fillRect(0, 0, w, h);

  if (stageBg.complete && stageBg.naturalWidth > 0) {{
    ctx.drawImage(stageBg, 0, 0, w, h);
  }}

  layersRoot.querySelectorAll(".layer").forEach((node) => {{
    const layerCanvas = node.querySelector(".layer-canvas");
    if (!layerCanvas || layerCanvas.width <= 0) {{
      return;
    }}
    ctx.drawImage(
      layerCanvas,
      node.offsetLeft,
      node.offsetTop,
      node.offsetWidth,
      node.offsetHeight,
    );
  }});

  const dataUrl = canvas.toDataURL("image/jpeg", EXPORT_JPEG_QUALITY);

  if (badge) {{
    badge.style.visibility = prevBadgeVisibility;
  }}
  selectedLayerId = prevSelected;
  renderSelectionHandles();

  return dataUrl;
}}

function downloadSnapshot(dataUrl, filename) {{
  const link = document.createElement("a");
  link.href = dataUrl;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
}}
let displayScale = 1;
let viewZoom = 1;
let layers = [];
let selectedLayerId = null;
let dragState = null;
let pinchState = null;
let layerCounter = 0;
let lastSyncSignature = "";

function serializeLayersForStreamlit() {{
  return layers.map((layer) => {{
    ensureLayerQuad(layer);
    const bounds = quadBounds(layer.quad);
    return {{
      id: layer.id,
      assetId: layer.assetId,
      label: layer.label,
      x: bounds.x / displayScale,
      y: bounds.y / displayScale,
      width: bounds.width / displayScale,
      height: bounds.height / displayScale,
      quad: layer.quad.map((point) => ({{
        x: point.x / displayScale,
        y: point.y / displayScale,
      }})),
    }};
  }});
}}

function syncLayersToStreamlit() {{
  if (layers.length === 0) {{
    sendValue({{ action: "sync", selectedLayerId: null, layers: [] }});
    return;
  }}
  const serialized = serializeLayersForStreamlit();
  const signature = JSON.stringify({{ selectedLayerId, layers: serialized }});
  if (signature === lastSyncSignature) {{
    return;
  }}
  lastSyncSignature = signature;
  sendValue({{
    action: "sync",
    selectedLayerId,
    layers: serialized,
  }});
}}

function isMobileLayout() {{
  return window.matchMedia("(max-width: 768px)").matches;
}}

function clamp(value, min, max) {{
  return Math.min(max, Math.max(min, value));
}}

function sendValue(value) {{
  window.parent.postMessage({{
    isStreamlitMessage: true,
    type: "streamlit:setComponentValue",
    value: value,
  }}, "*");
}}

function setFrameHeight() {{
  const height = Math.max(document.body.scrollHeight + 24, isMobileLayout() ? 860 : 720);
  window.parent.postMessage({{
    isStreamlitMessage: true,
    type: "streamlit:setFrameHeight",
    height,
  }}, "*");
}}

function getPhotoSize() {{
  const naturalWidth = payload.background.width;
  const shellWidth = stageShell.clientWidth > 0 ? stageShell.clientWidth - 20 : window.innerWidth - 48;
  const maxWidth = isMobileLayout()
    ? Math.max(240, shellWidth)
    : Math.min(MAX_STAGE_WIDTH, Math.max(320, shellWidth));
  displayScale = Math.min(1, maxWidth / naturalWidth);
  return {{
    width: Math.round(naturalWidth * displayScale),
    height: Math.round(payload.background.height * displayScale),
  }};
}}

function getStageLayout() {{
  const photo = getPhotoSize();
  const offsetX = Math.round(photo.width * STAGE_PAD.left);
  const offsetY = Math.round(photo.height * STAGE_PAD.top);
  const padRight = Math.round(photo.width * STAGE_PAD.right);
  const padBottom = Math.round(photo.height * STAGE_PAD.bottom);
  return {{
    photoWidth: photo.width,
    photoHeight: photo.height,
    offsetX,
    offsetY,
    padRight,
    padBottom,
    totalWidth: photo.width + offsetX + padRight,
    totalHeight: photo.height + offsetY + padBottom,
  }};
}}

function photoPointToStageOverlay(point) {{
  const layout = getStageLayout();
  return {{
    x: point.x + layout.offsetX,
    y: point.y + layout.offsetY,
  }};
}}

function updateViewTransform() {{
  const layout = getStageLayout();
  stage.style.width = `${{layout.totalWidth}}px`;
  stage.style.height = `${{layout.totalHeight}}px`;
  photoClip.style.left = `${{layout.offsetX}}px`;
  photoClip.style.top = `${{layout.offsetY}}px`;
  photoClip.style.width = `${{layout.photoWidth}}px`;
  photoClip.style.height = `${{layout.photoHeight}}px`;
  stageBg.style.width = "100%";
  stageBg.style.height = "100%";
  stage.style.transform = `scale(${{viewZoom}})`;
  zoomSpacer.style.width = `${{Math.round(layout.totalWidth * viewZoom)}}px`;
  zoomSpacer.style.height = `${{Math.round(layout.totalHeight * viewZoom)}}px`;
  zoomLabel.textContent = `${{Math.round(viewZoom * 100)}}%`;
  resizeUiOverlay();
  redrawUiOverlay();
  setFrameHeight();
}}

function scaleStage() {{
  updateViewTransform();
}}

function setViewZoom(nextZoom) {{
  viewZoom = clamp(nextZoom, MIN_VIEW_ZOOM, MAX_VIEW_ZOOM);
  updateViewTransform();
}}

function clientToStage(clientX, clientY) {{
  const rect = stage.getBoundingClientRect();
  const layout = getStageLayout();
  if (rect.width <= 0 || rect.height <= 0) {{
    return {{ x: 0, y: 0 }};
  }}
  const stageX = ((clientX - rect.left) / rect.width) * stage.offsetWidth;
  const stageY = ((clientY - rect.top) / rect.height) * stage.offsetHeight;
  return {{
    x: stageX - layout.offsetX,
    y: stageY - layout.offsetY,
  }};
}}

function touchDistance(touches) {{
  const dx = touches[0].clientX - touches[1].clientX;
  const dy = touches[0].clientY - touches[1].clientY;
  return Math.hypot(dx, dy);
}}

const CORNER_LABELS = ["nw", "ne", "se", "sw"];
const HANDLE_RADIUS = 6;
const EDGE_CORNERS = {{
  top: [0, 1],
  right: [1, 2],
}};
const imageCache = new Map();

function rectToQuad(x, y, width, height) {{
  return [
    {{ x, y }},
    {{ x: x + width, y }},
    {{ x: x + width, y: y + height }},
    {{ x, y: y + height }},
  ];
}}

function quadBounds(quad) {{
  const xs = quad.map((point) => point.x);
  const ys = quad.map((point) => point.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  return {{
    x: minX,
    y: minY,
    width: Math.max(1, Math.max(...xs) - minX),
    height: Math.max(1, Math.max(...ys) - minY),
  }};
}}

function ensureLayerQuad(layer) {{
  if (Array.isArray(layer.quad) && layer.quad.length === 4) {{
    return layer;
  }}
  const x = Number(layer.x) || 0;
  const y = Number(layer.y) || 0;
  const width = Math.max(40, Number(layer.width) || 120);
  const height = Math.max(40, Number(layer.height) || 120);
  layer.quad = rectToQuad(x, y, width, height);
  return layer;
}}

function quadEdgeMidpoint(quad, edge) {{
  const [a, b] = EDGE_CORNERS[edge];
  return {{
    x: (quad[a].x + quad[b].x) / 2,
    y: (quad[a].y + quad[b].y) / 2,
  }};
}}

function edgeHandleSize(edge) {{
  if (isMobileLayout()) {{
    return edge === "top" ? {{ width: 34, height: 12 }} : {{ width: 12, height: 34 }};
  }}
  return edge === "top" ? {{ width: 22, height: 8 }} : {{ width: 8, height: 22 }};
}}

function resizeUiOverlay() {{
  if (!uiOverlay || !photoClip) return;
  const layout = getStageLayout();
  const width = Math.max(1, layout.photoWidth);
  const height = Math.max(1, layout.photoHeight);
  uiOverlay.width = width;
  uiOverlay.height = height;
  uiOverlay.style.width = `${{width}}px`;
  uiOverlay.style.height = `${{height}}px`;
}}

function redrawUiOverlay() {{
  if (!uiOverlay) return;
  resizeUiOverlay();
  const ctx = uiOverlay.getContext("2d");
  ctx.clearRect(0, 0, uiOverlay.width, uiOverlay.height);
  if (!selectedLayerId) return;
  const layer = layers.find((item) => item.id === selectedLayerId);
  if (!layer) return;
  ensureLayerQuad(layer);

  ctx.save();
  ctx.strokeStyle = "rgba(255, 255, 255, 0.92)";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([7, 5]);
  ctx.shadowColor = "rgba(28, 36, 52, 0.45)";
  ctx.shadowBlur = 3;
  ctx.beginPath();
  ctx.moveTo(layer.quad[0].x, layer.quad[0].y);
  for (let i = 1; i < layer.quad.length; i += 1) {{
    ctx.lineTo(layer.quad[i].x, layer.quad[i].y);
  }}
  ctx.closePath();
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.shadowBlur = 0;
  ctx.restore();
}}

function quadDiagonal(quad) {{
  const d1 = Math.hypot(quad[0].x - quad[2].x, quad[0].y - quad[2].y);
  const d2 = Math.hypot(quad[1].x - quad[3].x, quad[1].y - quad[3].y);
  return Math.max(d1, d2);
}}

function loadLayerImage(src) {{
  if (imageCache.has(src)) {{
    const cached = imageCache.get(src);
    if (cached.complete && cached.naturalWidth > 0) {{
      return Promise.resolve(cached);
    }}
    return new Promise((resolve, reject) => {{
      cached.onload = () => resolve(cached);
      cached.onerror = reject;
    }});
  }}
  const img = new Image();
  img.src = src;
  imageCache.set(src, img);
  return new Promise((resolve, reject) => {{
    img.onload = () => resolve(img);
    img.onerror = reject;
  }});
}}

function solveLinear8(matrix, values) {{
  const n = 8;
  const rows = matrix.map((row, index) => [...row, values[index]]);
  for (let col = 0; col < n; col += 1) {{
    let pivot = col;
    for (let row = col + 1; row < n; row += 1) {{
      if (Math.abs(rows[row][col]) > Math.abs(rows[pivot][col])) {{
        pivot = row;
      }}
    }}
    if (Math.abs(rows[pivot][col]) < 1e-10) {{
      return null;
    }}
    if (pivot !== col) {{
      [rows[col], rows[pivot]] = [rows[pivot], rows[col]];
    }}
    const div = rows[col][col];
    for (let j = col; j <= n; j += 1) {{
      rows[col][j] /= div;
    }}
    for (let row = 0; row < n; row += 1) {{
      if (row === col) continue;
      const factor = rows[row][col];
      for (let j = col; j <= n; j += 1) {{
        rows[row][j] -= factor * rows[col][j];
      }}
    }}
  }}
  return rows.map((row) => row[n]);
}}

function homographyFromQuads(srcPts, dstPts) {{
  const matrix = [];
  const values = [];
  for (let i = 0; i < 4; i += 1) {{
    const sx = srcPts[i][0];
    const sy = srcPts[i][1];
    const dx = dstPts[i][0];
    const dy = dstPts[i][1];
    matrix.push([sx, sy, 1, 0, 0, 0, -dx * sx, -dx * sy]);
    values.push(dx);
    matrix.push([0, 0, 0, sx, sy, 1, -dy * sx, -dy * sy]);
    values.push(dy);
  }}
  const h = solveLinear8(matrix, values);
  if (!h) {{
    return [1, 0, 0, 0, 1, 0, 0, 0, 1];
  }}
  return [h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7], 1];
}}

function homographyToMatrix3d(h) {{
  const nums = [
    h[0], h[3], 0, h[6],
    h[1], h[4], 0, h[7],
    0, 0, 1, 0,
    h[2], h[5], 0, 1,
  ].map((value) => Number(value.toFixed(8)));
  return `matrix3d(${{nums.join(", ")}})`;
}}

function expandQuadOutward(quad, extraPx) {{
  const cx = quad.reduce((sum, point) => sum + point.x, 0) / 4;
  const cy = quad.reduce((sum, point) => sum + point.y, 0) / 4;
  return quad.map((point) => {{
    const dx = point.x - cx;
    const dy = point.y - cy;
    const dist = Math.hypot(dx, dy);
    if (dist < 0.5) {{
      return {{ x: point.x, y: point.y }};
    }}
    const scale = (dist + extraPx) / dist;
    return {{ x: cx + dx * scale, y: cy + dy * scale }};
  }});
}}

function getLayerRenderQuad(layer) {{
  ensureLayerQuad(layer);
  const base = layer.quad.map((point) => ({{ x: point.x, y: point.y }}));
  const diag = quadDiagonal(base);
  const edgeBleed = Math.max(4, diag * 0.02);
  // Keep the same shape as the selection handles / export quad.
  // (Previous sheet-only bottom stretch made 시트지 look skewed on first add.)
  return expandQuadOutward(base, edgeBleed);
}}

function drawImageTriangle(ctx, img, s0, s1, s2, d0, d1, d2) {{
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(d0.x, d0.y);
  ctx.lineTo(d1.x, d1.y);
  ctx.lineTo(d2.x, d2.y);
  ctx.closePath();
  ctx.clip();

  const denom = s0.x * (s2.y - s1.y) + s1.x * (s0.y - s2.y) + s2.x * (s1.y - s0.y);
  if (Math.abs(denom) < 0.001) {{
    ctx.restore();
    return;
  }}

  const m11 = (d0.x * (s2.y - s1.y) + d1.x * (s0.y - s2.y) + d2.x * (s1.y - s0.y)) / denom;
  const m12 = (d0.y * (s2.y - s1.y) + d1.y * (s0.y - s2.y) + d2.y * (s1.y - s0.y)) / denom;
  const m21 = (d0.x * (s1.x - s2.x) + d1.x * (s2.x - s0.x) + d2.x * (s0.x - s1.x)) / denom;
  const m22 = (d0.y * (s1.x - s2.x) + d1.y * (s2.x - s0.x) + d2.y * (s0.x - s1.x)) / denom;
  const dx = (d0.x * (s2.x * s1.y - s1.x * s2.y) + d1.x * (s0.x * s2.y - s2.x * s0.y) + d2.x * (s1.x * s0.y - s0.x * s1.y)) / denom;
  const dy = (d0.y * (s2.x * s1.y - s1.x * s2.y) + d1.y * (s0.x * s2.y - s2.x * s0.y) + d2.y * (s1.x * s0.y - s0.x * s1.y)) / denom;

  ctx.transform(m11, m12, m21, m22, dx, dy);
  ctx.drawImage(img, 0, 0);
  ctx.restore();
}}

function drawImageQuad(ctx, img, quad) {{
  const iw = img.naturalWidth || img.width;
  const ih = img.naturalHeight || img.height;
  ctx.save();
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = "source-over";
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  drawImageTriangle(
    ctx,
    img,
    {{ x: 0, y: 0 }},
    {{ x: iw, y: 0 }},
    {{ x: 0, y: ih }},
    quad[0],
    quad[1],
    quad[3],
  );
  drawImageTriangle(
    ctx,
    img,
    {{ x: iw, y: 0 }},
    {{ x: iw, y: ih }},
    {{ x: 0, y: ih }},
    quad[1],
    quad[2],
    quad[3],
  );
  ctx.restore();
}}

function resetExportControls() {{
  exportBtn.disabled = false;
  deleteBtn.disabled = false;
  clearBtn.disabled = false;
  exportBtn.textContent = "합성 이미지 적용";
  statusBanner.classList.remove("active");
  setFrameHeight();
}}

function paintLayerRectImg(imgNode, layer) {{
  if (imgNode.src !== layer.src) {{
    imgNode.src = layer.src;
  }}
  imgNode.style.left = "0";
  imgNode.style.top = "0";
  imgNode.style.width = "100%";
  imgNode.style.height = "100%";
  imgNode.style.transformOrigin = "";
  imgNode.style.transform = "none";
  imgNode.style.display = "block";
}}

function paintLayerPerspectiveCanvas(canvasNode, layerSrc, renderQuad, bounds) {{
  const width = Math.max(1, bounds.width);
  const height = Math.max(1, bounds.height);
  const localQuad = renderQuad.map((point) => ({{
    x: point.x - bounds.x,
    y: point.y - bounds.y,
  }}));
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  return loadLayerImage(layerSrc).then((img) => {{
    canvasNode.width = Math.ceil(width * dpr);
    canvasNode.height = Math.ceil(height * dpr);
    canvasNode.style.width = `${{width}}px`;
    canvasNode.style.height = `${{height}}px`;
    const ctx = canvasNode.getContext("2d", {{ alpha: true }});
    if (!ctx) {{
      return;
    }}
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    drawImageQuad(ctx, img, localQuad);
    canvasNode.style.display = "block";
  }});
}}

function syncLayerVisual(node, layer, isSelected) {{
  ensureLayerQuad(layer);
  const renderQuad = getLayerRenderQuad(layer);
  const bounds = quadBounds(renderQuad);
  node.style.left = `${{bounds.x}}px`;
  node.style.top = `${{bounds.y}}px`;
  node.style.width = `${{bounds.width}}px`;
  node.style.height = `${{bounds.height}}px`;

  let canvasNode = node.querySelector(".layer-canvas");
  let imgNode = node.querySelector(".layer-img");
  if (imgNode) {{
    imgNode.style.display = "none";
  }}
  if (!canvasNode) {{
    canvasNode = document.createElement("canvas");
    canvasNode.className = "layer-canvas";
    node.appendChild(canvasNode);
  }}
  return paintLayerPerspectiveCanvas(canvasNode, layer.src, renderQuad, bounds);
}}

function positionCornerHandleStage(handle, point) {{
  const overlayPoint = photoPointToStageOverlay(point);
  const radius = isMobileLayout() ? 14 : HANDLE_RADIUS;
  handle.style.left = `${{overlayPoint.x - radius}}px`;
  handle.style.top = `${{overlayPoint.y - radius}}px`;
}}

function positionEdgeHandleStage(handle, quad, edge) {{
  const mid = quadEdgeMidpoint(quad, edge);
  const overlayPoint = photoPointToStageOverlay(mid);
  const size = edgeHandleSize(edge);
  handle.style.width = `${{size.width}}px`;
  handle.style.height = `${{size.height}}px`;
  handle.style.left = `${{overlayPoint.x - size.width / 2}}px`;
  handle.style.top = `${{overlayPoint.y - size.height / 2}}px`;
}}

function onHandlePointerDown(event) {{
  event.preventDefault();
  event.stopPropagation();
  const target = event.currentTarget;
  target.setPointerCapture(event.pointerId);
  const layerId = target.dataset.layerId;
  if (!layerId) return;
  const edge = target.dataset.edge;
  if (edge) {{
    startDrag(event, layerId, `edge-${{edge}}`);
    return;
  }}
  const corner = target.dataset.corner;
  if (corner !== undefined) {{
    startDrag(event, layerId, `corner-${{corner}}`);
  }}
}}

function repositionSelectionHandles(layer) {{
  if (!handleOverlay || !layer) return;
  ensureLayerQuad(layer);
  handleOverlay.querySelectorAll(".corner-handle").forEach((handle) => {{
    const cornerIndex = Number(handle.dataset.corner);
    positionCornerHandleStage(handle, layer.quad[cornerIndex]);
  }});
  handleOverlay.querySelectorAll(".edge-handle").forEach((handle) => {{
    positionEdgeHandleStage(handle, layer.quad, handle.dataset.edge);
  }});
  redrawUiOverlay();
}}

function createEdgeHandle(layer, edge) {{
  const handle = document.createElement("div");
  handle.className = `edge-handle ${{edge}}`;
  handle.dataset.edge = edge;
  handle.dataset.layerId = layer.id;
  handle.title = edge === "top" ? "높이 조절" : "너비 조절";
  positionEdgeHandleStage(handle, layer.quad, edge);
  handle.addEventListener("pointerdown", onHandlePointerDown);
  return handle;
}}

function renderSelectionHandles() {{
  if (!handleOverlay) return;
  handleOverlay.innerHTML = "";
  if (!selectedLayerId) {{
    redrawUiOverlay();
    return;
  }}
  const layer = layers.find((item) => item.id === selectedLayerId);
  if (!layer) {{
    redrawUiOverlay();
    return;
  }}
  ensureLayerQuad(layer);

  CORNER_LABELS.forEach((label, index) => {{
    const handle = document.createElement("div");
    handle.className = `corner-handle ${{label}}`;
    handle.dataset.corner = String(index);
    handle.dataset.layerId = layer.id;
    positionCornerHandleStage(handle, layer.quad[index]);
    handle.addEventListener("pointerdown", onHandlePointerDown);
    handleOverlay.appendChild(handle);
  }});

  handleOverlay.appendChild(createEdgeHandle(layer, "top"));
  handleOverlay.appendChild(createEdgeHandle(layer, "right"));
  redrawUiOverlay();
}}

function createLayerFromAsset(asset, x, y) {{
  const layerId = `layer_${{++layerCounter}}`;
  const baseWidth = Math.max(120, Math.min(asset.width, payload.background.width * 0.45));
  const ratio = asset.height / asset.width;
  const width = baseWidth * displayScale;
  const height = width * ratio;
  const left = Math.max(0, x - width / 2);
  const top = Math.max(0, y - height / 2);
  return {{
    id: layerId,
    assetId: asset.id,
    label: asset.label,
    src: asset.src,
    category: asset.category,
    quad: rectToQuad(left, top, width, height),
  }};
}}

function bindLayerPointerEvents(node, layerId) {{
  if (node.dataset.bound === "1") {{
    return;
  }}
  node.dataset.bound = "1";
  node.addEventListener("pointerdown", (event) => {{
    event.preventDefault();
    event.stopPropagation();
    const layer = layers.find((item) => item.id === layerId);
    if (!layer) return;
    node.setPointerCapture(event.pointerId);
    startDrag(event, layerId, "move");
  }});
}}

function setSelectedLayer(layerId) {{
  if (selectedLayerId === layerId) {{
    return;
  }}
  selectedLayerId = layerId;
  renderLayers();
}}

function updateLayerNode(layer) {{
  const node = layersRoot.querySelector(`[data-layer-id="${{layer.id}}"]`);
  if (!node) return;
  syncLayerVisual(node, layer, layer.id === selectedLayerId);
  if (layer.id === selectedLayerId) {{
    if (dragState) {{
      repositionSelectionHandles(layer);
    }} else {{
      renderSelectionHandles();
    }}
  }}
}}

function renderLayers() {{
  layersRoot.querySelectorAll(".layer").forEach((node) => node.remove());
  layers.forEach((layer) => {{
    ensureLayerQuad(layer);
    const bounds = quadBounds(layer.quad);
    const isSelected = layer.id === selectedLayerId;
    const node = document.createElement("div");
    node.className = "layer" + (isSelected ? " selected" : "");
    node.dataset.layerId = layer.id;
    node.style.left = `${{bounds.x}}px`;
    node.style.top = `${{bounds.y}}px`;
    node.style.width = `${{bounds.width}}px`;
    node.style.height = `${{bounds.height}}px`;

    bindLayerPointerEvents(node, layer.id);
    layersRoot.appendChild(node);
    syncLayerVisual(node, layer, isSelected);
  }});
  renderSelectionHandles();
  setFrameHeight();
}}

function startDrag(event, layerId, mode) {{
  event.preventDefault();
  event.stopPropagation();
  selectedLayerId = layerId;
  layersRoot.querySelectorAll(".layer").forEach((node) => {{
    node.classList.toggle("selected", node.dataset.layerId === layerId);
  }});
  if (mode === "move") {{
    renderSelectionHandles();
  }}
  const layer = layers.find((item) => item.id === layerId);
  if (!layer) return;
  ensureLayerQuad(layer);
  const startPt = clientToStage(event.clientX, event.clientY);
  const originQuad = layer.quad.map((point) => ({{ x: point.x, y: point.y }}));
  dragState = {{
    mode,
    layerId,
    pointerId: event.pointerId,
    startPt,
    originQuad,
    cornerIndex: mode.startsWith("corner-") ? Number(mode.split("-")[1]) : null,
    edgeName: mode.startsWith("edge-") ? mode.slice(5) : null,
  }};
  stageShell.classList.add("is-dragging");
}}

function onPointerMove(event) {{
  if (!dragState || event.pointerId !== dragState.pointerId) return;
  event.preventDefault();
  const layer = layers.find((item) => item.id === dragState.layerId);
  if (!layer) return;
  const pt = clientToStage(event.clientX, event.clientY);
  const dx = pt.x - dragState.startPt.x;
  const dy = pt.y - dragState.startPt.y;

  if (dragState.mode === "move") {{
    layer.quad = dragState.originQuad.map((point) => ({{
      x: point.x + dx,
      y: point.y + dy,
    }}));
  }} else if (dragState.mode === "edge-top") {{
    layer.quad = dragState.originQuad.map((point, index) => (
      index === 0 || index === 1
        ? {{ x: point.x, y: point.y + dy }}
        : {{ x: point.x, y: point.y }}
    ));
  }} else if (dragState.mode === "edge-right") {{
    layer.quad = dragState.originQuad.map((point, index) => (
      index === 1 || index === 2
        ? {{ x: point.x + dx, y: point.y }}
        : {{ x: point.x, y: point.y }}
    ));
  }} else if (dragState.cornerIndex !== null) {{
    layer.quad = dragState.originQuad.map((point, index) => (
      index === dragState.cornerIndex
        ? {{
          x: point.x + dx,
          y: point.y + dy,
        }}
        : {{ x: point.x, y: point.y }}
    ));
  }}
  updateLayerNode(layer);
}}

function endDrag(event) {{
  if (!dragState) return;
  if (event && event.pointerId !== dragState.pointerId) return;
  dragState = null;
  stageShell.classList.remove("is-dragging");
  renderLayers();
}}

function addAssetToStage(asset, clientX, clientY) {{
  const pt = clientToStage(clientX, clientY);
  layers.push(createLayerFromAsset(asset, pt.x, pt.y));
  selectedLayerId = layers[layers.length - 1].id;
  renderLayers();
}}

function renderPalette() {{
  palette.innerHTML = "";
  const grouped = {{}};
  payload.palette.forEach((asset) => {{
    grouped[asset.category] = grouped[asset.category] || [];
    grouped[asset.category].push(asset);
  }});
  Object.entries(grouped).forEach(([category, items]) => {{
    const group = document.createElement("div");
    group.className = "palette-group";
    const title = document.createElement("h3");
    title.textContent = category;
    group.appendChild(title);
    items.forEach((asset) => {{
      const item = document.createElement("div");
      item.className = "palette-item";
      item.draggable = !isMobileLayout();
      item.innerHTML = `<img src="${{asset.src}}" alt="${{asset.label}}" /><span>${{asset.label}}</span>`;
      item.addEventListener("dragstart", (event) => {{
        event.dataTransfer.setData("application/json", JSON.stringify(asset));
      }});
      item.addEventListener("click", () => {{
        const rect = stage.getBoundingClientRect();
        addAssetToStage(asset, rect.left + rect.width * 0.5, rect.top + rect.height * 0.5);
      }});
      group.appendChild(item);
    }});
    palette.appendChild(group);
  }});
}}

stage.addEventListener("dragover", (event) => event.preventDefault());
stage.addEventListener("drop", (event) => {{
  event.preventDefault();
  const raw = event.dataTransfer.getData("application/json");
  if (!raw) return;
  const asset = JSON.parse(raw);
  addAssetToStage(asset, event.clientX, event.clientY);
}});

stage.addEventListener("pointerdown", (event) => {{
  if (event.target === stage || event.target === stageBg) {{
    setSelectedLayer(null);
  }}
}});

stageShell.addEventListener("touchstart", (event) => {{
  if (dragState) return;
  if (event.touches.length === 2) {{
    pinchState = {{
      startDist: touchDistance(event.touches),
      startZoom: viewZoom,
    }};
    stageShell.classList.add("is-pinching");
    event.preventDefault();
  }}
}}, {{ passive: false }});

stageShell.addEventListener("touchmove", (event) => {{
  if (dragState) {{
    event.preventDefault();
    return;
  }}
  if (pinchState && event.touches.length === 2) {{
    const dist = touchDistance(event.touches);
    if (pinchState.startDist > 0) {{
      setViewZoom(pinchState.startZoom * (dist / pinchState.startDist));
    }}
    event.preventDefault();
  }}
}}, {{ passive: false }});

stageShell.addEventListener("touchend", () => {{
  pinchState = null;
  stageShell.classList.remove("is-pinching");
}});

deleteBtn.addEventListener("click", () => {{
  if (!selectedLayerId) return;
  layers = layers.filter((layer) => layer.id !== selectedLayerId);
  selectedLayerId = null;
  renderLayers();
}});

clearBtn.addEventListener("click", () => {{
  layers = [];
  selectedLayerId = null;
  renderLayers();
}});

zoomOutBtn.addEventListener("click", () => setViewZoom(viewZoom - ZOOM_STEP));
zoomInBtn.addEventListener("click", () => setViewZoom(viewZoom + ZOOM_STEP));
zoomResetBtn.addEventListener("click", () => setViewZoom(1));

exportBtn.addEventListener("click", async () => {{
  if (layers.length === 0) {{
    alert("합성할 시트지·집기를 사진 위에 배치해 주세요.");
    return;
  }}

  exportBtn.disabled = true;
  deleteBtn.disabled = true;
  clearBtn.disabled = true;
  exportBtn.textContent = "캡처 중...";

  try {{
    const composite = await captureVisibleSnapshot();
    downloadSnapshot(composite, "window_composite.jpg");
    sendValue({{
      action: "export",
      composite,
      layers: serializeLayersForStreamlit(),
    }});
    resetExportControls();
    exportBtn.textContent = "저장 완료";
    window.setTimeout(() => {{
      exportBtn.textContent = "합성 이미지 적용";
    }}, 1500);
  }} catch (error) {{
    console.error(error);
    alert("화면 캡처에 실패했습니다. 다시 시도해 주세요.");
    resetExportControls();
  }}
}});

document.addEventListener("pointermove", onPointerMove);
document.addEventListener("pointerup", endDrag);
document.addEventListener("pointercancel", endDrag);

stageBg.src = payload.background.src;
imageCache.clear();
scaleStage();
layers = (payload.layers || []).map((layer) => {{
  const asset = payload.palette.find((item) => item.id === layer.assetId);
  const nextLayer = {{
    ...layer,
    src: asset ? asset.src : layer.src,
    category: layer.category || (asset ? asset.category : ""),
  }};
  if (Array.isArray(layer.quad) && layer.quad.length === 4) {{
    nextLayer.quad = layer.quad.map((point) => ({{
      x: Number(point.x) * displayScale,
      y: Number(point.y) * displayScale,
    }}));
  }} else {{
    nextLayer.x = Number(layer.x) * displayScale;
    nextLayer.y = Number(layer.y) * displayScale;
    nextLayer.width = Number(layer.width) * displayScale;
    nextLayer.height = Number(layer.height) * displayScale;
  }}
  ensureLayerQuad(nextLayer);
  return nextLayer;
}});
layerCounter = layers.length;
if (payload.selectedLayerId) {{
  selectedLayerId = payload.selectedLayerId;
}}
renderPalette();
renderLayers();
setFrameHeight();
window.addEventListener("resize", () => {{
  scaleStage();
  renderLayers();
}});
</script>
</body>
</html>
"""


def decode_data_uri_image(data_uri: str) -> Image.Image:
    if "," not in data_uri:
        raise ValueError("Invalid image data URI.")
    encoded = data_uri.split(",", 1)[1]
    raw = base64.b64decode(encoded)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def _quad_diagonal(quad: list[tuple[float, float]]) -> float:
    return max(
        math.hypot(quad[0][0] - quad[2][0], quad[0][1] - quad[2][1]),
        math.hypot(quad[1][0] - quad[3][0], quad[1][1] - quad[3][1]),
    )


def _layer_quad_points(layer: dict) -> list[tuple[float, float]] | None:
    quad = layer.get("quad")
    if not quad or len(quad) != 4:
        return None

    points: list[tuple[float, float]] = []
    for point in quad:
        if isinstance(point, dict):
            points.append((float(point["x"]), float(point["y"])))
        else:
            points.append((float(point[0]), float(point[1])))
    return points


def compose_window_layers(
    background: Image.Image,
    layers: list[dict],
    assets: list[dict],
) -> Image.Image:
    """레이어 좌표를 기준으로 배경 위에 시트지·집기를 합성합니다."""
    base_cv = pil_to_cv2(background.convert("RGB"))
    asset_map = {asset["id"]: asset for asset in assets}

    for layer in layers:
        asset = asset_map.get(layer.get("assetId"))
        if asset is None:
            continue

        overlay = asset["image"].convert("RGBA")
        quad = _layer_quad_points(layer)

        if quad:
            overlay_np = _asset_rgba_array(asset)
            base_cv = _warp_rgba_overlay(
                base_cv,
                overlay_np,
                quad,
                source_edge_feather=0,
                alpha_blur_sigma=0,
            )
            continue

        width = max(1, int(round(float(layer.get("width", overlay.width)))))
        height = max(1, int(round(float(layer.get("height", overlay.height)))))
        if overlay.size != (width, height):
            overlay = overlay.resize((width, height), Image.Resampling.LANCZOS)

        x = int(round(float(layer.get("x", 0))))
        y = int(round(float(layer.get("y", 0))))
        base_rgba = cv2_to_pil(base_cv).convert("RGBA")
        base_rgba.paste(overlay, (x, y), overlay)
        base_cv = pil_to_cv2(base_rgba.convert("RGB"))

    return cv2_to_pil(base_cv).convert("RGB")


def save_composite_image(image: Image.Image) -> str:
    os.makedirs(COMPOSITE_OUTPUT_DIR, exist_ok=True)
    filename = f"window_composite_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    output_path = os.path.join(COMPOSITE_OUTPUT_DIR, filename)
    image.convert("RGB").save(output_path, format="JPEG", quality=90, optimize=False)
    return output_path
