import json
from collections.abc import Callable

import streamlit as st
from PIL import Image, ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

from coordinate_picker import display_point_to_original, prepare_display_image

MAX_SELECTION_WIDTH = 720
MIN_RECT_SIZE = 24
POINT_LABELS = ("① 시작", "② 끝")


def _normalize_rect(rect: dict) -> dict:
    return {
        "x": round(float(rect["x"])),
        "y": round(float(rect["y"])),
        "width": round(float(rect["width"])),
        "height": round(float(rect["height"])),
    }


def _rects_equal(a: dict | None, b: dict | None, *, tolerance: float = 0.5) -> bool:
    if a is None or b is None:
        return a is b
    for key in ("x", "y", "width", "height"):
        if abs(float(a[key]) - float(b[key])) > tolerance:
            return False
    return True


def _validate_rect(rect: dict) -> dict | None:
    try:
        width = float(rect["width"])
        height = float(rect["height"])
        x = float(rect["x"])
        y = float(rect["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if width < MIN_RECT_SIZE - 0.5 or height < MIN_RECT_SIZE - 0.5:
        return None
    return {"x": x, "y": y, "width": width, "height": height}


def _clamp_rect(rect: dict, *, max_width: int, max_height: int) -> dict:
    x = max(0.0, min(float(rect["x"]), max_width - MIN_RECT_SIZE))
    y = max(0.0, min(float(rect["y"]), max_height - MIN_RECT_SIZE))
    width = max(MIN_RECT_SIZE, min(float(rect["width"]), max_width - x))
    height = max(MIN_RECT_SIZE, min(float(rect["height"]), max_height - y))
    return {"x": x, "y": y, "width": width, "height": height}


def _rect_from_original_points(
    p1: tuple[float, float],
    p2: tuple[float, float],
    *,
    max_width: int,
    max_height: int,
) -> dict | None:
    left = min(float(p1[0]), float(p2[0]))
    top = min(float(p1[1]), float(p2[1]))
    width = max(MIN_RECT_SIZE, abs(float(p2[0]) - float(p1[0])))
    height = max(MIN_RECT_SIZE, abs(float(p2[1]) - float(p1[1])))
    return _validate_rect(
        _clamp_rect(
            {"x": left, "y": top, "width": width, "height": height},
            max_width=max_width,
            max_height=max_height,
        )
    )


def _resolve_draft_cleanup_rect(
    *,
    max_width: int,
    max_height: int,
    key_prefix: str,
) -> dict | None:
    draft = st.session_state.get("window_cleanup_rect")
    if isinstance(draft, dict):
        validated = _validate_rect(
            _clamp_rect(
                _normalize_rect(draft),
                max_width=max_width,
                max_height=max_height,
            )
        )
        if validated is not None:
            return validated

    points = list(st.session_state.get(f"{key_prefix}_rect_points") or [])
    if len(points) >= 2:
        return _rect_from_original_points(
            points[0],
            points[1],
            max_width=max_width,
            max_height=max_height,
        )
    return None


def _store_selector_rect(rect: dict, *, confirmed: bool) -> dict:
    normalized = _normalize_rect(rect)
    st.session_state["window_cleanup_rect"] = normalized
    if confirmed:
        st.session_state["window_confirmed_cleanup_rect"] = normalized
        st.session_state["window_cleanup_confirmed"] = True
    return normalized


def is_cleanup_ready_for_remove() -> bool:
    image_size = st.session_state.get("window_selector_image_size")
    if isinstance(image_size, (list, tuple)) and len(image_size) == 2:
        max_width = int(image_size[0])
        max_height = int(image_size[1])
        if max_width > 0 and max_height > 0:
            if _resolve_draft_cleanup_rect(
                max_width=max_width,
                max_height=max_height,
                key_prefix="window",
            ) is not None:
                return True

    for key in ("window_confirmed_cleanup_rect", "window_cleanup_rect"):
        rect = st.session_state.get(key)
        if isinstance(rect, dict) and _validate_rect(_normalize_rect(rect)) is not None:
            return True
    return False


def get_confirmed_cleanup_rect() -> dict | None:
    confirmed = st.session_state.get("window_confirmed_cleanup_rect")
    if isinstance(confirmed, dict):
        return _validate_rect(_normalize_rect(confirmed))
    return None


def confirm_cleanup_rect_from_session(
    *,
    key_prefix: str = "window",
    image: Image.Image | None = None,
) -> dict | None:
    if image is not None:
        max_width = image.width
        max_height = image.height
    else:
        image_size = st.session_state.get("window_selector_image_size")
        if not isinstance(image_size, (list, tuple)) or len(image_size) != 2:
            return None
        max_width = int(image_size[0])
        max_height = int(image_size[1])

    rect = _resolve_draft_cleanup_rect(
        max_width=max_width,
        max_height=max_height,
        key_prefix=key_prefix,
    )
    if rect is None:
        return None
    return _store_selector_rect(rect, confirmed=True)


def sync_selector_rect_from_session(
    *,
    key_prefix: str = "window",
    image: Image.Image | None = None,
) -> dict | None:
    return confirm_cleanup_rect_from_session(key_prefix=key_prefix, image=image)


def _clear_selection_state(*, key_prefix: str = "window") -> None:
    for key in (
        "window_cleanup_rect",
        "window_confirmed_cleanup_rect",
        "window_cleanup_confirmed",
        f"{key_prefix}_rect_points",
        f"{key_prefix}_last_click",
        f"{key_prefix}_adj_x",
        f"{key_prefix}_adj_y",
        f"{key_prefix}_adj_w",
        f"{key_prefix}_adj_h",
    ):
        st.session_state.pop(key, None)


def _clear_confirmed_selection() -> None:
    st.session_state.pop("window_confirmed_cleanup_rect", None)
    st.session_state.pop("window_cleanup_confirmed", None)


def _original_points_to_display(
    points: list[tuple[float, float]],
    scale: float,
) -> list[tuple[float, float]]:
    return [(float(x) * scale, float(y) * scale) for x, y in points]


def _draw_rect_selector(
    image: Image.Image,
    points: list[tuple[float, float]],
) -> Image.Image:
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    for index, (x, y) in enumerate(points):
        radius = max(6, min(image.size) // 120)
        draw.ellipse(
            [(x - radius, y - radius), (x + radius, y + radius)],
            fill="#ef4444",
            outline="#ffffff",
            width=2,
        )
        draw.text((x + radius + 4, y - radius - 2), POINT_LABELS[index], fill="#b42318")

    if len(points) == 2:
        x1, y1 = points[0]
        x2, y2 = points[1]
        left = min(x1, x2)
        top = min(y1, y2)
        right = max(x1, x2)
        bottom = max(y1, y2)
        draw.rectangle([left, top, right, bottom], outline="#ef4444", width=3)
    return annotated


def render_window_rect_selector(
    image: Image.Image,
    *,
    key_prefix: str = "window",
    promo_remove_runner: Callable[[dict], bool] | None = None,
) -> dict | None:
    st.caption(
        "① **시작점** → ② **끝점** 클릭 → **「✓ 선택 영역 확정」** → **홍보물 제거**"
    )

    points_key = f"{key_prefix}_rect_points"
    click_key = f"{key_prefix}_last_click"
    if points_key not in st.session_state:
        st.session_state[points_key] = []

    undo_col, reset_col, _ = st.columns([1, 1, 3])
    with undo_col:
        if st.button("마지막 점 취소", key=f"{key_prefix}_undo", use_container_width=True):
            points = list(st.session_state.get(points_key) or [])
            if points:
                points.pop()
                st.session_state[points_key] = points
                st.session_state.pop(click_key, None)
                if len(points) < 2:
                    st.session_state.pop("window_cleanup_rect", None)
                    _clear_confirmed_selection()
            st.rerun()
    with reset_col:
        if st.button("영역 초기화", key=f"{key_prefix}_reset", use_container_width=True):
            _clear_selection_state(key_prefix=key_prefix)
            st.rerun()

    display_image, display_scale = prepare_display_image(image, max_width=MAX_SELECTION_WIDTH)
    st.session_state["window_selector_display_scale"] = display_scale
    st.session_state["window_selector_image_size"] = (image.width, image.height)

    original_points: list[tuple[float, float]] = list(st.session_state.get(points_key) or [])
    display_points = _original_points_to_display(original_points, display_scale)
    annotated_display = (
        _draw_rect_selector(display_image, display_points)
        if display_points
        else display_image
    )

    if len(original_points) == 0:
        st.info("① 시작점 → ② 끝점 순서로 사진을 **클릭**해 제거할 영역을 지정하세요.")
    elif len(original_points) == 1:
        st.info("② 끝점을 **클릭**해 영역을 완성하세요.")

    click = streamlit_image_coordinates(
        annotated_display,
        key=f"{key_prefix}_picker",
        width=annotated_display.width,
    )

    if click and click != st.session_state.get(click_key):
        points = list(st.session_state.get(points_key) or [])
        if len(points) >= 2:
            points = []
        if len(points) < 2:
            point = display_point_to_original(float(click["x"]), float(click["y"]), display_scale)
            points.append(point)
            st.session_state[points_key] = points
        st.session_state[click_key] = click
        _clear_confirmed_selection()
        st.rerun()

    active_rect = _resolve_draft_cleanup_rect(
        max_width=image.width,
        max_height=image.height,
        key_prefix=key_prefix,
    )
    if active_rect is not None and len(original_points) >= 2:
        if not st.session_state.get("window_cleanup_confirmed"):
            _store_selector_rect(active_rect, confirmed=False)

    apply_col, status_col, _ = st.columns([1.2, 1.5, 2])
    with apply_col:
        if st.button(
            "✓ 선택 영역 확정",
            type="primary",
            use_container_width=True,
            key=f"{key_prefix}_apply_selection",
        ):
            rect = _resolve_draft_cleanup_rect(
                max_width=image.width,
                max_height=image.height,
                key_prefix=key_prefix,
            )
            if rect is not None:
                _store_selector_rect(rect, confirmed=True)
                st.success(
                    f"선택 영역 확정: {int(rect['width'])} x {int(rect['height'])}px · "
                    "이제 「선택 영역 홍보물 제거」를 누를 수 있습니다."
                )
                st.rerun()
            else:
                st.warning("먼저 ①→② 순서로 사진을 클릭해 영역을 지정해 주세요.")

    with status_col:
        if promo_remove_runner is not None and st.session_state.pop(
            "window_pending_promo_remove", False
        ):
            pending_rect = (
                st.session_state.get("window_confirmed_cleanup_rect")
                or st.session_state.get("window_cleanup_rect")
            )
            if pending_rect:
                with st.spinner("🔄 홍보물 제거 중... (30~90초)"):
                    if promo_remove_runner(pending_rect):
                        st.session_state.pop("window_confirmed_cleanup_rect", None)
                        st.session_state.pop("window_cleanup_confirmed", None)
                        st.rerun()
            else:
                st.warning("먼저 사진에서 영역을 지정하고 「✓ 선택 영역 확정」을 눌러 주세요.")

    if active_rect is None:
        return None

    st.markdown("**세부 조정** (픽셀 단위)")
    max_w = image.width
    max_h = image.height
    adj1, adj2, adj3, adj4 = st.columns(4)
    with adj1:
        new_x = st.number_input(
            "X",
            min_value=0,
            max_value=max(0, max_w - MIN_RECT_SIZE),
            value=int(round(active_rect["x"])),
            step=1,
            key=f"{key_prefix}_adj_x",
        )
    with adj2:
        new_y = st.number_input(
            "Y",
            min_value=0,
            max_value=max(0, max_h - MIN_RECT_SIZE),
            value=int(round(active_rect["y"])),
            step=1,
            key=f"{key_prefix}_adj_y",
        )
    with adj3:
        new_w = st.number_input(
            "너비",
            min_value=MIN_RECT_SIZE,
            max_value=max_w,
            value=int(round(active_rect["width"])),
            step=1,
            key=f"{key_prefix}_adj_w",
        )
    with adj4:
        new_h = st.number_input(
            "높이",
            min_value=MIN_RECT_SIZE,
            max_value=max_h,
            value=int(round(active_rect["height"])),
            step=1,
            key=f"{key_prefix}_adj_h",
        )

    adjusted = _normalize_rect(
        _clamp_rect(
            {"x": new_x, "y": new_y, "width": new_w, "height": new_h},
            max_width=max_w,
            max_height=max_h,
        )
    )
    confirmed = st.session_state.get("window_cleanup_confirmed", False)
    if not confirmed:
        if not _rects_equal(adjusted, active_rect, tolerance=3.0):
            _store_selector_rect(adjusted, confirmed=False)
            active_rect = adjusted
    elif not _rects_equal(adjusted, active_rect, tolerance=3.0):
        _store_selector_rect(adjusted, confirmed=True)
        active_rect = adjusted

    if st.session_state.get("window_cleanup_confirmed") and is_cleanup_ready_for_remove():
        st.success(
            f"선택 영역 확정: {int(active_rect['width'])} x {int(active_rect['height'])}px · "
            "이제 「선택 영역 홍보물 제거」를 누를 수 있습니다."
        )
        return get_confirmed_cleanup_rect() or active_rect

    st.info(
        f"임시 선택: {int(active_rect['width'])} x {int(active_rect['height'])}px · "
        "**「✓ 선택 영역 확정」**을 눌러 주세요."
    )
    return None
