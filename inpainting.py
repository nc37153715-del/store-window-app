import base64
import io

import cv2
import numpy as np
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFilter

from brand_guides import get_brand_guide_hint
from overlay import perspective_tray_overlay

INPAINT_PROMPT = (
    "매장 내부 사진의 선택된 진열장 영역에 "
    "모던하고 고급스러운 안경 진열대 가구와 안경들이 정돈된 모습을 "
    "주변 환경의 조명, 색감, 원근감과 자연스럽게 어울리도록 고화질로 생성해 주세요. "
    "선택 영역 밖의 벽, 바닥, 천장, 조명은 그대로 유지하고 진열장 부분만 현실적인 실내 사진처럼 완성해 주세요."
)

INPAINT_PROMPT_AFTER_OVERLAY = (
    "선택된 진열장 영역의 흰색 디스플레이 트레이와 선반 구조는 그대로 유지하면서, "
    "각 트레이 위에 안경과 선글라스를 정돈해 배치해 주세요. "
    "모던하고 고급스러운 매장 인테리어 사진처럼, 주변 조명·색감·원근감과 자연스럽게 어울리게 완성해 주세요. "
    "선택 영역 밖은 변경하지 마세요."
)

# DALL-E 3는 Image Edit API(마스크 인페인팅)를 지원하지 않습니다.
# OpenAI images.edit + mask 조합은 gpt-image / dall-e-2 모델을 사용합니다.
DEFAULT_EDIT_MODEL = "gpt-image-1.5"
SUPPORTED_EDIT_MODELS = (
    "gpt-image-1.5",
    "gpt-image-1",
    "gpt-image-1-mini",
    "dall-e-2",
)
MAX_IMAGE_EDGE = 1536
CROP_INPAINT_MAX_AREA_RATIO = 0.45
CROP_PADDING_RATIO = 0.45
MIN_CROP_PADDING = 48


def normalize_rect(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    image_width: int,
    image_height: int,
    min_size: int = 32,
) -> tuple[int, int, int, int]:
    left = int(max(0, min(x1, x2)))
    top = int(max(0, min(y1, y2)))
    right = int(min(image_width, max(x1, x2)))
    bottom = int(min(image_height, max(y1, y2)))

    if right - left < min_size:
        right = min(image_width, left + min_size)
    if bottom - top < min_size:
        bottom = min(image_height, top + min_size)

    return left, top, right, bottom


def rect_to_quad(rect: tuple[int, int, int, int]) -> list[tuple[float, float]]:
    left, top, right, bottom = rect
    return [
        (left, top),
        (right, top),
        (right, bottom),
        (left, bottom),
    ]


def build_brand_inpaint_prompt(
    brand: str,
    *,
    base_prompt: str = INPAINT_PROMPT,
    after_overlay: bool = False,
) -> str:
    guide_hint = get_brand_guide_hint(brand)
    overlay_note = (
        "이미 합성된 흰색 트레이 레이아웃을 유지한 채 "
        if after_overlay
        else ""
    )
    return (
        f"{base_prompt} "
        f"{overlay_note}"
        f"브랜드 {brand} {guide_hint} "
        "설치 완료 가이드 사진의 트레이 배치·밀도·전시 스타일을 최대한 재현해 주세요."
    )


def apply_guide_tray_overlay(
    image: Image.Image,
    rect: tuple[int, int, int, int],
    guide_image: Image.Image,
) -> Image.Image:
    """설치 완료 가이드 사진 기준으로 흰색 트레이를 원근 보정해 합성합니다."""
    return perspective_tray_overlay(
        image.convert("RGB"),
        guide_image,
        rect_to_quad(rect),
    )


def create_inpaint_mask(
    image_size: tuple[int, int],
    rect: tuple[int, int, int, int],
) -> Image.Image:
    """OpenAI edit API용 마스크. 투명(alpha=0) 영역이 편집 대상입니다."""
    width, height = image_size
    mask = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(mask)
    draw.rectangle(rect, fill=(0, 0, 0, 0))
    return mask


def apply_rect_only(
    original: Image.Image,
    edited: Image.Image,
    edit_rect: tuple[int, int, int, int],
) -> Image.Image:
    """선택 영역 안만 결과를 반영하고, 바깥은 원본 픽셀을 그대로 유지합니다."""
    original_rgb = original.convert("RGB")
    edited_rgb = edited.convert("RGB")
    if edited_rgb.size != original_rgb.size:
        edited_rgb = edited_rgb.resize(original_rgb.size, Image.Resampling.LANCZOS)

    left, top, right, bottom = normalize_rect(
        *edit_rect,
        image_width=original_rgb.width,
        image_height=original_rgb.height,
    )
    output = original_rgb.copy()
    patch = edited_rgb.crop((left, top, right, bottom))
    output.paste(patch, (left, top))
    return output


def apply_rect_feathered(
    original: Image.Image,
    edited: Image.Image,
    edit_rect: tuple[int, int, int, int],
    *,
    feather: int | None = None,
) -> Image.Image:
    """선택 영역만 반영하되 가장자리는 원본과 부드럽게 블렌딩합니다."""
    original_rgb = original.convert("RGB")
    edited_rgb = edited.convert("RGB")
    if edited_rgb.size != original_rgb.size:
        edited_rgb = edited_rgb.resize(original_rgb.size, Image.Resampling.LANCZOS)

    left, top, right, bottom = normalize_rect(
        *edit_rect,
        image_width=original_rgb.width,
        image_height=original_rgb.height,
    )
    merged = original_rgb.copy()
    patch = edited_rgb.crop((left, top, right, bottom))
    merged.paste(patch, (left, top))
    return blend_inpaint_result(original_rgb, merged, edit_rect, feather=feather)


def cleanup_promo_color_artifacts(
    original: Image.Image,
    edited: Image.Image,
    edit_rect: tuple[int, int, int, int],
) -> Image.Image:
    """선택 영역 안 AI·원본에 남은 노란·주황·빨간 홍보물 잔색을 주변 질감으로 보정합니다."""
    original_rgb = original.convert("RGB")
    edited_rgb = edited.convert("RGB")
    if edited_rgb.size != original_rgb.size:
        edited_rgb = edited_rgb.resize(original_rgb.size, Image.Resampling.LANCZOS)

    left, top, right, bottom = normalize_rect(
        *edit_rect,
        image_width=original_rgb.width,
        image_height=original_rgb.height,
    )
    width = right - left
    height = bottom - top
    if width < 8 or height < 8:
        return edited_rgb

    patch_rgb = np.array(edited_rgb.crop((left, top, right, bottom)))
    hsv = cv2.cvtColor(patch_rgb, cv2.COLOR_RGB2HSV)

    yellow = cv2.inRange(hsv, (14, 55, 70), (48, 255, 255))
    orange = cv2.inRange(hsv, (5, 70, 80), (22, 255, 255))
    bright_red = cv2.inRange(hsv, (0, 90, 80), (12, 255, 255))
    promo_mask = cv2.bitwise_or(yellow, cv2.bitwise_or(orange, bright_red))

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    promo_mask = cv2.morphologyEx(promo_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    promo_mask = cv2.dilate(promo_mask, kernel, iterations=1)

    if cv2.countNonZero(promo_mask) < 40:
        return edited_rgb

    patch_bgr = cv2.cvtColor(patch_rgb, cv2.COLOR_RGB2BGR)
    filled = cv2.inpaint(patch_bgr, promo_mask, 7, cv2.INPAINT_NS)

    # 경계는 원본·주변 픽셀과 섞어 직사각형 티를 줄입니다.
    edge = max(6, min(24, int(min(width, height) * 0.08)))
    blend = np.linspace(0.0, 1.0, edge, dtype=np.float32)
    result_patch = filled.astype(np.float32)
    for offset in range(edge):
        alpha = blend[offset]
        if offset < height:
            row = offset
            src = patch_bgr[row].astype(np.float32)
            result_patch[row] = src * (1.0 - alpha) + result_patch[row] * alpha
        if height - 1 - offset >= 0:
            row = height - 1 - offset
            src = patch_bgr[row].astype(np.float32)
            result_patch[row] = src * (1.0 - alpha) + result_patch[row] * alpha
        if offset < width:
            col = offset
            src = patch_bgr[:, col].astype(np.float32)
            result_patch[:, col] = src * (1.0 - alpha) + result_patch[:, col] * alpha
        if width - 1 - offset >= 0:
            col = width - 1 - offset
            src = patch_bgr[:, col].astype(np.float32)
            result_patch[:, col] = src * (1.0 - alpha) + result_patch[:, col] * alpha

    output = edited_rgb.copy()
    output.paste(
        Image.fromarray(cv2.cvtColor(np.clip(result_patch, 0, 255).astype(np.uint8), cv2.COLOR_BGR2RGB)),
        (left, top),
    )
    return output


def refine_lower_band_with_neighbors(
    original: Image.Image,
    edited: Image.Image,
    edit_rect: tuple[int, int, int, int],
    *,
    band_start_ratio: float = 0.55,
) -> Image.Image:
    """선택 영역 하단을 좌·우 원본과 맞춰 바닥선·높이 어긋남을 줄입니다."""
    original_rgb = original.convert("RGB")
    edited_rgb = edited.convert("RGB")
    if edited_rgb.size != original_rgb.size:
        edited_rgb = edited_rgb.resize(original_rgb.size, Image.Resampling.LANCZOS)

    left, top, right, bottom = normalize_rect(
        *edit_rect,
        image_width=original_rgb.width,
        image_height=original_rgb.height,
    )
    if left <= 0 or right >= original_rgb.width or bottom - top < 32:
        return edited_rgb

    original_arr = np.array(original_rgb, dtype=np.float32)
    edited_arr = np.array(edited_rgb, dtype=np.float32)
    band_start = top + int((bottom - top) * band_start_ratio)
    if band_start >= bottom - 2:
        return edited_rgb

    left_x = left - 1
    right_x = min(right, original_arr.shape[1] - 1)
    width = right - left
    xs = np.linspace(0.0, 1.0, width, dtype=np.float32)[:, None]

    for y in range(band_start, bottom):
        blend = (y - band_start) / max(1, bottom - band_start - 1)
        left_col = original_arr[y, left_x]
        right_col = original_arr[y, right_x]
        neighbors = left_col * (1.0 - xs) + right_col * xs
        edited_arr[y, left:right] = (
            edited_arr[y, left:right] * (1.0 - blend) + neighbors * blend
        )

    return Image.fromarray(np.clip(edited_arr, 0, 255).astype(np.uint8))


def expand_rect_with_padding(
    rect: tuple[int, int, int, int],
    image_size: tuple[int, int],
    *,
    padding_ratio: float = CROP_PADDING_RATIO,
    min_padding: int = MIN_CROP_PADDING,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    pad_x = max(min_padding, int(width * padding_ratio))
    pad_y = max(min_padding, int(height * padding_ratio))
    img_w, img_h = image_size
    return (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(img_w, right + pad_x),
        min(img_h, bottom + pad_y),
    )


def rect_area(rect: tuple[int, int, int, int]) -> int:
    left, top, right, bottom = rect
    return max(1, right - left) * max(1, bottom - top)


def should_use_crop_inpaint(
    edit_rect: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> bool:
    img_w, img_h = image_size
    return rect_area(edit_rect) < img_w * img_h * CROP_INPAINT_MAX_AREA_RATIO


def composite_crop_onto_image(
    full: Image.Image,
    crop_edited: Image.Image,
    crop_rect: tuple[int, int, int, int],
) -> Image.Image:
    result = full.convert("RGB").copy()
    left, top, right, bottom = crop_rect
    target_size = (max(1, right - left), max(1, bottom - top))
    patch = crop_edited.convert("RGB")
    if patch.size != target_size:
        patch = patch.resize(target_size, Image.Resampling.LANCZOS)
    result.paste(patch, (left, top))
    return result


def try_local_ground_promo_removal(
    image: Image.Image,
    edit_rect: tuple[int, int, int, int],
) -> Image.Image | None:
    """바닥·보도 홍보물(노란 안내판 등)을 주변 질감으로 로컬 복원합니다."""
    source = image.convert("RGB")
    img_w, img_h = source.size
    left, top, right, bottom = edit_rect
    width = right - left
    height = bottom - top
    if width < 16 or height < 16:
        return None

    # 유리창·매장 내부 영역에는 적용하지 않습니다. 사진 맨 아래 보도/바닥만 대상.
    if bottom < img_h * 0.84 or (top + bottom) / 2 < img_h * 0.78:
        return None
    if height > img_h * 0.22:
        return None

    context_top = max(0, top - int(height * 1.8))
    context_left = max(0, left - int(width * 0.6))
    context_right = min(img_w, right + int(width * 0.6))
    context_bottom = min(img_h, bottom + int(height * 0.2))
    context_rect = (context_left, context_top, context_right, context_bottom)

    cl, ct, cr, cb = context_rect
    context_bgr = cv2.cvtColor(
        np.array(source.crop(context_rect)),
        cv2.COLOR_RGB2BGR,
    )
    local_left = left - cl
    local_top = top - ct
    local_right = right - cl
    local_bottom = bottom - ct

    patch_h, patch_w = context_bgr.shape[:2]
    sign_mask = np.zeros((patch_h, patch_w), dtype=np.uint8)
    sign_mask[local_top:local_bottom, local_left:local_right] = 255

    filled = cv2.inpaint(context_bgr, sign_mask, 9, cv2.INPAINT_NS)

    result = source.copy()
    restored_patch = Image.fromarray(
        cv2.cvtColor(
            filled[local_top:local_bottom, local_left:local_right],
            cv2.COLOR_BGR2RGB,
        )
    )
    result.paste(restored_patch, (left, top))
    return result


def _neighbor_baseline_rgb(
    arr: np.ndarray,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> np.ndarray | None:
    """선택 영역 안을 좌·우·상·하 원본 픽셀로 보간한 기준 배경."""
    img_h, img_w = arr.shape[:2]
    height = bottom - top
    width = right - left
    if height < 4 or width < 4:
        return None

    horiz: np.ndarray | None = None
    if left > 0 and right < img_w:
        left_col = arr[top:bottom, left - 1].astype(np.float32)
        right_col = arr[top:bottom, right].astype(np.float32)
        alpha = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :, None]
        horiz = left_col[:, None, :] * (1.0 - alpha) + right_col[:, None, :] * alpha
    elif left > 0:
        horiz = np.repeat(arr[top:bottom, left - 1:left], width, axis=1).astype(np.float32)
    elif right < img_w:
        horiz = np.repeat(arr[top:bottom, right : right + 1], width, axis=1).astype(np.float32)

    vert: np.ndarray | None = None
    if top > 0 and bottom < img_h:
        top_row = arr[top - 1, left:right].astype(np.float32)
        bottom_row = arr[bottom, left:right].astype(np.float32)
        beta = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
        vert = top_row[None, :, :] * (1.0 - beta) + bottom_row[None, :, :] * beta
    elif top > 0:
        vert = np.repeat(arr[top - 1 : top, left:right], height, axis=0).astype(np.float32)
    elif bottom < img_h:
        vert = np.repeat(arr[bottom : bottom + 1, left:right], height, axis=0).astype(np.float32)

    if horiz is not None and vert is not None:
        return (horiz + vert) / 2.0
    return horiz if horiz is not None else vert


def _promo_mask_in_rect(
    arr: np.ndarray,
    left: int,
    top: int,
    right: int,
    bottom: int,
    *,
    baseline: np.ndarray | None = None,
) -> np.ndarray:
    """선택 영역 안 홍보물·스티커로 보이는 픽셀 마스크(0~255)."""
    patch = arr[top:bottom, left:right]
    if baseline is None:
        baseline = _neighbor_baseline_rgb(arr, left, top, right, bottom)
    if baseline is None:
        return np.full((bottom - top, right - left), 255, dtype=np.uint8)

    diff = np.linalg.norm(patch.astype(np.float32) - baseline, axis=2)
    promo_mask = (diff > 24.0).astype(np.uint8) * 255

    hsv = cv2.cvtColor(patch.astype(np.uint8), cv2.COLOR_RGB2HSV)
    sat_mask = (hsv[:, :, 1] > 65).astype(np.uint8) * 255
    bright_mask = ((hsv[:, :, 2] > 185) & (hsv[:, :, 1] > 35)).astype(np.uint8) * 255
    promo_mask = cv2.bitwise_or(promo_mask, cv2.bitwise_or(sat_mask, bright_mask))

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    promo_mask = cv2.morphologyEx(promo_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return promo_mask


def try_local_window_promo_removal(
    image: Image.Image,
    edit_rect: tuple[int, int, int, int],
) -> Image.Image | None:
    """유리창·외벽 홍보물을 좌우·상하 원본과 이어지게 로컬 복원합니다."""
    source = image.convert("RGB")
    img_w, img_h = source.size
    left, top, right, bottom = normalize_rect(
        *edit_rect,
        image_width=img_w,
        image_height=img_h,
    )
    width = right - left
    height = bottom - top
    if width < 16 or height < 16:
        return None
    if left <= 0 and right >= img_w - 1:
        return None

    arr = np.array(source, dtype=np.float32)
    baseline = _neighbor_baseline_rgb(arr, left, top, right, bottom)
    if baseline is None:
        return None

    promo_mask = _promo_mask_in_rect(arr, left, top, right, bottom, baseline=baseline)
    mask_ratio = cv2.countNonZero(promo_mask) / max(1, width * height)
    if mask_ratio < 0.02:
        return None

    patch = arr[top:bottom, left:right].copy()
    replace = promo_mask > 0
    patch[replace] = baseline[replace]

    pad = max(12, min(48, width // 5, height // 5))
    context_left = max(0, left - pad)
    context_top = max(0, top - pad)
    context_right = min(img_w, right + pad)
    context_bottom = min(img_h, bottom + pad)
    context_bgr = cv2.cvtColor(
        np.array(source.crop((context_left, context_top, context_right, context_bottom))),
        cv2.COLOR_RGB2BGR,
    )
    local_left = left - context_left
    local_top = top - context_top
    local_right = right - context_left
    local_bottom = bottom - context_top

    context_arr = context_bgr.astype(np.float32)
    context_arr[local_top:local_bottom, local_left:local_right] = cv2.cvtColor(
        np.clip(patch, 0, 255).astype(np.uint8),
        cv2.COLOR_RGB2BGR,
    )
    inpaint_mask = np.zeros(context_bgr.shape[:2], dtype=np.uint8)
    inpaint_mask[local_top:local_bottom, local_left:local_right] = promo_mask
    inpaint_mask = cv2.dilate(inpaint_mask, np.ones((3, 3), np.uint8), iterations=1)

    filled = cv2.inpaint(
        context_arr.astype(np.uint8),
        inpaint_mask,
        5,
        cv2.INPAINT_NS,
    )
    restored = filled[local_top:local_bottom, local_left:local_right]
    result = source.copy()
    result.paste(
        Image.fromarray(cv2.cvtColor(restored, cv2.COLOR_BGR2RGB)),
        (left, top),
    )
    return result


def is_ai_inpaint_unacceptable(
    original: Image.Image,
    edited: Image.Image,
    edit_rect: tuple[int, int, int, int],
) -> bool:
    """AI가 가구·바닥 등을 새로 그려 왜곡·톱니 경계가 생겼는지 검사합니다."""
    original_rgb = original.convert("RGB")
    edited_rgb = edited.convert("RGB")
    if edited_rgb.size != original_rgb.size:
        edited_rgb = edited_rgb.resize(original_rgb.size, Image.Resampling.LANCZOS)

    left, top, right, bottom = normalize_rect(
        *edit_rect,
        image_width=original_rgb.width,
        image_height=original_rgb.height,
    )
    width = right - left
    height = bottom - top
    if width < 24 or height < 24:
        return False

    orig_arr = np.array(original_rgb, dtype=np.float32)
    edit_arr = np.array(edited_rgb, dtype=np.float32)
    orig_patch = orig_arr[top:bottom, left:right]
    edit_patch = edit_arr[top:bottom, left:right]

    baseline = _neighbor_baseline_rgb(orig_arr, left, top, right, bottom)
    if baseline is not None:
        orig_err = float(np.mean(np.linalg.norm(orig_patch - baseline, axis=2)))
        edit_err = float(np.mean(np.linalg.norm(edit_patch - baseline, axis=2)))
        if edit_err > orig_err * 1.25 + 12.0:
            return True

    orig_gray = cv2.cvtColor(orig_patch.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    edit_gray = cv2.cvtColor(edit_patch.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    orig_lap = cv2.Laplacian(orig_gray, cv2.CV_64F).var()
    edit_lap = cv2.Laplacian(edit_gray, cv2.CV_64F).var()
    if edit_lap > max(120.0, orig_lap * 2.2):
        return True

    diff = np.mean(np.abs(edit_patch - orig_patch))
    if diff > 42.0 and edit_lap > orig_lap * 1.6:
        return True

    return False


def inpaint_with_mask(
    image: Image.Image,
    mask: np.ndarray,
    *,
    radius: int = 7,
    feather_sigma: float = 3.0,
) -> Image.Image:
    """스마트폰 마법 지우개처럼 마스크 영역을 주변 질감으로 채웁니다."""
    source = image.convert("RGB")
    arr = np.array(source, dtype=np.float32)
    img_h, img_w = arr.shape[:2]
    if mask.shape[:2] != (img_h, img_w):
        mask = cv2.resize(mask, (img_w, img_h), interpolation=cv2.INTER_NEAREST)

    inpaint_mask = ((mask > 0).astype(np.uint8)) * 255
    if cv2.countNonZero(inpaint_mask) < 40:
        return source

    filled_rgb = _propagate_fill_from_boundary(arr, inpaint_mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    edge_band = cv2.dilate(inpaint_mask, kernel, iterations=1)
    edge_band = cv2.subtract(edge_band, cv2.erode(inpaint_mask, kernel, iterations=2))
    if cv2.countNonZero(edge_band) > 0:
        bgr = cv2.cvtColor(filled_rgb.astype(np.uint8), cv2.COLOR_RGB2BGR)
        refined = cv2.inpaint(bgr, edge_band, max(3, radius - 2), cv2.INPAINT_TELEA)
        refined_rgb = cv2.cvtColor(refined, cv2.COLOR_BGR2RGB).astype(np.float32)
        edge_f = (edge_band > 0).astype(np.float32)[:, :, None]
        filled_rgb = filled_rgb * (1.0 - edge_f) + refined_rgb * edge_f

    blur_size = max(3, int(feather_sigma * 2) | 1)
    alpha = cv2.GaussianBlur(inpaint_mask.astype(np.float32), (blur_size, blur_size), feather_sigma)
    alpha = np.clip(alpha / 255.0, 0.0, 1.0)
    blended = arr * (1.0 - alpha[:, :, None]) + filled_rgb * alpha[:, :, None]
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))


def _propagate_fill_from_boundary(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """마스크 안을 좌우·상하 원본 픽셀로 먼저 채워 cv2.inpaint 번짐을 줄입니다."""
    h, w, channels = arr.shape
    result = arr.copy()
    mask_bool = mask > 0

    for y in range(h):
        row_mask = mask_bool[y]
        if not np.any(row_mask):
            continue
        known = ~row_mask
        if np.count_nonzero(known) < 2:
            continue
        xs = np.arange(w, dtype=np.float32)
        for ch in range(channels):
            result[y, row_mask, ch] = np.interp(xs[row_mask], xs[known], result[y, known, ch])

    for x in range(w):
        col_mask = mask_bool[:, x]
        if not np.any(col_mask):
            continue
        known = ~col_mask
        if np.count_nonzero(known) < 2:
            continue
        ys = np.arange(h, dtype=np.float32)
        for ch in range(channels):
            result[col_mask, x, ch] = np.interp(ys[col_mask], ys[known], result[known, x, ch])

    return result


def create_inpaint_mask_from_array(mask: np.ndarray) -> Image.Image:
    """OpenAI edit API용 마스크. 투명(alpha=0) 영역이 편집 대상입니다."""
    height, width = mask.shape[:2]
    alpha = np.where(mask > 0, 0, 255).astype(np.uint8)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, :3] = 255
    rgba[:, :, 3] = alpha
    return Image.fromarray(rgba, mode="RGBA")


def composite_with_mask(
    original: Image.Image,
    edited: Image.Image,
    mask: np.ndarray,
    *,
    feather_sigma: float = 3.0,
) -> Image.Image:
    """편집 결과를 마스크 영역에만 반영합니다."""
    original_rgb = original.convert("RGB")
    edited_rgb = edited.convert("RGB")
    if edited_rgb.size != original_rgb.size:
        edited_rgb = edited_rgb.resize(original_rgb.size, Image.Resampling.LANCZOS)

    arr = np.array(original_rgb, dtype=np.float32)
    edit_arr = np.array(edited_rgb, dtype=np.float32)
    if mask.shape[:2] != arr.shape[:2]:
        mask = cv2.resize(mask, (arr.shape[1], arr.shape[0]), interpolation=cv2.INTER_NEAREST)

    blur_size = max(3, int(feather_sigma * 2) | 1)
    alpha = cv2.GaussianBlur((mask > 0).astype(np.float32) * 255.0, (blur_size, blur_size), feather_sigma)
    alpha = np.clip(alpha / 255.0, 0.0, 1.0)
    blended = arr * (1.0 - alpha[:, :, None]) + edit_arr * alpha[:, :, None]
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))


def is_local_inpaint_poor(
    original: Image.Image,
    edited: Image.Image,
    mask: np.ndarray,
) -> bool:
    """로컬 보정이 수직 번짐·스미어로 품질이 나쁜지 검사합니다."""
    original_rgb = original.convert("RGB")
    edited_rgb = edited.convert("RGB")
    if edited_rgb.size != original_rgb.size:
        edited_rgb = edited_rgb.resize(original_rgb.size, Image.Resampling.LANCZOS)

    orig = np.array(original_rgb, dtype=np.float32)
    edit = np.array(edited_rgb, dtype=np.float32)
    if mask.shape[:2] != orig.shape[:2]:
        mask = cv2.resize(mask, (orig.shape[1], orig.shape[0]), interpolation=cv2.INTER_NEAREST)

    region = mask > 0
    if np.count_nonzero(region) < 40:
        return False

    edit_gray = cv2.cvtColor(edit.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    orig_gray = cv2.cvtColor(orig.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    gx = cv2.Sobel(edit_gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(edit_gray, cv2.CV_64F, 0, 1, ksize=3)
    vert = float(np.mean(np.abs(gy[region])))
    horiz = float(np.mean(np.abs(gx[region])))
    if vert > max(8.0, horiz * 1.6):
        return True

    edit_lap = cv2.Laplacian(edit_gray[region], cv2.CV_64F).var()
    orig_lap = cv2.Laplacian(orig_gray[region], cv2.CV_64F).var()
    return edit_lap < orig_lap * 0.35


def inpaint_with_mask_openai(
    *,
    client: OpenAI,
    image: Image.Image,
    mask: np.ndarray,
    prompt: str,
    model: str = DEFAULT_EDIT_MODEL,
) -> Image.Image:
    """스마트 선택 마스크 형태 그대로 OpenAI로 고품질 보정합니다."""
    source = image.convert("RGB")
    img_w, img_h = source.size
    if mask.shape[:2] != (img_h, img_w):
        mask = cv2.resize(mask, (img_w, img_h), interpolation=cv2.INTER_NEAREST)

    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return source

    edit_rect = normalize_rect(
        int(xs.min()),
        int(ys.min()),
        int(xs.max()) + 1,
        int(ys.max()) + 1,
        image_width=img_w,
        image_height=img_h,
    )
    crop_rect = expand_rect_with_padding(edit_rect, (img_w, img_h), padding_ratio=0.35, min_padding=40)
    left, top, right, bottom = crop_rect
    crop = source.crop(crop_rect)
    local_mask = mask[top:bottom, left:right]

    crop_arr = np.array(crop)
    crop_h, crop_w = crop_arr.shape[:2]
    if local_mask.shape[:2] != (crop_h, crop_w):
        local_mask = cv2.resize(local_mask, (crop_w, crop_h), interpolation=cv2.INTER_NEAREST)

    edit_image, scale = resize_for_edit(crop)
    if scale != 1.0:
        scaled_mask = cv2.resize(
            local_mask,
            (edit_image.width, edit_image.height),
            interpolation=cv2.INTER_NEAREST,
        )
    else:
        scaled_mask = local_mask

    mask_image = create_inpaint_mask_from_array(scaled_mask)
    image_bytes = image_to_png_bytes(edit_image)
    mask_bytes = image_to_png_bytes(mask_image)

    request_kwargs = {
        "model": model,
        "image": ("source.png", image_bytes, "image/png"),
        "mask": ("mask.png", mask_bytes, "image/png"),
        "prompt": prompt,
        "size": "auto",
        "quality": "high",
        "background": "opaque",
        "output_format": "png",
    }
    if model == "dall-e-2":
        del request_kwargs["quality"]
        del request_kwargs["background"]
        del request_kwargs["output_format"]
        request_kwargs["response_format"] = "b64_json"

    response = client.images.edit(**request_kwargs)
    decoded = decode_edit_response_image(response, background=edit_image)
    edited_crop = composite_with_mask(edit_image, decoded, scaled_mask, feather_sigma=2.5)
    if scale != 1.0:
        edited_crop = edited_crop.resize(crop.size, Image.Resampling.LANCZOS)

    result = source.copy()
    result.paste(edited_crop, (left, top))
    return composite_with_mask(source, result, mask, feather_sigma=3.0)


def _restore_black_artifacts(edited_patch: Image.Image) -> Image.Image:
    """API가 남긴 순수 검정 구역을 주변 픽셀로 보정합니다."""
    edited_bgr = cv2.cvtColor(np.array(edited_patch.convert("RGB")), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(edited_bgr, cv2.COLOR_BGR2GRAY)
    black_mask = (gray <= 8).astype(np.uint8) * 255
    if not np.any(black_mask):
        return edited_patch

    black_ratio = cv2.countNonZero(black_mask) / max(1, edited_bgr.shape[0] * edited_bgr.shape[1])
    if black_ratio > 0.35:
        return edited_patch

    filled = cv2.inpaint(edited_bgr, black_mask, 5, cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(filled, cv2.COLOR_BGR2RGB))


def resize_for_edit(image: Image.Image, *, max_edge: int = MAX_IMAGE_EDGE) -> tuple[Image.Image, float]:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_edge:
        return image.copy(), 1.0

    scale = max_edge / longest
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS), scale


def scale_rect(rect: tuple[int, int, int, int], scale: float) -> tuple[int, int, int, int]:
    if scale == 1.0:
        return rect
    return (
        int(rect[0] * scale),
        int(rect[1] * scale),
        int(rect[2] * scale),
        int(rect[3] * scale),
    )


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


def decode_edit_response_image(
    response,
    *,
    background: Image.Image | None = None,
) -> Image.Image:
    item = response.data[0]
    if getattr(item, "b64_json", None):
        raw = base64.b64decode(item.b64_json)
        edited = Image.open(io.BytesIO(raw))
    elif getattr(item, "url", None):
        import urllib.request

        with urllib.request.urlopen(item.url) as remote:
            edited = Image.open(io.BytesIO(remote.read()))
    else:
        raise ValueError("API 응답에서 이미지를 찾을 수 없습니다.")

    if background is None:
        return edited.convert("RGB")

    background_rgb = background.convert("RGB")
    if edited.mode != "RGBA":
        edited = edited.convert("RGBA")

    if edited.size != background_rgb.size:
        edited = edited.resize(background_rgb.size, Image.Resampling.LANCZOS)

    composite = background_rgb.copy()
    composite.paste(edited.convert("RGB"), (0, 0), edited.split()[3])
    return composite


def blend_inpaint_result(
    original: Image.Image,
    edited: Image.Image,
    edit_rect: tuple[int, int, int, int],
    *,
    feather: int | None = None,
) -> Image.Image:
    """선택 영역만 API 결과로 교체하고, 나머지·투명 픽셀은 원본을 유지합니다."""
    original_rgb = original.convert("RGB")
    edited_rgb = edited.convert("RGB")
    if edited_rgb.size != original_rgb.size:
        edited_rgb = edited_rgb.resize(original_rgb.size, Image.Resampling.LANCZOS)

    left, top, right, bottom = edit_rect
    if feather is None:
        feather = max(4, min(18, int(min(right - left, bottom - top) * 0.06)))

    region_mask = Image.new("L", original_rgb.size, 0)
    region_draw = ImageDraw.Draw(region_mask)
    region_draw.rectangle(edit_rect, fill=255)
    if feather > 0:
        region_mask = region_mask.filter(ImageFilter.GaussianBlur(feather))

    edited_patch = edited_rgb.crop((left, top, right, bottom))
    restored_patch = _restore_black_artifacts(edited_patch)

    merged = edited_rgb.copy()
    merged.paste(restored_patch, (left, top))
    return Image.composite(merged, original_rgb, region_mask)


def _inpaint_image_core(
    *,
    client: OpenAI,
    image: Image.Image,
    edit_rect: tuple[int, int, int, int],
    prompt: str,
    model: str,
    blend_feather: int | None = None,
    decode_with_alpha: bool = True,
) -> Image.Image:
    source = image.convert("RGB")
    edit_rect = normalize_rect(*edit_rect, image_width=source.width, image_height=source.height)
    edit_image, scale = resize_for_edit(source)
    scaled_rect = scale_rect(edit_rect, scale)
    scaled_rect = normalize_rect(
        *scaled_rect,
        image_width=edit_image.width,
        image_height=edit_image.height,
    )

    mask = create_inpaint_mask(edit_image.size, scaled_rect)
    image_bytes = image_to_png_bytes(edit_image)
    mask_bytes = image_to_png_bytes(mask)

    request_kwargs = {
        "model": model,
        "image": ("source.png", image_bytes, "image/png"),
        "mask": ("mask.png", mask_bytes, "image/png"),
        "prompt": prompt,
    }

    if model == "dall-e-2":
        side = max(edit_image.width, edit_image.height)
        if side <= 256:
            request_kwargs["size"] = "256x256"
        elif side <= 512:
            request_kwargs["size"] = "512x512"
        else:
            request_kwargs["size"] = "1024x1024"
        request_kwargs["response_format"] = "b64_json"
    else:
        request_kwargs["size"] = "auto"
        request_kwargs["quality"] = "high"
        request_kwargs["background"] = "opaque"
        request_kwargs["output_format"] = "png"

    response = client.images.edit(**request_kwargs)
    if decode_with_alpha:
        decoded = decode_edit_response_image(response, background=edit_image)
    else:
        decoded = decode_edit_response_image(response, background=None).convert("RGB")
        if decoded.size != edit_image.size:
            decoded = decoded.resize(edit_image.size, Image.Resampling.LANCZOS)
    result = blend_inpaint_result(
        edit_image,
        decoded,
        scaled_rect,
        feather=blend_feather,
    )

    if scale != 1.0:
        result = result.resize(source.size, Image.Resampling.LANCZOS)

    return result


def inpaint_display_area(
    *,
    client: OpenAI,
    image: Image.Image,
    rect: tuple[int, int, int, int],
    prompt: str = INPAINT_PROMPT,
    model: str = DEFAULT_EDIT_MODEL,
    prefer_crop: bool = False,
    allow_crop: bool = True,
    blend_feather: int | None = None,
    decode_with_alpha: bool = True,
    rect_only: bool = False,
) -> Image.Image:
    """마스킹된 영역을 OpenAI Image Edit API로 인페인팅합니다."""
    if model not in SUPPORTED_EDIT_MODELS:
        raise ValueError(f"지원하지 않는 모델입니다: {model}")

    source = image.convert("RGB")
    edit_rect = normalize_rect(*rect, image_width=source.width, image_height=source.height)

    if prefer_crop or (allow_crop and should_use_crop_inpaint(edit_rect, source.size)):
        crop_rect = expand_rect_with_padding(edit_rect, source.size)
        cl, ct, cr, cb = crop_rect
        crop = source.crop(crop_rect)
        local_rect = normalize_rect(
            edit_rect[0] - cl,
            edit_rect[1] - ct,
            edit_rect[2] - cl,
            edit_rect[3] - ct,
            image_width=crop.width,
            image_height=crop.height,
        )
        edited_crop = _inpaint_image_core(
            client=client,
            image=crop,
            edit_rect=local_rect,
            prompt=prompt,
            model=model,
            blend_feather=blend_feather,
            decode_with_alpha=decode_with_alpha,
        )
        result = composite_crop_onto_image(source, edited_crop, crop_rect)
    else:
        result = _inpaint_image_core(
            client=client,
            image=source,
            edit_rect=edit_rect,
            prompt=prompt,
            model=model,
            blend_feather=blend_feather,
            decode_with_alpha=decode_with_alpha,
        )

    if rect_only:
        return apply_rect_only(source, result, edit_rect)
    return result


def inpaint_window_promo_area(
    *,
    client: OpenAI,
    image: Image.Image,
    rect: tuple[int, int, int, int],
    prompt: str,
    model: str = DEFAULT_EDIT_MODEL,
) -> Image.Image:
    """유리창 홍보물 제거용 — 전체 이미지 편집, 알파·페더·크롭 없이 선택 영역만 반영."""
    return inpaint_display_area(
        client=client,
        image=image,
        rect=rect,
        prompt=prompt,
        model=model,
        prefer_crop=False,
        allow_crop=False,
        blend_feather=0,
        decode_with_alpha=False,
        rect_only=True,
    )


def inpaint_with_guide_composite(
    *,
    client: OpenAI,
    image: Image.Image,
    rect: tuple[int, int, int, int],
    brand: str,
    guide_image: Image.Image,
    prompt: str | None = None,
    model: str = DEFAULT_EDIT_MODEL,
    use_guide_overlay: bool = True,
    use_ai_inpaint: bool = True,
) -> tuple[Image.Image, Image.Image | None]:
    """
    설치 완료 가이드 사진 기준 트레이 합성 후, 선택 영역을 AI 인페인팅으로 완성합니다.

    Returns:
        (최종 결과, 가이드 트레이 합성 중간 결과 또는 None)
    """
    source = image.convert("RGB")
    edit_rect = normalize_rect(*rect, image_width=source.width, image_height=source.height)

    overlay_result: Image.Image | None = None
    working = source

    if use_guide_overlay:
        overlay_result = apply_guide_tray_overlay(source, edit_rect, guide_image)
        working = overlay_result

    if not use_ai_inpaint:
        return working, overlay_result

    full_prompt = build_brand_inpaint_prompt(
        brand,
        base_prompt=prompt or (
            INPAINT_PROMPT_AFTER_OVERLAY if use_guide_overlay else INPAINT_PROMPT
        ),
        after_overlay=use_guide_overlay,
    )
    final = inpaint_display_area(
        client=client,
        image=working,
        rect=edit_rect,
        prompt=full_prompt,
        model=model,
    )
    return final, overlay_result
