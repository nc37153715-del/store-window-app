"""Window — 유리창 홍보물 제거 · 시트지·집기 합성 (독립 실행)"""

from __future__ import annotations

import traceback

import streamlit as st


def inject_window_theme() -> None:
    st.markdown(
        """
<style>
html, body, .stApp {
    background: #fcfbfa;
}
.stApp [data-testid="stHeader"] {
    background: transparent;
}
.block-container {
    padding-top: 1.0rem;
    padding-bottom: 2.5rem;
    max-width: 1100px;
}
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.75rem;
        padding-right: 0.75rem;
    }
    .window-page-title {
        font-size: 1.7rem !important;
    }
    button[kind="primary"],
    [data-testid="stButton"] button {
        min-height: 2.75rem;
    }
}
</style>
""",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Window",
        page_icon="🪟",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_window_theme()

    try:
        from window_page import render_window_page
    except Exception:
        st.error("앱을 불러오는 중 오류가 발생했습니다.")
        st.code(traceback.format_exc())
        return

    try:
        render_window_page()
    except Exception:
        st.error("페이지 실행 중 오류가 발생했습니다.")
        st.code(traceback.format_exc())


main()
