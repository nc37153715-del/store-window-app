"""모바일 웹에서 사진 촬영·앨범 선택이 잘 되도록 최적화한 업로드 UI."""

from __future__ import annotations

import streamlit as st

MOBILE_IMAGE_TYPES = ["jpg", "jpeg", "png", "webp"]
MOBILE_UPLOAD_CSS = """
<style>
@media (max-width: 768px) {
    [data-testid="stFileUploader"] {
        padding: 0.25rem 0;
    }
    [data-testid="stFileUploader"] section {
        padding: 1rem 0.75rem;
    }
    [data-testid="stFileUploader"] button {
        min-height: 3rem;
        font-size: 1rem;
        width: 100%;
    }
    [data-testid="stFileUploaderDropzone"] {
        min-height: 7rem;
    }
    .mobile-upload-hint {
        font-size: 0.95rem;
        line-height: 1.5;
        margin: 0.35rem 0 0.75rem 0;
        color: #475569;
    }
}
</style>
"""


def inject_mobile_upload_styles() -> None:
    if st.session_state.get("_mobile_upload_css_injected"):
        return
    st.markdown(MOBILE_UPLOAD_CSS, unsafe_allow_html=True)
    st.session_state["_mobile_upload_css_injected"] = True


def mobile_photo_uploader(
    label: str,
    *,
    key: str,
    help_text: str | None = None,
    show_mobile_hint: bool = True,
    accept_multiple: bool = False,
) -> object | None:
    """
    스마트폰 브라우저에서 카메라 촬영·갤러리 선택을 모두 제공하는 이미지 업로더.

    Streamlit file_uploader는 모바일에서 OS 기본 선택창(카메라/앨범)을 띄웁니다.
    """
    inject_mobile_upload_styles()

    if show_mobile_hint:
        multi_note = " 여러 장 선택 가능합니다." if accept_multiple else ""
        st.markdown(
            (
                '<p class="mobile-upload-hint">'
                "📱 <strong>스마트폰:</strong> 아래 버튼을 누르면 "
                "<strong>카메라로 새로 촬영</strong> 또는 "
                "<strong>앨범(갤러리)에서 불러오기</strong> 중 선택할 수 있습니다."
                f"{multi_note}"
                "</p>"
            ),
            unsafe_allow_html=True,
        )

    if accept_multiple:
        default_help = "JPG · PNG · WEBP · 여러 장 업로드 가능"
    else:
        default_help = "JPG · PNG · WEBP · 단일 사진"
    merged_help = help_text or default_help
    if show_mobile_hint and help_text:
        merged_help = f"{help_text} (모바일: 카메라/앨범 선택 가능)"

    return st.file_uploader(
        label,
        type=MOBILE_IMAGE_TYPES,
        accept_multiple_files=accept_multiple,
        help=merged_help,
        key=key,
    )
