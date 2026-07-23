from PIL import Image, ImageOps


def load_image(path_or_file, *, mode: str = "RGB") -> Image.Image:
    """EXIF 회전 정보를 반영해 이미지를 올바른 방향으로 불러옵니다."""
    image = Image.open(path_or_file)
    image = ImageOps.exif_transpose(image)
    return image.convert(mode)


def load_image_limited(
    path_or_file,
    *,
    max_dimension: int,
    mode: str = "RGB",
    resample: Image.Resampling = Image.Resampling.BILINEAR,
) -> Image.Image:
    """긴 변 기준으로 축소해 불러옵니다. JPEG draft로 디코드 비용을 줄입니다."""
    with Image.open(path_or_file) as image:
        width, height = image.size
        longest = max(width, height)
        if longest > max_dimension:
            scale = max_dimension / longest
            target = (max(1, int(width * scale)), max(1, int(height * scale)))
            try:
                image.draft(mode, target)
            except Exception:
                pass
        image = ImageOps.exif_transpose(image)
        if max(image.size) > max_dimension:
            image.thumbnail((max_dimension, max_dimension), resample)
        return image.convert(mode)


def limit_image_size(image: Image.Image, *, max_dimension: int = 2048) -> Image.Image:
    """업로드·전송 속도를 위해 긴 변 기준으로 이미지 크기를 제한합니다."""
    width, height = image.size
    longest = max(width, height)
    if longest <= max_dimension:
        return image
    scale = max_dimension / longest
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)
