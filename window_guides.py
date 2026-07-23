import os

from PIL import Image, ImageDraw

from image_utils import load_image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WINDOW_GUC_DIR = os.path.join(BASE_DIR, "매장사진", "Window", "GUC")
SHEET_DIR = os.path.join(WINDOW_GUC_DIR, "시트지")
FIXTURE_DIR = os.path.join(WINDOW_GUC_DIR, "집기")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

WINDOW_GUIDE_CATEGORIES = (
    ("시트지", SHEET_DIR),
    ("집기", FIXTURE_DIR),
)

DEFAULT_WINDOW_ASSETS = {
    "시트지": (
        ("brand_sheet.png", "브랜드 시트지", (220, 320), "#f8f6f2"),
        ("campaign_sheet.png", "캠페인 시트지", (200, 280), "#efe8dc"),
        ("hours_sheet.png", "영업시간 시트지", (180, 120), "#ffffff"),
    ),
    "집기": (
        ("display_table.png", "디스플레이 테이블", (260, 140), "#e8e4dc"),
        ("brand_stand.png", "브랜드 스탠드", (120, 220), "#ddd6c8"),
        ("pop_fixture.png", "POP 집기", (160, 180), "#f0ebe3"),
    ),
}


def _draw_placeholder_asset(label: str, size: tuple[int, int], fill: str) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        [(0, 0), (width - 1, height - 1)],
        radius=12,
        fill=fill,
        outline="#b8956a",
        width=3,
    )
    draw.line([(12, height // 2), (width - 12, height // 2)], fill="#c9c2b8", width=2)
    text = label.replace(" ", "\n")
    draw.multiline_text(
        (width // 2, height // 2),
        text,
        fill="#1c2434",
        anchor="mm",
        align="center",
        spacing=4,
    )
    return image


def ensure_default_window_assets() -> None:
    os.makedirs(SHEET_DIR, exist_ok=True)
    os.makedirs(FIXTURE_DIR, exist_ok=True)

    for category, directory in WINDOW_GUIDE_CATEGORIES:
        existing = [
            name
            for name in os.listdir(directory)
            if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
        ]
        if existing:
            continue

        for filename, label, size, fill in DEFAULT_WINDOW_ASSETS[category]:
            asset_path = os.path.join(directory, filename)
            if os.path.exists(asset_path):
                continue
            _draw_placeholder_asset(label, size, fill).save(asset_path, "PNG")


def list_guide_images(directory: str) -> list[str]:
    if not os.path.isdir(directory):
        return []
    return sorted(
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
    )


def load_window_guide_assets() -> list[dict]:
    ensure_default_window_assets()
    assets: list[dict] = []

    for category, directory in WINDOW_GUIDE_CATEGORIES:
        for image_path in list_guide_images(directory):
            image = load_image(image_path, mode="RGBA")
            stem = os.path.splitext(os.path.basename(image_path))[0]
            assets.append(
                {
                    "id": f"{category}_{stem}",
                    "label": stem.replace("_", " "),
                    "category": category,
                    "path": image_path,
                    "width": image.width,
                    "height": image.height,
                    "image": image,
                }
            )
    return assets
