"""Window — 유리창 홍보물 제거 · 시트지·집기 합성 (독립 실행)"""

from __future__ import annotations

import html
import os
import traceback

import streamlit as st

WINDOW_PORT = int(os.getenv("STREAMLIT_SERVER_PORT", "8502"))


def is_streamlit_cloud() -> bool:
    return bool(os.getenv("STREAMLIT_SHARING_MODE")) or os.path.exists("/mount/src")


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
.mobile-access-box {
    margin: 0 0 1rem 0;
    padding: 0.85rem 1rem;
    border: 1px solid #d8d2c8;
    border-radius: 10px;
    background: #f7f5f1;
    color: #1c2434;
}
.mobile-access-box strong {
    color: #1d4ed8;
}
.mobile-access-box code {
    font-size: 1.05rem;
    word-break: break-all;
}
.mobile-access-hint {
    margin-top: 0.4rem;
    font-size: 0.85rem;
    color: #64748b;
    line-height: 1.45;
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


def render_cloud_access_banner() -> None:
    st.markdown(
        """
<div class="mobile-access-box">
  <div>📱 어디서나 핸드폰으로 사용</div>
  <div class="mobile-access-hint">
    이 앱은 <strong>Streamlit Community Cloud</strong>에 배포되어 있습니다.<br/>
    PC가 꺼져 있어도 이 주소만 있으면 언제든 사용할 수 있습니다.<br/>
    브라우저 주소창의 URL을 즐겨찾기에 추가해 두세요.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_local_access_banner() -> None:
    try:
        from network_utils import get_mobile_access_urls, is_port_listening
    except Exception:
        return

    urls = get_mobile_access_urls(WINDOW_PORT)
    hotspot = [url for url in urls if "192.168.137." in url]
    primary = hotspot[0] if hotspot else (urls[0] if urls else f"http://localhost:{WINDOW_PORT}")
    listening = is_port_listening(WINDOW_PORT)
    status = "서버 실행 중" if listening else "서버 확인 필요"

    extra = ""
    if urls:
        extra_urls = "<br/>".join(f"<code>{html.escape(url)}</code>" for url in urls)
        extra = f'<div class="mobile-access-hint">감지된 주소:<br/>{extra_urls}</div>'

    st.markdown(
        f"""
<div class="mobile-access-box">
  <div>📱 로컬 핸드폰 접속 · {html.escape(status)}</div>
  <div style="margin-top:0.35rem;"><strong><code>{html.escape(primary)}</code></strong></div>
  <div class="mobile-access-hint">
    클라우드 배포본을 쓰려면 Streamlit Cloud URL을 사용하세요.<br/>
    로컬: <code>방화벽_허용.bat</code> / <code>핫스팟_연결안내.bat</code>
  </div>
  {extra}
</div>
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

    with st.expander("📱 핸드폰으로 사용하기", expanded=is_streamlit_cloud()):
        if is_streamlit_cloud():
            render_cloud_access_banner()
        else:
            render_local_access_banner()

    try:
        render_window_page()
    except Exception:
        st.error("페이지 실행 중 오류가 발생했습니다.")
        st.code(traceback.format_exc())


main()
