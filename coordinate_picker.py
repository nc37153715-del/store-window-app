from PIL import Image, ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

CORNER_LABELS = ("① 좌상", "② 우상", "③ 우하", "④ 좌하")


def prepare_display_image(
    image: Image.Image,
    *,
    max_width: int,
) -> tuple[Image.Image, float]:
    if image.width <= max_width:
        return image.copy(), 1.0
    scale = max_width / image.width
    new_height = max(1, int(image.height * scale))
    return image.resize((max_width, new_height), Image.Resampling.LANCZOS), scale


def original_points_to_display(
    points: list[tuple[float, float]],
    scale: float,
) -> list[tuple[float, float]]:
    return [(x * scale, y * scale) for x, y in points]


def display_point_to_original(x: float, y: float, scale: float) -> tuple[float, float]:
    if scale == 1.0:
        return x, y
    return x / scale, y / scale


def draw_corner_points(image: Image.Image, points: list[tuple[float, float]]) -> Image.Image:
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    for index, (x, y) in enumerate(points):
        radius = max(6, min(image.size) // 120)
        draw.ellipse(
            [(x - radius, y - radius), (x + radius, y + radius)],
            fill="#b8956a",
            outline="#ffffff",
            width=2,
        )
        draw.text((x + radius + 4, y - radius - 2), CORNER_LABELS[index], fill="#1c2434")
    if len(points) == 4:
        draw.polygon(points, outline="#b8956a", width=3)
    return annotated


def pick_image_coordinates(
    image: Image.Image,
    *,
    component_id: str,
    max_display_width: int,
) -> dict | None:
    display_image, _display_scale = prepare_display_image(image, max_width=max_display_width)
    value = streamlit_image_coordinates(
        display_image,
        key=f"coord_picker_{component_id}",
        width=display_image.width,
        cursor="crosshair",
    )
    if not isinstance(value, dict):
        return None
    if "x" not in value or "y" not in value:
        return None
    return {"x": float(value["x"]), "y": float(value["y"])}
