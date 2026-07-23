import os

from PIL import Image

from image_utils import load_image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISPLAY_DIR = os.path.join(BASE_DIR, "매장사진", "진열장")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
BRANDS = ("GUC", "CTR", "SLP")

BRAND_GUIDE_HINTS = {
    "GUC": (
        "GUCCI 설치 완료 가이드 사진과 동일하게, 선반마다 흰색 디스플레이 트레이를 배치하고 "
        "럭셔리 안경·선글라스를 정돈해 전시합니다."
    ),
    "CTR": (
        "Cartier 설치 완료 가이드 사진과 동일하게, 선반마다 흰색 디스플레이 트레이를 배치하고 "
        "고급스러운 안경·선글라스를 정돈해 전시합니다."
    ),
    "SLP": (
        "Saint Laurent 설치 완료 가이드 사진과 동일하게, 선반마다 흰색 디스플레이 트레이를 배치하고 "
        "모던하고 세련된 안경·선글라스를 정돈해 전시합니다."
    ),
}


def find_first_image_in_dir(directory: str) -> str | None:
    if not os.path.isdir(directory):
        return None

    images = [
        os.path.join(directory, name)
        for name in sorted(os.listdir(directory))
        if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
    ]
    return images[0] if images else None


def find_brand_image_path(brand: str) -> str | None:
    brand_upper = brand.upper()

    folder_candidates = (
        os.path.join(DISPLAY_DIR, brand_upper),
        os.path.join(DISPLAY_DIR, brand),
    )
    for folder_path in folder_candidates:
        image_path = find_first_image_in_dir(folder_path)
        if image_path:
            return image_path

    if not os.path.isdir(DISPLAY_DIR):
        return None

    for name in sorted(os.listdir(DISPLAY_DIR)):
        path = os.path.join(DISPLAY_DIR, name)
        ext = os.path.splitext(name)[1].lower()

        if os.path.isfile(path) and ext in IMAGE_EXTENSIONS and brand_upper in name.upper():
            return path

        if os.path.isdir(path) and brand_upper in name.upper():
            image_path = find_first_image_in_dir(path)
            if image_path:
                return image_path

    return None


def load_brand_images() -> dict[str, tuple[Image.Image, str]]:
    brand_images: dict[str, tuple[Image.Image, str]] = {}
    for brand in BRANDS:
        image_path = find_brand_image_path(brand)
        if image_path:
            brand_images[brand] = (load_image(image_path, mode="RGBA"), image_path)
    return brand_images


def get_brand_guide_hint(brand: str) -> str:
    return BRAND_GUIDE_HINTS.get(brand.upper(), "브랜드 설치 완료 가이드 사진과 동일한 진열 스타일")
