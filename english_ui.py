"""브라우저 자동 번역 방지 + 영문 라벨 고정."""

from __future__ import annotations

import json

import streamlit.components.v1 as components


def no_translate(text: str) -> str:
    """zero-width space로 자동 번역(예: SLP→언어치료사)을 방지합니다."""
    return "\u200b".join(text)


def inject_english_widget_guard(labels: dict[str, str]) -> None:
    """Streamlit 위젯 key → 영문 라벨을 DOM에 고정합니다."""
    if not labels:
        return

    labels_json = json.dumps(labels, ensure_ascii=False)
    components.html(
        f"""
<script>
(function() {{
  const incoming = {labels_json};
  window.__englishLabelMap = Object.assign(window.__englishLabelMap || {{}}, incoming);
  const doc = window.parent.document;

  function fixLabels() {{
    Object.entries(window.__englishLabelMap).forEach(([key, label]) => {{
      const host =
        doc.querySelector(".st-key-" + key) ||
        doc.querySelector('[data-st-key="' + key + '"]');
      if (!host) return;
      host.setAttribute("translate", "no");
      host.classList.add("notranslate");

      host.querySelectorAll("button, p, span").forEach((el) => {{
        el.setAttribute("translate", "no");
        el.classList.add("notranslate");
      }});

      const button = host.querySelector("button");
      if (!button) return;
      const text = button.querySelector("p");
      if (text && text.textContent !== label) {{
        text.textContent = label;
      }}
    }});
  }}

  fixLabels();
  setTimeout(fixLabels, 200);
  setTimeout(fixLabels, 800);
}})();
</script>
        """,
        height=0,
        width=0,
    )


CUSTOMIZATION_ENGLISH_LABELS = {
    "custom_back_main": "← Visual Check Guide",
    "custom_go_window": "Window",
    "brand_btn_GUC": "GUC",
    "brand_btn_CTR": "CTR",
    "brand_btn_SLP": "SLP",
}

WINDOW_ENGLISH_LABELS = {
    "window_back_main": "← Visual Check Guide",
    "window_back_top": "← Visual Check Guide",
}

MAIN_NAV_ENGLISH_LABELS = {
    "nav_customization": "In-Store Customization",
    "nav_window": "Window",
}
