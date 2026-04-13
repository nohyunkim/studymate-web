# StudyMate Cloudflare 배포 가이드

이 저장소는 기존 Flask 앱을 유지한 채, Cloudflare Workers용 Python 런타임 파일을 추가한 상태입니다.

## 구성

- `cf_worker.py`: Cloudflare Workers에서 동작하는 Python 진입점
- `wrangler.toml`: Workers + D1 + static assets 설정
- `pyproject.toml`: `pywrangler` 실행에 필요한 Python 의존성
- `cloudflare/schema.sql`: D1 초기 스키마
- `cloudflare/export_sqlite_to_d1.py`: 기존 SQLite 데이터를 D1 INSERT SQL로 변환하는 스크립트

## 사전 준비

1. Node.js 설치
2. `uv` 설치
3. Cloudflare 로그인
4. 기존 SQLite DB가 있으면 위치 확인

## 로컬 실행

```powershell
uv sync
uv run pywrangler dev
```

## D1 생성 및 연결

1. D1 생성

```powershell
npx wrangler d1 create studymate-db
```

2. 반환된 `database_id`를 `wrangler.toml`의 `database_id`에 반영

3. 스키마 적용

```powershell
npx wrangler d1 execute studymate-db --file cloudflare/schema.sql
```

## 기존 SQLite 데이터 이전

기존 DB가 `instance/database.db`에 있다면:

```powershell
python cloudflare/export_sqlite_to_d1.py instance/database.db > cloudflare/data.sql
npx wrangler d1 execute studymate-db --file cloudflare/data.sql
```

## 시크릿 설정

로그인 세션 서명을 위해 시크릿을 설정합니다.

```powershell
npx wrangler secret put SECRET_KEY
```

## 배포

```powershell
uv run pywrangler deploy
```

## 변경된 동작

- 화면, URL, 서버 렌더링 템플릿 구조는 유지합니다.
- 정적 파일은 `static` 디렉터리를 Workers Assets로 서빙합니다.
- DB는 SQLite 파일 대신 D1을 사용합니다.
- 로그인 세션은 서버 메모리 대신 서명된 쿠키에 저장합니다.
- 채팅은 SSE 대신 짧은 주기 폴링으로 유지합니다. 사용자 입장에서는 동일한 채팅 화면과 전송 흐름을 유지합니다.