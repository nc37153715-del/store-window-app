# Window

유리창 홍보물 제거 + 시트지·집기 합성 앱 (Streamlit)

**GitHub:** https://github.com/nc37153715-del/store-window-app

## Streamlit Community Cloud 배포

1. https://share.streamlit.io 접속 (GitHub로 로그인)
2. **New app** 또는 배포 링크:
   https://share.streamlit.io/deploy?repository=nc37153715-del/store-window-app&branch=main&mainModule=app.py
3. 설정
   - Repository: `nc37153715-del/store-window-app`
   - Branch: `main`
   - Main file path: `app.py`
4. **Advanced settings → Secrets**에 추가:

```toml
OPENAI_API_KEY = "sk-여기에_키"
```

   (로컬 `.env`에 있는 키를 그대로 넣으면 됩니다. GitHub에는 올라가지 않습니다.)

5. **Deploy** 클릭 → 완료 후 `https://xxxx.streamlit.app` 주소 생성
6. 그 주소를 핸드폰 북마크 → PC OFF여도 사용 가능

## 로컬 실행

```bat
사무실_최초설치.bat
실행.bat
```

브라우저: http://localhost:8502
