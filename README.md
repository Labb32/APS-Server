# APS Server

APS Server는 개인의 APS Vault를 API와 자동화 작업으로 연결하는 self-hosted 백엔드다. Vault의 Markdown 문서를 원본으로 유지하면서 브리핑, 프로젝트, 서비스 유지보수 정보와 Idea를 JSON 또는 HTML로 제공한다.

하나의 APS Server 컨테이너는 한 명의 사용자와 하나의 Vault를 담당한다. 여러 사용자가 필요하면 사용자별 컨테이너를 분리하고 reverse proxy에서 요청을 전달한다.

> **Release status:** `0.1.0` pre-release. MVP 구현은 완료됐으며 현재 개인 서버 운영 QA 단계다. 실사용 Vault를 연결하기 전에 disposable Vault로 검증하는 것을 권장한다.

## 주요 기능

- APS Vault의 Markdown 문서를 기준 데이터로 사용
- Bearer token 기반 `operator`, `viewer`, `scheduler` 권한 분리
- Vault clean 검사와 fast-forward-only Git 동기화
- 사전에 정의된 Job과 내장 cron Scheduler
- 검증된 canonical JSON 저장 및 JSON/HTML 조회
- 일일 브리핑, 프로젝트, 서비스 유지보수와 Idea API
- 고정 `00_Inbox`를 통한 안전한 Idea 접수
- 공식 확장 패키지 설치와 Schedule 자동 등록
- OpenAI Responses API, OpenAI-compatible API 또는 범용 Agent HTTP 서비스 연결
- 고정 task와 Tool만 실행하는 provider-neutral AgentExecutor
- pending Idea의 AI 정규화·중복·Set 후보 검증 및 단일 batch commit
- 선택형 `aps-index` 연동을 고려한 Idea 검색 구조

조회 요청마다 AI를 실행하지 않는다. Scheduler나 Job이 Vault를 읽어 결과를 미리 생성하고, Content API는 마지막으로 검증된 결과만 반환한다.

```text
APS Vault (Markdown)
        │
        ▼
APS Server ── Job / Scheduler ── AI provider
        │
        ├─ canonical JSON API
        └─ JSON 기반 HTML viewer
```

## 빠른 시작

### 1. 준비

- Docker Engine과 Docker Compose
- 길고 서로 다른 operator/viewer/scheduler token
- 사용할 AI provider 하나

저장소를 받은 뒤 예제 설정을 복사한다.

```bash
cp .env.example .env
```

`.env`에서 최소한 다음 값을 변경한다.

```dotenv
APS_OPERATOR_TOKEN=replace-with-a-long-random-token
APS_VIEWER_TOKEN=replace-with-a-different-long-random-token
APS_SCHEDULER_TOKEN=replace-with-a-third-long-random-token

APS_VAULT_MODE=local

APS_AI_PROVIDER=openai
APS_AI_API_KEY=replace-with-openai-api-key
APS_AI_MODEL=replace-with-an-available-responses-model
```

`APS_AI_PROVIDER`는 필수이며 다음 중 하나다.

| Provider | 용도 | 추가 설정 |
|---|---|---|
| `openai` | OpenAI Responses API와 Codex 계열 API 모델 | `APS_AI_API_KEY`, `APS_AI_MODEL` |
| `agent-http` | APS 계약을 지원하는 범용 Agent 서비스 | `APS_AI_BASE_URL` |
| `openai-compatible` | vLLM 등 Chat Completions 호환 API | `APS_AI_BASE_URL`, `APS_AI_MODEL` |

### 2. Vault 선택

| Mode | 사용 시점 | 주요 설정 |
|---|---|---|
| `local` | 내장 템플릿으로 새 Vault 생성 | `APS_VAULT_MODE=local` |
| `git` | 원격 Git Vault를 처음 clone | `APS_VAULT_GIT_URL`, 선택형 branch |
| `mounted` | host에 이미 존재하는 Vault 연결 | `APS_VAULT_MOUNT`, 필요 시 `APS_SYNC_BEFORE_JOB=false` |

처음 실행할 때는 기본값인 `local` mode가 가장 간단하다. 원격 또는 기존 Vault 연결 방법은 [컨테이너 배포 가이드](docs/CONTAINER_DEPLOYMENT.md)를 참고한다.

### 3. 실행

모든 provider는 Node.js와 Codex CLI가 없는 동일한 Python image를 사용한다. `openai` provider에서 Codex 계열 API 모델을 선택해도 별도 runtime image가 필요하지 않다.

```bash
docker compose build
docker compose up -d
docker compose ps
```

### 4. 상태 확인

기본 주소는 `127.0.0.1:8080`이다.

```bash
curl http://127.0.0.1:8080/health/live

curl http://127.0.0.1:8080/health/ready \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
```

`live`는 프로세스 생존 여부를, `ready`는 Vault·인증·확장·AI provider 설정 준비 상태를 확인한다. readiness는 외부 AI에 실제 생성 요청을 보내지 않는다.

## 기본 사용법

### 인증

보호된 요청에는 역할에 맞는 Bearer token을 전달한다.

```http
Authorization: Bearer <token>
```

| 역할 | 기본 용도 |
|---|---|
| `viewer` | Content와 Idea 조회, 허용된 생성 Job 요청 |
| `operator` | 운영 상태, Job 제어, Idea 작성과 수정 |
| `scheduler` | 등록된 주기 작업 실행 |

### Idea 조회와 접수

Idea 목록을 조회한다.

```bash
curl http://127.0.0.1:8080/v1/ideas \
  -H "Authorization: Bearer $APS_VIEWER_TOKEN"
```

새 Idea는 요청자가 경로를 지정하지 않고 서버가 관리하는 Git-ignored `00_Inbox`에만 접수된다.

```bash
curl -X POST http://127.0.0.1:8080/v1/ideas \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Vault 변경 알림",
    "keywords": ["vault", "notification"],
    "summary": "Vault 변경을 여러 기기에 알려 주는 Idea"
  }'
```

Inbox의 Idea는 Scheduler가 검증하고 정리한 뒤 `01_Ideas` 또는 `01_Idea_Sets`로 이동해 commit한다.

### Job 실행

현재 token으로 실행할 수 있는 operation을 먼저 확인한다.

```bash
curl http://127.0.0.1:8080/v1/operations \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
```

Job 요청은 등록된 operation과 고정 입력 schema만 받는다.

```bash
curl -X POST http://127.0.0.1:8080/v1/jobs \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: idea-index-2026-09-02" \
  -d '{"operation":"ideas.index.refresh","input":{},"context":{}}'
```

응답의 `job_id`로 상태를 조회한다.

```bash
curl http://127.0.0.1:8080/v1/jobs/<job_id> \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
```

### JSON과 HTML Content

Content API의 기준 응답은 JSON이다. `format=html`은 같은 JSON을 고정 템플릿으로 보여 주는 viewer이며 별도의 AI 요청을 만들지 않는다.

```bash
curl "http://127.0.0.1:8080/v1/content/ideas?format=json" \
  -H "Authorization: Bearer $APS_VIEWER_TOKEN"

curl "http://127.0.0.1:8080/v1/content/ideas?format=html" \
  -H "Authorization: Bearer $APS_VIEWER_TOKEN"
```

아직 결과를 생성하지 않은 Content는 `404 CONTENT_NOT_GENERATED`를 반환할 수 있다. 관련 Job이나 Schedule이 성공하면 검증된 최신 결과가 게시된다.

## 공식 확장

기본 서버는 활성 확장 없이 시작한다. 현재 공식 `briefing` 확장은 브리핑과 서비스 유지보수 operation 및 Schedule을 추가한다.

초기 설치는 `.env`에서 지정할 수 있다.

```dotenv
APS_INITIAL_EXTENSIONS=briefing
```

실행 중 설치한 경우 재시작해야 활성화된다.

```bash
docker compose exec aps-server aps extensions list
docker compose exec aps-server aps extensions install briefing
docker compose restart aps-server
```

확장은 임의 shell 명령이나 Vault 경로를 추가할 수 없으며, 등록된 입력과 JSON Schema 안에서만 동작한다.

## 문서

- [구조 및 개발 현황](docs/DEVELOPMENT_STATUS.md) — 구성 요소, 코드 구조, 구현 범위와 후속 작업
- [아키텍처](docs/ARCHITECTURE.md) — Core, Vault, 확장과 쓰기 경계
- [컨테이너 배포](docs/CONTAINER_DEPLOYMENT.md) — Vault mode, 설정 mount, Nginx와 영속 volume
- [AI provider](docs/AI_PROVIDERS.md) — OpenAI Responses API, Agent HTTP 계약과 OpenAI-compatible API
- [AgentExecutor 설계](docs/AGENT_EXECUTOR_DESIGN.md) — Operation, Queue, Tool과 확장 경계
- [API Reference](docs/API_REFERENCE.md) — 요청·응답 schema, 역할과 오류 코드
- [OpenAPI](specs/aps-api.openapi.json) — machine-readable 전체 API 계약
- [Pre-release QA](docs/PRE_RELEASE_QA.md) — 개인 서버 검증 및 공개 승인 기준
- [개인 서버 QA 발견사항](docs/PERSONAL_SERVER_QA_FINDINGS.md) — Compose 배포 오류와 수정·복구 항목
- [프로젝트 계획](docs/PROJECT_PLAN.md) — 범위와 이후 개발 후보

## 운영 안전 원칙

- Vault가 dirty하거나 upstream과 diverged 상태이면 자동 동기화를 중단한다.
- local Vault, 기존 remote clone mount, 빈 volume remote clone을 지원하며 Git 인증은 별도 persistent volume에서 재사용한다.
- 자동 merge, reset, 강제 checkout과 force push를 하지 않는다. 선택형 Vault push도 현재 tracking upstream에 대한 fast-forward만 허용한다.
- 자유 형식 agent query, 요청자 지정 Vault 경로와 임의 실행 명령을 제공하지 않는다.
- AI credential, token과 내부 비밀값을 Git, image, Job 결과나 일반 로그에 기록하지 않는다.
- 생성 작업이 실패하면 불완전한 결과 대신 직전 정상 Content를 유지한다.
- Project·Service 쓰기는 proposal branch와 명시적 승인 흐름이 구현되기 전까지 허용하지 않는다.

취약점은 공개 Issue 대신 [Security Policy](SECURITY.md)에 따라 비공개로 제보한다. 기여 절차와 변경 불가 안전 경계는 [Contributing Guide](CONTRIBUTING.md)를 따른다.

## 라이선스

APS Server의 코드와 문서는 [Apache License 2.0](LICENSE)으로 제공된다. 수정 및 재배포 시 라이선스 조건과 [NOTICE](NOTICE)의 출처 고지를 보존해야 한다.
