# APS Server

APS Vault를 서버에서 안전하게 동기화하고 정기·요청 기반 브리핑, 점검과 읽기 전용 에이전트 작업을 실행하는 컨테이너 서비스다.

APS Vault는 프로젝트 운영 문서의 원본이고 이 저장소는 API, queue, worker와 컨테이너 배포를 소유한다. 프로젝트 코드 저장소는 서버 입력이 아니다.

상세 목표, 범위와 마일스톤은 [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md)를 따른다.

## 구조

```text
Client / cron / CLI
  → FastAPI Job API
  → in-process worker queue
  → Vault fetch + fast-forward only
  → briefing / audit / scoped agent query
  → persisted Job JSON + Artifact
```

```text
aps-server/
├── src/aps_server/       # API, Job store, worker와 Vault adapter
├── tests/                # API·경로·저장 테스트
├── Dockerfile
├── compose.yaml
└── .env.example
```

## 현재 operation

| Operation | 역할 | 내용 |
|---|---|---|
| `briefing.daily` | scheduler/operator/viewer | 전체 일일 브리핑 |
| `briefing.project` | operator/viewer | 프로젝트 하나의 브리핑 |
| `vault.audit` | scheduler/operator | 진행 프로젝트 컨텍스트 검사 |
| `service.maintenance_due` | scheduler/operator/viewer | 서비스 점검 기한 조회 |
| `agent.query` | operator | 선택한 Vault 문서만 읽는 질문 |

모든 작업은 비동기다. `POST /v1/jobs`의 `job_id`를 `GET /v1/jobs/{job_id}`로 조회한다.

## 서버 준비

1. 서버에 APS Vault를 `/srv/aps/repo` 같은 전용 경로로 clone한다.
2. 서비스 계정이 해당 clone을 읽고 fast-forward할 권한을 갖게 한다.
3. Codex CLI 인증 디렉터리를 `/srv/aps/codex-home`에 준비한다.
4. `.env.example`을 `.env`로 복사하고 서로 다른 긴 token 세 개와 실제 경로를 설정한다.

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose ps
```

기본 port bind는 `127.0.0.1:8080`이다. 외부 접근은 reverse proxy의 TLS·인증을 거쳐야 한다. Codex 인증정보는 image에 포함하지 않고 host bind mount로 주입한다.

Vault worktree가 dirty하거나 upstream으로 fast-forward할 수 없으면 Job을 실패시키며 merge, reset 또는 강제 checkout하지 않는다.

## 요청 예시

```bash
curl -X POST http://127.0.0.1:8080/v1/jobs \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: daily-2026-08-25" \
  -d '{"operation":"briefing.daily","input":{"format":"html"},"context":{}}'
```

```bash
export APS_API_URL=http://127.0.0.1:8080
export APS_API_TOKEN="$APS_OPERATOR_TOKEN"
aps vault-audit --wait
aps agent-ask --project tauri-markdown-editor --wait "오늘 사용자 결정이 필요한 항목만 알려줘"
```

## 로컬 개발

```powershell
py -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/pytest
```

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

## 보안 경계

- API token은 저장소에 commit하지 않는다.
- `agent.query`는 선택된 Vault 경로를 격리된 작업 폴더로 복사한 뒤 Codex를 read-only sandbox로 실행한다.
- 절대경로, `..`, Windows drive 경로와 Vault 밖으로 향하는 symlink는 거부한다.
- API는 shell 명령과 Codex CLI 인자를 입력으로 받지 않는다.
- Artifact 다운로드는 해당 Job의 Artifact 디렉터리 안으로 제한한다.
- Vault 원본을 수정하는 operation은 아직 제공하지 않는다.

## 현재 1차 한계

- queue는 단일 API 프로세스 내부에 있으므로 Uvicorn worker를 1개만 사용한다.
- Job 상태는 JSON 파일로 보존되지만 프로세스 재시작 시 실행 중 Job은 자동 재개되지 않는다.
- 브리핑의 HTML과 JSON은 각각 별도 Job으로 생성한다.
- `vault.propose_change`, multi-host worker와 외부 queue는 후속 마일스톤이다.
