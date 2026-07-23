import io
import json
import os

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from english_ui import inject_english_widget_guard
from image_utils import limit_image_size, load_image
from mobile_upload import inject_mobile_upload_styles, mobile_photo_uploader
from window_compositor import (
    build_window_compositor_html,
    compose_window_layers,
    decode_data_uri_image,
    image_to_data_uri,
    save_composite_image,
)
from window_guides import FIXTURE_DIR, IMAGE_EXTENSIONS, SHEET_DIR, load_window_guide_assets
from window_inpaint import get_openai_client, remove_window_promo
from window_selection import (
    get_confirmed_cleanup_rect,
    is_cleanup_ready_for_remove,
    render_window_rect_selector,
)

WINDOW_ENGLISH_LABELS = {}

GUIDE_CARD_WIDTH = 204
GUIDE_IMAGE_SIZE = 180
GUIDE_CARD_HEIGHT = 290
COMPOSITOR_HEIGHT = 820
COMPOSITOR_UI_VERSION = "v27"
COMPOSITOR_ASSET_URI_VERSION = 6
COMPOSITOR_ASSET_PREVIEW_MAX = 720
COMPOSITOR_BG_MAX_DIM = 1920
MAX_WINDOW_IMAGE_DIM = 2048


def _sync_compositor_session(parsed: dict) -> None:
    if parsed.get("action") != "sync":
        return
    layers = parsed.get("layers") or []
    st.session_state["window_layer_state"] = layers
    selected_id = parsed.get("selectedLayerId")
    if selected_id:
        st.session_state["window_selected_layer_id"] = selected_id


def _parse_component_result(raw: object) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return {"composite": raw}
        except json.JSONDecodeError:
            return {"composite": raw}
    return None


def _parse_compositor_result(raw: object) -> dict | None:
    return _parse_component_result(raw)


def _promo_was_removed() -> bool:
    return bool(st.session_state.get("window_promo_removed"))


def _invalidate_compositor_cache(*, bump_nonce: bool = True) -> None:
    if bump_nonce:
        st.session_state["window_compositor_nonce"] = (
            int(st.session_state.get("window_compositor_nonce", 0)) + 1
        )
    for key in (
        "window_assets_for_compositor",
        "window_assets_cache_key",
        "window_compositor_html",
        "window_compositor_html_key",
        "window_bg_data_uri",
        "window_bg_uri_sig",
        "window_compositor_bg_uri",
        "window_compositor_bg_sig",
        "window_compositor_coord_scale",
    ):
        st.session_state.pop(key, None)


def _enter_compose_step(*, promo_removed: bool) -> None:
    st.session_state["window_cleanup_complete"] = True
    st.session_state["window_promo_removed"] = promo_removed
    _invalidate_compositor_cache(bump_nonce=True)
    st.rerun()


def _reset_window_workflow(*, keep_upload_signature: str | None = None) -> None:
    if keep_upload_signature is not None:
        st.session_state["window_upload_signature"] = keep_upload_signature
    st.session_state.pop("window_working_image", None)
    st.session_state.pop("window_cleanup_complete", None)
    st.session_state.pop("window_promo_removed", None)
    st.session_state.pop("window_cleanup_rect", None)
    st.session_state.pop("window_rect_points", None)
    st.session_state.pop("window_selector_raw", None)
    st.session_state.pop("window_last_rect_sig", None)
    st.session_state.pop("window_confirmed_cleanup_rect", None)
    st.session_state.pop("window_cleanup_confirmed", None)
    st.session_state.pop("window_cleanup_mask", None)
    st.session_state.pop("window_cleanup_mask_shape", None)
    st.session_state.pop("window_cleanup_mask_stack", None)
    st.session_state.pop("window_confirmed_cleanup_mode", None)
    st.session_state.pop("window_pending_promo_remove", None)
    st.session_state.pop("window_last_click", None)
    st.session_state.pop("window_composite_result", None)
    st.session_state.pop("window_composite_saved_path", None)
    st.session_state.pop("window_layer_state", None)
    st.session_state.pop("window_last_export_sig", None)
    st.session_state.pop("window_compositor_raw", None)
    st.session_state.pop("window_compositor_nonce", None)
    st.session_state.pop("window_selected_layer_id", None)
    st.session_state.pop("window_composite_applying", None)
    st.session_state.pop("window_pending_export", None)
    st.session_state.pop("window_show_composite_only", None)
    st.session_state.pop("window_bg_data_uri", None)
    st.session_state.pop("window_bg_uri_sig", None)
    st.session_state.pop("window_selector_data_uri", None)
    st.session_state.pop("window_selector_uri_key", None)
    st.session_state.pop("window_selector_display_key", None)
    st.session_state.pop("window_selector_display_image", None)
    st.session_state.pop("window_selector_mount_sig", None)
    st.session_state.pop("window_base_image", None)
    st.session_state.pop("window_base_image_signature", None)
    st.session_state.pop("window_assets_for_compositor", None)
    st.session_state.pop("window_assets_cache_key", None)
    st.session_state.pop("window_interior_reference", None)
    st.session_state.pop("window_interior_signature", None)
    st.session_state.pop("window_removal_notes", None)
    for key in list(st.session_state.keys()):
        if key.startswith("window_rect") or key.startswith("window_picker"):
            st.session_state.pop(key, None)


def _rect_tuple(rect_data: dict) -> tuple[float, float, float, float]:
    return (
        float(rect_data["x"]),
        float(rect_data["y"]),
        float(rect_data["width"]),
        float(rect_data["height"]),
    )


def _sync_interior_reference(uploaded_file) -> Image.Image | None:
    if uploaded_file is None:
        return st.session_state.get("window_interior_reference")

    file_signature = f"{uploaded_file.name}:{uploaded_file.size}"
    if st.session_state.get("window_interior_signature") != file_signature:
        st.session_state["window_interior_signature"] = file_signature
        interior = load_image(uploaded_file, mode="RGB")
        st.session_state["window_interior_reference"] = limit_image_size(
            interior,
            max_dimension=MAX_WINDOW_IMAGE_DIM,
        )

    return st.session_state.get("window_interior_reference")


def _guide_assets_dir_signature() -> str:
    parts: list[str] = []
    for directory in (SHEET_DIR, FIXTURE_DIR):
        if not os.path.isdir(directory):
            parts.append(f"{directory}:missing")
            continue
        mtimes = sorted(
            (
                name,
                os.path.getmtime(os.path.join(directory, name)),
            )
            for name in os.listdir(directory)
            if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
        )
        parts.append(json.dumps(mtimes, default=str))
    return "|".join(parts)


def _get_guide_assets() -> list[dict]:
    signature = _guide_assets_dir_signature()
    if st.session_state.get("window_guide_assets_key") != signature:
        st.session_state["window_guide_assets"] = load_window_guide_assets()
        st.session_state["window_guide_assets_key"] = signature
        st.session_state.pop("window_guide_preview_html", None)
        st.session_state.pop("window_guide_preview_key", None)
    return st.session_state["window_guide_assets"]


def _sync_base_image(uploaded_file) -> Image.Image:
    file_signature = f"{uploaded_file.name}:{uploaded_file.size}"
    cached = st.session_state.get("window_base_image")
    if (
        st.session_state.get("window_base_image_signature") == file_signature
        and cached is not None
    ):
        return cached

    with st.spinner("사진 불러오는 중..."):
        try:
            image = load_image(io.BytesIO(uploaded_file.getvalue()), mode="RGB")
        except Exception as exc:
            st.error(f"사진을 불러오지 못했습니다: {exc}")
            st.stop()
        image = limit_image_size(image, max_dimension=MAX_WINDOW_IMAGE_DIM)

    st.session_state["window_base_image"] = image
    st.session_state["window_base_image_signature"] = file_signature
    st.session_state.pop("window_selector_data_uri", None)
    st.session_state.pop("window_selector_uri_key", None)
    st.session_state.pop("window_selector_display_key", None)
    st.session_state.pop("window_selector_display_image", None)
    st.session_state.pop("window_selector_mount_sig", None)
    st.session_state.pop("window_bg_data_uri", None)
    st.session_state.pop("window_bg_uri_sig", None)
    return image


def _run_window_promo_remove(
    base_image: Image.Image,
    rect_data: dict,
    *,
    interior_reference: Image.Image | None = None,
    removal_notes: str | None = None,
) -> bool:
    try:
        rect = _rect_tuple(rect_data)
    except (KeyError, TypeError, ValueError):
        st.error("선택 영역 좌표가 올바르지 않습니다.")
        return False

    working = _working_image(base_image)
    try:
        client = get_openai_client()
    except RuntimeError as exc:
        st.error(str(exc))
        return False

    try:
        cleaned = remove_window_promo(
            client=client,
            image=working,
            rect=rect,
            interior_reference=interior_reference,
            removal_notes=removal_notes,
        )
    except Exception as exc:
        st.error(f"홍보물 제거에 실패했습니다: {exc}")
        return False

    st.session_state["window_working_image"] = cleaned
    st.session_state["window_promo_removed"] = True
    _invalidate_compositor_cache(bump_nonce=False)
    st.session_state.pop("window_selector_display_key", None)
    st.session_state.pop("window_selector_display_image", None)
    st.session_state.pop("window_selector_mount_sig", None)
    st.session_state["window_selector_hydrate"] = True
    st.session_state.pop("window_cleanup_rect", None)
    st.session_state.pop("window_rect_points", None)
    st.session_state.pop("window_selector_raw", None)
    st.session_state.pop("window_last_click", None)
    st.session_state.pop("window_composite_result", None)
    st.session_state.pop("window_layer_state", None)

    st.success("선택 영역의 홍보물이 제거되었습니다. 필요하면 다른 영역도 반복해 주세요.")
    return True


def _working_image(base_image: Image.Image) -> Image.Image:
    stored = st.session_state.get("window_working_image")
    if stored is not None:
        return stored
    return base_image


def _export_signature(layers: list) -> str:
    return json.dumps(layers, sort_keys=True, default=str)


def _working_image_signature(image: Image.Image) -> str:
    return f"{image.width}x{image.height}@{id(image)}"


def _resize_rgba_for_preview(image: Image.Image, *, max_dim: int) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_dim:
        return image
    scale = max_dim / longest
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _compositor_preview_image(working_image: Image.Image) -> tuple[Image.Image, float]:
    preview = limit_image_size(working_image, max_dimension=COMPOSITOR_BG_MAX_DIM)
    if preview.width <= 0:
        return working_image, 1.0
    scale = working_image.width / preview.width
    return preview, scale


def _scale_layers_coords(layers: list[dict], scale: float) -> list[dict]:
    if not layers or abs(scale - 1.0) < 0.001:
        return layers

    scaled_layers: list[dict] = []
    for layer in layers:
        next_layer = dict(layer)
        for key in ("x", "y", "width", "height"):
            if key in next_layer and next_layer[key] is not None:
                next_layer[key] = float(next_layer[key]) * scale

        quad = next_layer.get("quad")
        if isinstance(quad, list):
            scaled_quad = []
            for point in quad:
                if isinstance(point, dict):
                    scaled_quad.append(
                        {
                            "x": float(point["x"]) * scale,
                            "y": float(point["y"]) * scale,
                        }
                    )
                else:
                    scaled_quad.append(
                        [float(point[0]) * scale, float(point[1]) * scale]
                    )
            next_layer["quad"] = scaled_quad

        scaled_layers.append(next_layer)
    return scaled_layers


def _get_compositor_background(working_image: Image.Image) -> tuple[str, int, int, float]:
    preview, coord_scale = _compositor_preview_image(working_image)
    sig = f"{preview.width}x{preview.height}@{id(working_image)}"
    cache_sig = st.session_state.get("window_compositor_bg_sig")
    cached_uri = st.session_state.get("window_compositor_bg_uri")
    if cache_sig == sig and cached_uri:
        return cached_uri, preview.width, preview.height, coord_scale

    uri = image_to_data_uri(preview, jpeg_quality=88)
    st.session_state["window_compositor_bg_sig"] = sig
    st.session_state["window_compositor_bg_uri"] = uri
    st.session_state["window_compositor_coord_scale"] = coord_scale
    return uri, preview.width, preview.height, coord_scale


def _compositor_html_cache_key(
    *,
    working_image: Image.Image,
    compositor_nonce: int,
    restore_layers: bool,
) -> tuple:
    assets_key = st.session_state.get("window_assets_cache_key")
    return (
        COMPOSITOR_UI_VERSION,
        compositor_nonce,
        _working_image_signature(working_image),
        assets_key,
        restore_layers,
    )


def _get_compositor_html(
    *,
    working_image: Image.Image,
    compositor_assets: list[dict],
    compositor_nonce: int,
    layers: list | None,
    selected_layer_id: str | None,
    restore_layers: bool,
) -> str:
    cache_key = _compositor_html_cache_key(
        working_image=working_image,
        compositor_nonce=compositor_nonce,
        restore_layers=restore_layers,
    )
    if st.session_state.get("window_compositor_html_key") == cache_key:
        cached = st.session_state.get("window_compositor_html")
        if cached:
            return cached

    bg_uri, bg_width, bg_height, coord_scale = _get_compositor_background(working_image)
    preview_layers = layers
    if restore_layers and layers:
        preview_layers = _scale_layers_coords(layers, 1.0 / coord_scale)

    html = build_window_compositor_html(
        background_data_uri=bg_uri,
        background_width=bg_width,
        background_height=bg_height,
        assets=compositor_assets,
        initial_layers=preview_layers if restore_layers else [],
        selected_layer_id=selected_layer_id if restore_layers else None,
        remount_nonce=compositor_nonce,
    )
    st.session_state["window_compositor_html_key"] = cache_key
    st.session_state["window_compositor_html"] = html
    return html


def _asset_data_uri_for_compositor(asset: dict) -> str:
    image = _resize_rgba_for_preview(
        asset["image"].convert("RGBA"),
        max_dim=COMPOSITOR_ASSET_PREVIEW_MAX,
    )
    return image_to_data_uri(image, prefer_jpeg=False)


def _guide_assets_for_compositor(guide_assets: list[dict]) -> list[dict]:
    cache_key = (
        COMPOSITOR_ASSET_URI_VERSION,
        tuple(
            f"{asset['id']}:{os.path.getmtime(asset['path'])}"
            for asset in guide_assets
        ),
    )
    if st.session_state.get("window_assets_cache_key") == cache_key:
        cached = st.session_state.get("window_assets_for_compositor")
        if cached:
            return cached

    enriched = []
    for asset in guide_assets:
        enriched.append(
            {
                **asset,
                "data_uri": _asset_data_uri_for_compositor(asset),
            }
        )
    st.session_state["window_assets_cache_key"] = cache_key
    st.session_state["window_assets_for_compositor"] = enriched
    return enriched


def _should_queue_compositor_export(parsed: dict | None) -> bool:
    if not parsed:
        return False

    if parsed.get("action") == "export":
        layers = parsed.get("layers") or []
        if not layers:
            return False
        return _export_signature(layers) != st.session_state.get("window_last_export_sig")

    if parsed.get("composite"):
        export_sig = parsed["composite"][:120]
        return export_sig != st.session_state.get("window_last_export_sig")

    return False


def _store_client_composite(
    composite_uri: str,
    layers: list[dict],
    *,
    working_image: Image.Image,
    guide_assets: list[dict],
    coord_scale: float = 1.0,
) -> None:
    """최종 저장은 원본 해상도 서버 합성을 우선합니다. 캡처본은 폴백만 사용."""
    if layers:
        _compose_layers_and_store(
            layers,
            working_image=working_image,
            guide_assets=guide_assets,
            coord_scale=coord_scale,
        )
        return

    composite_image = decode_data_uri_image(composite_uri)
    export_sig = composite_uri[:240]
    saved_path = save_composite_image(composite_image)
    st.session_state["window_composite_result"] = composite_image
    st.session_state["window_composite_saved_path"] = saved_path
    st.session_state["window_last_export_sig"] = export_sig


def _compose_layers_and_store(
    layers: list[dict],
    *,
    working_image: Image.Image,
    guide_assets: list[dict],
    coord_scale: float = 1.0,
) -> None:
    export_sig = _export_signature(layers)
    full_layers = _scale_layers_coords(layers, coord_scale)
    composite_image = compose_window_layers(working_image, full_layers, guide_assets)
    saved_path = save_composite_image(composite_image)
    st.session_state["window_layer_state"] = full_layers
    st.session_state["window_composite_result"] = composite_image
    st.session_state["window_composite_saved_path"] = saved_path
    st.session_state["window_last_export_sig"] = export_sig


def _render_composite_result_section() -> None:
    composite_image = st.session_state.get("window_composite_result")
    if composite_image is None:
        return

    st.divider()
    st.markdown("### 합성 결과")
    saved_path = st.session_state.get("window_composite_saved_path")
    if saved_path:
        st.caption(f"자동 저장: `{saved_path}`")
    st.image(composite_image, use_container_width=True)

    buffer = io.BytesIO()
    composite_image.save(buffer, format="JPEG", quality=95)
    st.download_button(
        "합성 이미지 다운로드",
        data=buffer.getvalue(),
        file_name="window_composite.jpg",
        mime="image/jpeg",
        use_container_width=True,
        key="window_download_composite",
    )


def _first_asset(assets: list[dict], category: str) -> dict | None:
    for asset in assets:
        if asset["category"] == category:
            return asset
    return None


def _fit_preview_image(asset: dict | None) -> str | None:
    if asset is None:
        return None
    image = asset["image"].convert("RGBA")
    scale = min(GUIDE_IMAGE_SIZE / image.width, GUIDE_IMAGE_SIZE / image.height)
    width = max(1, int(image.width * scale))
    height = max(1, int(image.height * scale))
    fitted = image.resize((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (GUIDE_IMAGE_SIZE, GUIDE_IMAGE_SIZE), (255, 255, 255, 0))
    offset = ((GUIDE_IMAGE_SIZE - width) // 2, (GUIDE_IMAGE_SIZE - height) // 2)
    canvas.paste(fitted, offset, fitted if fitted.mode == "RGBA" else None)
    return image_to_data_uri(canvas)


def _guide_card_html(title: str, asset: dict | None) -> str:
    uri = _fit_preview_image(asset)
    if uri:
        image_block = f'<img src="{uri}" alt="{title}" />'
    else:
        image_block = '<div class="guide-empty">이미지 없음</div>'

    return f"""
<div class="guide-card">
  <div class="guide-title">{title}</div>
  <div class="guide-image">{image_block}</div>
  <div class="guide-note">드래그하여 배치</div>
</div>
"""


def build_guide_preview_html(assets: list[dict]) -> str:
    sheet_asset = _first_asset(assets, "시트지")
    fixture_asset = _first_asset(assets, "집기")

    return f"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 0;
    font-family: "Segoe UI", sans-serif;
    background: transparent;
    color: #1c2434;
    display: flex;
    justify-content: flex-start;
    align-items: flex-start;
  }}
  .guide-row {{
    display: flex;
    flex-wrap: nowrap;
    align-items: stretch;
    justify-content: flex-start;
    gap: 12px;
  }}
  .guide-card {{
    width: {GUIDE_CARD_WIDTH}px;
    height: {GUIDE_CARD_HEIGHT}px;
    border: 1px solid #e5e0d8;
    border-radius: 10px;
    background: #fff;
    padding: 10px 12px 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }}
  .guide-title {{
    font-size: 0.84rem;
    font-weight: 600;
    color: #1c2434;
    margin-bottom: 8px;
    flex: 0 0 auto;
    width: 100%;
    text-align: center;
  }}
  .guide-image {{
    width: {GUIDE_IMAGE_SIZE}px;
    height: {GUIDE_IMAGE_SIZE}px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1 1 auto;
  }}
  .guide-image img {{
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    display: block;
  }}
  .guide-empty {{
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f3f1ec;
    border-radius: 6px;
    color: #6b7280;
    font-size: 0.78rem;
  }}
  .guide-note {{
    margin-top: 8px;
    font-size: 0.75rem;
    color: #6b7280;
    text-align: center;
    flex: 0 0 auto;
    width: 100%;
  }}
</style>
</head>
<body>
  <div class="guide-row">
    {_guide_card_html("시트지", sheet_asset)}
    {_guide_card_html("집기", fixture_asset)}
  </div>
</body>
</html>
"""


def render_guide_preview(assets: list[dict]) -> None:
    st.markdown("**가이드 에셋**")
    preview_key = st.session_state.get("window_guide_assets_key", "")
    preview_html = st.session_state.get("window_guide_preview_html")
    if not preview_html or st.session_state.get("window_guide_preview_key") != preview_key:
        preview_html = build_guide_preview_html(assets)
        st.session_state["window_guide_preview_html"] = preview_html
        st.session_state["window_guide_preview_key"] = preview_key
    components.html(
        preview_html,
        height=GUIDE_CARD_HEIGHT + 20,
        scrolling=False,
    )


def _render_window_cleanup_step(base_image: Image.Image, working_image: Image.Image) -> None:
    st.subheader("1단계 · 유리창 홍보물 제거")

    upload_col, preview_col = st.columns([1.15, 1], gap="medium")
    with upload_col:
        interior_upload = mobile_photo_uploader(
            "가려진 유리창 안쪽 참고 사진 (선택)",
            key="window_interior_reference_upload",
            help_text=(
                "홍보물·시트지 뒤에 가려진 유리창 안쪽(매장 내부) 사진을 올리면 "
                "제거·합성 결과가 더 자연스러워집니다."
            ),
            show_mobile_hint=True,
        )
        interior_reference = _sync_interior_reference(interior_upload)
        if interior_reference is None:
            st.markdown(
                """
<div class="window-interior-caption">
  유리창 홍보물 뒤에 가려진 <strong>매장 내부</strong>가 보이는 사진을 올려 주세요.
  없으면 AI가 주변 배경만 참고해 복원합니다.
</div>
""",
                unsafe_allow_html=True,
            )
    with preview_col:
        if interior_reference is not None:
            st.image(
                interior_reference,
                caption="안쪽 참고 사진",
                width=220,
            )
            if st.button("안쪽 참고 사진 제거", key="window_clear_interior"):
                st.session_state.pop("window_interior_reference", None)
                st.session_state.pop("window_interior_signature", None)
                st.rerun()

    st.text_area(
        "가려진 영역 · 참고 사진 설명 (선택)",
        key="window_removal_notes",
        height=96,
        placeholder=(
            "예: 좌측 유리창 중앙 캠페인 시트지 뒤에 선반과 조명이 보여야 함. "
            "참고 사진은 매장 내부를 정면에서 촬영한 것."
        ),
        help=(
            "가려진 부분에 실제로 보여야 할 내용, 참고 사진 설명, "
            "제거할 홍보물 종류 등을 적어 주세요."
        ),
    )

    interior_reference = st.session_state.get("window_interior_reference")
    removal_notes = st.session_state.get("window_removal_notes", "")

    render_window_rect_selector(
        working_image,
        key_prefix="window",
        promo_remove_runner=lambda rect_data: _run_window_promo_remove(
            base_image,
            rect_data,
            interior_reference=interior_reference,
            removal_notes=removal_notes,
        ),
    )

    cleanup_ready = is_cleanup_ready_for_remove()

    remove_col, clear_col, proceed_col = st.columns([1.3, 0.9, 1.4], gap="small")
    with remove_col:
        if st.button(
            "선택 영역 홍보물 제거",
            type="primary",
            use_container_width=True,
            disabled=not cleanup_ready,
            key="window_remove_promo_btn",
        ):
            st.session_state["window_pending_promo_remove"] = True
            st.rerun()
    with clear_col:
        if st.button("선택 초기화", use_container_width=True, key="window_clear_selection"):
            st.session_state.pop("window_cleanup_rect", None)
            st.session_state.pop("window_cleanup_mask", None)
            st.session_state.pop("window_cleanup_mask_shape", None)
            st.session_state.pop("window_confirmed_cleanup_mode", None)
            st.session_state.pop("window_confirmed_cleanup_rect", None)
            st.session_state.pop("window_cleanup_confirmed", None)
            st.session_state.pop("window_rect_points", None)
            st.session_state.pop("window_last_click", None)
            st.rerun()
    with proceed_col:
        if st.button(
            "시트지·집기 합성 단계로",
            use_container_width=True,
            key="window_proceed_compose",
        ):
            _enter_compose_step(promo_removed=_promo_was_removed())

    if working_image is not base_image:
        st.markdown("**현재 정리된 사진**")
        st.image(working_image, use_container_width=True)

    if st.button(
        "홍보물 제거 건너뛰고 합성 단계로",
        key="window_skip_cleanup",
        help="시트지 PNG 가운데 투명 영역에는 업로드한 외부 사진(기존 홍보물)이 그대로 보입니다.",
    ):
        _enter_compose_step(promo_removed=False)


def _render_window_page_header() -> None:
    st.markdown(
        """
<style>
.window-page-title {
    color: #1c2434;
    font-size: 2.25rem;
    font-weight: 700;
    margin: 0.15rem 0 0.35rem 0;
    padding: 0;
    line-height: 1.2;
}
</style>
""",
        unsafe_allow_html=True,
    )

    st.markdown('<h1 translate="no" class="window-page-title">Window</h1>', unsafe_allow_html=True)
    st.caption(
        "1) 외부 사진을 업로드하고 **①→② 클릭**으로 유리창·홍보물 영역을 지정해 **제거**한 뒤, "
        "2) **시트지·집기** 가이드를 드래그해 합성하세요."
    )


def _render_window_page_body() -> None:
    guide_assets = _get_guide_assets()
    if not guide_assets:
        st.warning(
            "유리창 가이드 에셋을 찾을 수 없습니다.\n\n"
            f"- 시트지: `{SHEET_DIR}`\n"
            f"- 집기: `{FIXTURE_DIR}`\n\n"
            "위 폴더에 PNG/JPG 이미지 파일을 넣어 주세요."
        )
        return

    render_guide_preview(guide_assets)

    st.subheader("매장 외부 사진")
    uploaded_file = mobile_photo_uploader(
        "외부 사진 업로드",
        key="window_external_upload",
        help_text="매장 외부(유리창·전면) 사진을 촬영하거나 앨범에서 선택하세요.",
        show_mobile_hint=True,
    )

    if uploaded_file is None:
        st.info("외부 사진을 업로드하면 홍보물 제거 후 시트지·집기를 합성할 수 있습니다.")
        return

    file_signature = f"{uploaded_file.name}:{uploaded_file.size}"
    if st.session_state.get("window_upload_signature") != file_signature:
        _reset_window_workflow(keep_upload_signature=file_signature)

    base_image = _sync_base_image(uploaded_file)
    working_image = _working_image(base_image)
    cleanup_complete = st.session_state.get("window_cleanup_complete", False)

    if not cleanup_complete:
        _render_window_cleanup_step(base_image, working_image)
        return

    with st.expander("1단계 · 유리창 홍보물 제거 (완료)", expanded=False):
        bg_caption = (
            "홍보물 제거 후 배경 사진"
            if _promo_was_removed()
            else "업로드된 외부 사진 (홍보물 제거 안 함)"
        )
        st.image(working_image, caption=bg_caption, use_container_width=True)
        if st.button("1단계(홍보물 제거)로 돌아가기", key="window_back_cleanup"):
            st.session_state.pop("window_cleanup_complete", None)
            st.rerun()

    st.subheader("2단계 · 시트지 · 집기 드래그 합성")
    if not _promo_was_removed():
        st.warning(
            "**홍보물 제거 없이 진행 중입니다.** 시트지 PNG는 GUCCI 검은 바·테두리만 불투명하고 "
            "**가운데 유리창 영역은 투명**합니다. 따라서 업로드한 외부 사진의 기존 홍보물·매장 내부가 "
            "그대로 비쳐 보여 흐릿하거나 겹쳐 보일 수 있습니다. "
            "1단계에서 홍보물을 먼저 제거한 뒤 합성하면 더 정확합니다."
        )
    st.caption(
        "왼쪽 팔레트에서 에셋을 배치한 뒤 「합성 이미지 적용」을 누르세요. "
        "선택 후 **상단·우측 점선 중간 핸들**로 높이·너비를 각각 조절할 수 있습니다."
    )

    if st.session_state.get("window_show_composite_only"):
        saved_path = st.session_state.get("window_composite_saved_path")
        if saved_path:
            st.success(f"합성 이미지가 저장되었습니다: `{saved_path}`")
        _render_composite_result_section()
        if st.button("합성기에서 다시 편집", key="window_back_to_compositor"):
            st.session_state.pop("window_show_composite_only", None)
            st.session_state["window_restore_layers"] = True
            st.session_state["window_compositor_nonce"] = (
                int(st.session_state.get("window_compositor_nonce", 0)) + 1
            )
            st.rerun()
        return

    if st.session_state.get("window_compositor_version") != COMPOSITOR_UI_VERSION:
        st.session_state["window_compositor_version"] = COMPOSITOR_UI_VERSION
        _invalidate_compositor_cache(bump_nonce=True)

    compositor_nonce = int(st.session_state.get("window_compositor_nonce", 0))
    compositor_assets = _guide_assets_for_compositor(guide_assets)
    restore_layers = bool(st.session_state.pop("window_restore_layers", False))
    initial_layers = (
        st.session_state.get("window_layer_state") if restore_layers else []
    )
    selected_layer_id = (
        st.session_state.get("window_selected_layer_id") if restore_layers else None
    )

    @st.fragment
    def _compositor_fragment() -> None:
        compositor_html = _get_compositor_html(
            working_image=working_image,
            compositor_assets=compositor_assets,
            compositor_nonce=compositor_nonce,
            layers=initial_layers,
            selected_layer_id=selected_layer_id,
            restore_layers=restore_layers,
        )
        compositor_result = components.html(
            compositor_html,
            height=COMPOSITOR_HEIGHT,
            scrolling=True,
        )
        if compositor_result is not None:
            st.session_state["window_compositor_raw"] = compositor_result

        parsed_result = _parse_compositor_result(compositor_result)
        if not parsed_result or parsed_result.get("action") != "export":
            return

        layers = parsed_result.get("layers") or []
        composite_uri = parsed_result.get("composite")
        if not layers and not composite_uri:
            return

        export_sig = (
            _export_signature(layers)
            if layers
            else (composite_uri[:240] if composite_uri else "")
        )
        if export_sig == st.session_state.get("window_last_export_sig"):
            return

        coord_scale = float(st.session_state.get("window_compositor_coord_scale", 1.0))
        try:
            if layers:
                _compose_layers_and_store(
                    layers,
                    working_image=working_image,
                    guide_assets=guide_assets,
                    coord_scale=coord_scale,
                )
            elif composite_uri:
                _store_client_composite(
                    composite_uri,
                    layers,
                    working_image=working_image,
                    guide_assets=guide_assets,
                    coord_scale=coord_scale,
                )
            saved_path = st.session_state.get("window_composite_saved_path")
            if saved_path:
                st.success(f"합성 이미지가 저장되었습니다.\n\n`{saved_path}`")
        except Exception as exc:
            st.error(f"합성에 실패했습니다: {exc}")
        return

    _compositor_fragment()

    composite_image = st.session_state.get("window_composite_result")
    if composite_image is not None:
        with st.expander("이전 합성 결과 보기", expanded=False):
            _render_composite_result_section()


def render_window_page() -> None:
    inject_english_widget_guard(WINDOW_ENGLISH_LABELS)
    inject_mobile_upload_styles()
    _render_window_page_header()
    _render_window_page_body()
