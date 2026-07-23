import cv2
import numpy as np
from PIL import Image


def pil_to_cv2(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def cv2_to_pil(image: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


def _lerp_point(
    start: tuple[float, float],
    end: tuple[float, float],
    ratio: float,
) -> tuple[float, float]:
    return (
        start[0] + (end[0] - start[0]) * ratio,
        start[1] + (end[1] - start[1]) * ratio,
    )


def split_quad_horizontally(
    quad: list[tuple[float, float]],
    count: int,
) -> list[list[tuple[float, float]]]:
    top_left, top_right, bottom_right, bottom_left = quad
    bands: list[list[tuple[float, float]]] = []

    for index in range(count):
        top_ratio = index / count
        bottom_ratio = (index + 1) / count
        bands.append(
            [
                _lerp_point(top_left, bottom_left, top_ratio),
                _lerp_point(top_right, bottom_right, top_ratio),
                _lerp_point(top_right, bottom_right, bottom_ratio),
                _lerp_point(top_left, bottom_left, bottom_ratio),
            ]
        )

    return bands


def tray_quad_from_band(
    band: list[tuple[float, float]],
    *,
    surface_ratio: float = 0.28,
) -> list[tuple[float, float]]:
    """선반 한 칸의 하단(선반면)에 해당하는 얇은 사각형을 만듭니다."""
    top_left, top_right, bottom_right, bottom_left = band
    top_ratio = 1.0 - surface_ratio
    return [
        _lerp_point(top_left, bottom_left, top_ratio),
        _lerp_point(top_right, bottom_right, top_ratio),
        bottom_right,
        bottom_left,
    ]


def _find_peak_rows(signal: np.ndarray, *, min_distance: int, threshold: float) -> list[int]:
    peaks: list[int] = []
    for index in range(1, len(signal) - 1):
        if signal[index] < threshold:
            continue
        if signal[index] <= signal[index - 1] or signal[index] <= signal[index + 1]:
            continue
        if peaks and index - peaks[-1] < min_distance:
            if signal[index] > signal[peaks[-1]]:
                peaks[-1] = index
            continue
        peaks.append(index)
    return peaks


def count_shelves_in_quad(base_bgr: np.ndarray, quad: list[tuple[float, float]]) -> int:
    """원본 진열장 사진에서 선택 영역의 가로 선반 라인 개수를 추정합니다."""
    quad_array = np.float32(quad)
    xs = quad_array[:, 0]
    ys = quad_array[:, 1]
    width = max(int(np.linalg.norm(quad_array[1] - quad_array[0])), 120)
    height = max(int(np.linalg.norm(quad_array[3] - quad_array[0])), 120)

    rect = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    matrix = cv2.getPerspectiveTransform(quad_array, rect)
    warped = cv2.warpPerspective(base_bgr, matrix, (width, height))

    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    horizontal_edges = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    row_energy = np.abs(horizontal_edges).mean(axis=1)

    min_distance = max(12, height // 10)
    threshold = max(float(row_energy.max()) * 0.18, 8.0)
    peaks = _find_peak_rows(row_energy, min_distance=min_distance, threshold=threshold)

    if len(peaks) >= 2:
        return max(2, min(8, len(peaks)))

    return 4


def count_trays_in_brand_image(brand_image: Image.Image) -> int | None:
    """브랜드 설치 사진에서 흰색 트레이 줄 개수를 추정합니다."""
    rgb = np.array(brand_image.convert("RGB"))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    white_mask = ((hsv[:, :, 1] < 60) & (hsv[:, :, 2] > 155)).astype(np.uint8) * 255

    row_density = white_mask.sum(axis=1).astype(np.float32)
    threshold = white_mask.shape[1] * 0.12
    bands: list[tuple[int, int]] = []
    start: int | None = None
    gap = 0

    for row, density in enumerate(row_density):
        if density >= threshold:
            if start is None:
                start = row
            gap = 0
            continue

        if start is not None:
            gap += 1
            if gap > 4:
                end = row - gap
                if end - start >= max(12, rgb.shape[0] // 40):
                    band_height = end - start
                    if 0.035 * rgb.shape[0] <= band_height <= 0.22 * rgb.shape[0]:
                        if start >= rgb.shape[0] * 0.12:
                            bands.append((start, end))
                start = None
                gap = 0

    if len(bands) >= 2:
        return min(8, len(bands))
    return None


def create_synthetic_white_tray(
    *,
    width: int = 640,
    height: int = 48,
    color: tuple[int, int, int] = (248, 248, 246),
) -> np.ndarray:
    """검정 테두리 없이 흰색 트레이 텍스처만 생성합니다."""
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, 0] = color[0]
    rgba[:, :, 1] = color[1]
    rgba[:, :, 2] = color[2]
    rgba[:, :, 3] = 255

    fade_rows = min(6, max(2, height // 8))
    for row in range(fade_rows):
        alpha = int(255 * (row + 1) / fade_rows)
        rgba[row, :, 3] = alpha

    return rgba


def _soften_rgba_edges(overlay_rgba: np.ndarray, feather_px: int) -> np.ndarray:
    """오버레이 PNG 가장자리 알파를 부드럽게 페이드합니다."""
    if feather_px <= 0:
        return overlay_rgba

    result = overlay_rgba.copy()
    height, width = result.shape[:2]
    if height < 2 or width < 2:
        return result

    alpha = result[:, :, 3].astype(np.float32) / 255.0
    yy, xx = np.mgrid[0:height, 0:width]
    dist_edge = np.minimum.reduce(
        [
            xx.astype(np.float32),
            yy.astype(np.float32),
            (width - 1 - xx).astype(np.float32),
            (height - 1 - yy).astype(np.float32),
        ]
    )
    edge_factor = np.clip(dist_edge / float(feather_px), 0.0, 1.0)
    alpha *= edge_factor
    result[:, :, 3] = np.clip(alpha * 255.0, 0, 255).astype(np.uint8)
    return result


def _warp_rgba_overlay(
    base: np.ndarray,
    overlay_rgba: np.ndarray,
    dst_points: list[tuple[float, float]],
    *,
    source_edge_feather: int = 0,
    alpha_blur_sigma: float | None = None,
) -> np.ndarray:
    if source_edge_feather > 0:
        overlay_rgba = _soften_rgba_edges(overlay_rgba, source_edge_feather)

    overlay_bgr = cv2.cvtColor(overlay_rgba[:, :, :3], cv2.COLOR_RGB2BGR)
    overlay_alpha = overlay_rgba[:, :, 3].astype(np.float32) / 255.0

    overlay_height, overlay_width = overlay_bgr.shape[:2]
    base_height, base_width = base.shape[:2]

    src_points = np.float32(
        [
            [0, 0],
            [overlay_width - 1, 0],
            [overlay_width - 1, overlay_height - 1],
            [0, overlay_height - 1],
        ]
    )
    dst_points_array = np.float32(dst_points)
    matrix = cv2.getPerspectiveTransform(src_points, dst_points_array)

    warped_overlay = cv2.warpPerspective(
        overlay_bgr,
        matrix,
        (base_width, base_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    warped_alpha = cv2.warpPerspective(
        overlay_alpha,
        matrix,
        (base_width, base_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    if alpha_blur_sigma is None:
        warped_alpha = cv2.GaussianBlur(warped_alpha, (3, 3), 0)
    elif alpha_blur_sigma > 0:
        blur_size = max(3, int(alpha_blur_sigma * 2) | 1)
        warped_alpha = cv2.GaussianBlur(warped_alpha, (blur_size, blur_size), alpha_blur_sigma)

    warped_alpha = np.clip(warped_alpha, 0.0, 1.0)
    alpha_3ch = np.stack([warped_alpha] * 3, axis=-1)

    base_float = base.astype(np.float32)
    overlay_float = warped_overlay.astype(np.float32)
    blended = base_float * (1.0 - alpha_3ch) + overlay_float * alpha_3ch
    return np.clip(blended, 0, 255).astype(np.uint8)


def perspective_tray_overlay(
    base_image: Image.Image,
    brand_image: Image.Image,
    dst_points: list[tuple[float, float]],
) -> Image.Image:
    """원본 진열장은 유지하고, 각 선반면 위에 흰색 트레이만 합성합니다."""
    if len(dst_points) != 4:
        raise ValueError("합성하려면 4개의 꼭짓점이 필요합니다.")

    base = pil_to_cv2(base_image)
    shelf_count = count_shelves_in_quad(base, dst_points)
    brand_tray_count = count_trays_in_brand_image(brand_image)
    if brand_tray_count is not None:
        shelf_count = brand_tray_count

    shelf_bands = split_quad_horizontally(dst_points, shelf_count)
    white_tray = create_synthetic_white_tray(width=900, height=56)

    for shelf_band in shelf_bands:
        tray_quad = tray_quad_from_band(shelf_band, surface_ratio=0.30)
        base = _warp_rgba_overlay(base, white_tray, tray_quad)

    return cv2_to_pil(base)


def perspective_overlay(
    base_image: Image.Image,
    overlay_image: Image.Image,
    dst_points: list[tuple[float, float]],
) -> Image.Image:
    return perspective_tray_overlay(base_image, overlay_image, dst_points)
