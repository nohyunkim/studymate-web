# StudyMate Cloudflare Deployment Guide

이 저장소는 Flask 로컬 앱과 Cloudflare Workers 배포 경로를 함께 유지합니다. 실제 Cloudflare 진입점은 `worker/cf_worker.py`입니다.

## 핵심 파일

- `worker/cf_worker.py`: Cloudflare Workers Python 진입점
- `templates/`: Flask와 Worker가 함께 사용하는 공용 템플릿
- `wrangler.toml`: Workers, D1, static assets 설정
- `pyproject.toml`: 로컬 앱/Worker 실행에 필요한 Python 의존성
- `cloudflare/schema.sql`: D1 초기 스키마
- `cloudflare/export_sqlite_to_d1.py`: SQLite 데이터를 D1용 SQL로 변환하는 스크립트

## 로컬 준비

1. Node.js 설치
2. `uv` 설치
3. Cloudflare 로그인
4. 필요한 환경 변수 설정

```powershell
$env:SECRET_KEY="replace-with-a-random-secret"
$env:STUDYMATE_CONTACT_EMAIL="contact@example.com"
```

개발 환경에서만 임시 기본 시크릿을 허용하려면 아래 값을 명시적으로 사용합니다.

```powershell
$env:STUDYMATE_ALLOW_INSECURE_DEV_SECRET="1"
```

## 로컬 실행

```powershell
uv sync
$env:UV_CACHE_DIR=".uv-cache"
uv run pywrangler dev
```

Flask 로컬 앱을 직접 실행할 때도 `SECRET_KEY`는 반드시 설정하는 것을 권장합니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
```

## D1 생성 및 연결

1. D1 생성

```powershell
npx wrangler d1 create studymate-db
```

2. 반환된 `database_id`를 `wrangler.toml`에 반영

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

운영 환경에서는 기본 시크릿 fallback을 허용하지 않습니다.

```powershell
npx wrangler secret put SECRET_KEY
```

필요하면 일반 환경 변수도 설정합니다.

```powershell
npx wrangler secret put STUDYMATE_CONTACT_EMAIL
```

## 배포

```powershell
$env:UV_CACHE_DIR=".uv-cache"
uv run pywrangler deploy
```

## 운영 체크

- `SECRET_KEY`가 실제로 설정되어 있는지 확인
- 공개 연락처가 `STUDYMATE_CONTACT_EMAIL`에 반영되었는지 확인
- `templates/` 변경이 Worker에도 동일하게 반영되는지 확인
- `python -m unittest discover -s tests -v` 기준 테스트가 통과하는지 확인
