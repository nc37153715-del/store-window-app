# Window

유리창 홍보물 제거 + 시트지·집기 합성 앱 (Streamlit)

## 로컬 실행

```bat
사무실_최초설치.bat
실행.bat
```

브라우저: http://localhost:8502

## Streamlit Community Cloud 배포

1. 이 저장소를 GitHub에 push
2. https://share.streamlit.io 접속 후 GitHub 로그인
3. **New app** → 이 저장소 선택
   - Main file path: `app.py`
   - Python version: 3.12 권장
4. **Advanced settings → Secrets** 에 아래 추가:

```toml
OPENAI_API_KEY = "sk-여기에_키"
```

5. Deploy

배포 후 나오는 `https://xxxx.streamlit.app` 주소를 핸드폰에서도 그대로 사용하면 됩니다.
(PC가 꺼져 있어도 사용 가능)

## Secrets 예시

`.streamlit/secrets.toml` (로컬, git 제외):

```toml
OPENAI_API_KEY = "sk-..."
```
