import os

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

from inpainting import DEFAULT_EDIT_MODEL, inpaint_window_promo_area, normalize_rect

load_dotenv()

WINDOW_REMOVE_PROMPT = (
    "매장 유리창·외부 사진에서 선택된 영역 안의 시트지, 스티커, 홍보물, 포스터, "
    "전단, POP, 캠페인 안내 등을 자연스럽게 제거해 주세요. "
    "선택 영역 안은 주변 유리, 프레임, 벽, 실내 비치는 배경과 조명·색감·질감이 "
    "끊김 없이 이어지도록 깨끗한 유리창·외벽처럼 복원하세요. "
    "선택 영역 밖은 원본과 동일하게 유지하세요."
)

WINDOW_REMOVE_PROMPT_WITH_INTERIOR = (
    "매장 유리창·외부 사진에서 선택된 영역의 시트지·홍보물을 제거하고, "
    "영역 안에는 유리창 너머 보이는 매장 내부가 자연스럽게 드러나도록 완성해 주세요. "
    "작업자가 제공한 안쪽 참고 사진의 내용·원근·조명을 참고하되, "
    "주변 유리·프레임·반사와 자연스럽게 이어지게 블렌딩하세요. "
    "선택 영역 밖은 원본과 동일하게 유지하세요."
)


def build_window_remove_prompt(
    *,
    interior_reference: Image.Image | None = None,
    removal_notes: str | None = None,
) -> str:
    prompt = (
        WINDOW_REMOVE_PROMPT_WITH_INTERIOR
        if interior_reference is not None
        else WINDOW_REMOVE_PROMPT
    )
    notes = (removal_notes or "").strip()
    if not notes:
        return prompt

    if len(notes) > 500:
        notes = notes[:500].rstrip() + "..."

    return (
        f"{prompt} "
        "아래는 작업자가 제공한 가려진 영역·참고 사진 설명입니다. "
        f"가능한 한 반영하세요: {notes}"
    )


def get_openai_api_key() -> str | None:
    """로컬 .env 또는 Streamlit Cloud secrets에서 API 키를 읽습니다."""
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if key:
        return key
    try:
        import streamlit as st

        secret = st.secrets.get("OPENAI_API_KEY", "")
        if secret:
            return str(secret).strip()
    except Exception:
        pass
    return None


def get_openai_client() -> OpenAI:
    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY가 없습니다. "
            "로컬은 .env, Streamlit Cloud는 App settings → Secrets에 "
            'OPENAI_API_KEY = "sk-..." 를 넣어 주세요.'
        )
    return OpenAI(api_key=api_key)


def remove_window_promo(
    *,
    client: OpenAI,
    image: Image.Image,
    rect: tuple[float, float, float, float],
    interior_reference: Image.Image | None = None,
    removal_notes: str | None = None,
    model: str = DEFAULT_EDIT_MODEL,
) -> Image.Image:
    """선택 영역의 유리창 시트지·홍보물을 OpenAI로 제거합니다."""
    normalized = normalize_rect(
        rect[0],
        rect[1],
        rect[0] + rect[2],
        rect[1] + rect[3],
        image_width=image.width,
        image_height=image.height,
    )
    prompt = build_window_remove_prompt(
        interior_reference=interior_reference,
        removal_notes=removal_notes,
    )
    return inpaint_window_promo_area(
        client=client,
        image=image.convert("RGB"),
        rect=normalized,
        prompt=prompt,
        model=model,
    )
