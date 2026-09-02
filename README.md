# APS Server

APS Server는 한 사용자의 APS Vault를 연결해 브리핑, 아이디어, 프로젝트 및 서비스 유지보수 정보를 제공하는 FastAPI 기반 백엔드다. 하나의 APS Server 컨테이너는 한 명의 마스터 사용자와 하나의 Vault를 기준으로 운영한다. 여러 사용자를 수용할 때는 사용자별 컨테이너를 분리하고 앞단 프록시에서 요청을 전달한다.

Vault의 Markdown 문서가 원본이며 APS Server는 인증, 안전한 동기화, 작업 실행, 결과 저장과 API 제공을 담당한다. 조회 요청마다 AI를 실행하지 않고 cron 또는 Job이 미리 생성한 결과를 반환한다.

> **Release status:** `0.1.0` pre-release. Core MVP 구현은 완료됐으며 현재 개인 서버에서 운영 QA와 보안 검증을 진행하는 단계다. 공개 인터넷에 직접 노출하거나 복구 계획 없이 실사용 Vault에 연결하는 것은 아직 권장하지 않는다.

## 핵심 원칙

- APS Vault의 Markdown을 원본 데이터로 사용한다.
- Vault 동기화는 clean 상태에서 fast-forward만 허용한다.
- API가 반환하는 기준 데이터는 항상 검증된 JSON이다.
- HTML은 같은 JSON을 고정 템플릿에 주입하는 뷰어다.
- 조회 요청 중에는 Codex 또는 다른 AI를 실행하지 않는다.
- 자유 형식 agent query와 요청자가 지정하는 Vault 경로를 제공하지 않는다.
- 임의 shell 명령, 실행 파일 경로 또는 Codex 인자를 API로 받지 않는다.
- Idea 접수는 Git에서 제외된 고정 `00_Inbox`만 사용하고, 검증된 Idea 정리 결과만 Scheduler가 `01_Ideas`와 `01_Idea_Sets`에 commit한다.
- Project·Service 등 다른 Vault 쓰기는 proposal branch와 명시적 승인 절차가 구현되기 전까지 허용하지 않는다.
- in-process queue를 사용하는 동안 web process는 하나만 실행한다.

## 전체 구성

```text
client / cron / reverse proxy
              │ Bearer token
              ▼
┌──────────────────────────────────────────┐
│ APS Server                               │
│ FastAPI · auth · Job queue · scheduler   │
│ Vault sync · JSON store · HTML renderer  │
│ official extensions                      │
└───────────────┬──────────────────────────┘
                │ read + Idea 전용 제한 쓰기
                ▼
          APS Vault (Markdown)

선택 구성:
APS Server ── internal API ── aps-index
                              GPU embedding
                              vector index
```

역할 경계의 세부 내용은 [아키텍처](docs/ARCHITECTURE.md), 컨테이너 설정은 [배포 가이드](docs/CONTAINER_DEPLOYMENT.md), 상세 HTTP 계약은 [API Reference](docs/API_REFERENCE.md), 설계 기준은 [Content API](docs/CONTENT_API.md), AI 연결은 [AI provider 설정](docs/AI_PROVIDERS.md), 개발 방향은 [프로젝트 계획](docs/PROJECT_PLAN.md)에서 관리한다. 개인 서버 검증과 공개 승인 기준은 [Pre-release QA](docs/PRE_RELEASE_QA.md)를 따른다.

## JSON과 HTML 응답

콘텐츠 생성 흐름은 다음과 같다.

```text
Vault 동기화
→ cron 또는 Job 실행
→ canonical JSON 생성
→ JSON Schema 검증
→ materialized result 저장
→ API 조회 시 JSON 반환
                    └─ format=html이면 고정 템플릿으로 렌더링
```

JSON과 HTML은 서로 다른 결과가 아니다. HTML 요청도 저장된 JSON을 읽으며 AI 작업을 다시 실행하지 않는다.

```http
GET /v1/content/briefing/daily?format=json
GET /v1/content/briefing/daily?format=html
```

HTML은 Nginx 등의 reverse proxy를 통해 직접 웹 페이지처럼 제공할 수 있다. 서버는 HTML에 제한적인 Content Security Policy를 적용하고 외부 스크립트 실행을 전제로 하지 않는다.

## 현재 구현된 기능

상세 요청·응답 schema, role, 성공 상태와 오류 코드는 [API Reference](docs/API_REFERENCE.md), 전체 machine-readable 계약은 [OpenAPI](specs/aps-api.openapi.json)를 참고한다.

현재 저장소는 문서에 정의한 Core MVP 완료 조건을 충족한다. 다음 기능은 컨테이너에서 함께 실행된다.

- FastAPI 애플리케이션과 Bearer token 인증
- `operator`, `viewer`, `scheduler` 역할
- Vault clean 검사와 fast-forward-only 동기화
- in-process 비동기 Job queue
- 숫자 5필드 cron과 IANA timezone을 사용하는 내장 Scheduler
- 기본 schedule 영속 설정과 scheduler 실행 상태 조회
- 서버 시작 시 queued Job 재등록과 중단된 Job의 안전한 실패 처리
- Job 생성, 상태 조회, 취소 및 Artifact 다운로드
- Job 출력의 Pydantic 계약 검증과 canonical JSON checksum 생성
- 검증된 Job 결과의 materialized ContentStore 원자적 게시
- JSON 기반 일일 브리핑, 프로젝트, 유지보수 및 Idea 조회
- 동일한 콘텐츠의 서버 측 HTML 렌더링
- live/readiness healthcheck
- 고정된 읽기 operation과 Idea 전용 제한 commit operation 실행
- 확장이 설치되지 않은 Core-only 기본 실행
- 공식 확장 package 검증·설치 CLI와 재시작 기반 활성화
- 확장 manifest Schedule의 자동 등록과 사용자 시간 override
- Core AI gateway와 `codex`, `openai-compatible`, `agent-http` provider 선택
- 초기 설정에서 AI provider 명시 선택과 provider별 필수 설정 검증

### 코드 구조

| 모듈 | 책임 |
|---|---|
| `main.py` | 애플리케이션 lifecycle, 인증, Job 제어 API 조립 |
| `ai_gateway.py` | 서버 설정 기반 AI provider 선택과 구조화 응답 검증 |
| `ai_bridge.py` | 공식 확장이 Core gateway를 호출하는 고정 stdin/stdout 계약 |
| `content_api.py` | materialized JSON 및 HTML Content 조회 라우트 |
| `idea_api.py` | Idea 조회·접수·수정 라우트 |
| `api_support.py` | Content 응답 형식과 공통 HTTP 오류 처리 |
| `runner.py` | bounded in-process queue와 Job 실행 상태 전이 |
| `scheduler.py` | 고정 Schedule 로딩·영속 상태·Job 등록 |
| `schedule_models.py` | cron parser와 Schedule 계약 모델 |
| `content_store.py` | canonical JSON 검증과 원자적 게시 |
| `idea_service.py` | Git 제외 Inbox 및 Idea 전용 제한 쓰기 |
| `vault.py` | clean/fast-forward-only Git 경계 |

모듈 사이의 상세 흐름은 [아키텍처](docs/ARCHITECTURE.md)를 참고한다. 공개 API를 변경할 때는 구현과 함께 [API Reference](docs/API_REFERENCE.md) 및 [OpenAPI](specs/aps-api.openapi.json)를 같은 변경에서 갱신한다.

### Content API

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/v1/content/briefing/daily` | 저장된 일일 브리핑 |
| `GET` | `/v1/content/projects` | 프로젝트 목록 |
| `GET` | `/v1/content/projects/{project_id}/briefing` | 프로젝트 브리핑 |
| `GET` | `/v1/content/services/maintenance` | 서비스 유지보수 정보 |
| `GET` | `/v1/content/ideas` | `title/keywords/summary` 기반 Idea와 Idea set 결과 |
| `GET` | `/v1/content/status` | 콘텐츠 생성 상태 |
| `GET` | `/v1/ideas` | Idea 목록과 필터 |
| `GET` | `/v1/ideas/{idea_id}` | Idea 상세 |
| `POST` | `/v1/ideas/search` | 제목·키워드·요약 기반 lexical 검색 |
| `GET` | `/v1/ideas/{idea_id}/similar` | 유사 Idea 후보 |
| `GET` | `/v1/idea-sets/recommended` | 추천 Idea set |
| `POST` | `/v1/ideas` | 고정 `00_Inbox`에 pending Idea 접수 |
| `PATCH` | `/v1/ideas/{idea_id}` | pending Idea 수정 또는 tracked Idea 즉시 commit |
| `POST` | `/v1/ideas/merge` | 원본을 보존하는 통합 Idea를 Inbox에 접수 |
| `POST` | `/v1/idea-sets` | Idea Set 후보를 Inbox에 접수 |

Content API는 `operator`와 `viewer`가 사용할 수 있다. 콘텐츠 엔드포인트의 기본 형식은 JSON이며, 지원하는 엔드포인트에 `?format=html`을 지정하면 같은 JSON의 HTML 뷰를 반환한다.

### Job API

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/v1/operations` | 토큰 역할이 실행할 수 있는 operation 목록 |
| `GET` | `/v1/extensions` | 현재 프로세스에서 활성화된 공식 확장 목록 |
| `GET` | `/v1/scheduler` | 내장 Scheduler, queue와 schedule 실행 상태 |
| `POST` | `/v1/jobs` | Job 생성 |
| `GET` | `/v1/jobs/{job_id}` | Job 상태와 결과 조회 |
| `POST` | `/v1/jobs/{job_id}/cancel` | Job 취소 |
| `GET` | `/v1/jobs/{job_id}/artifacts/{artifact_id}` | Artifact 다운로드 |

확장이 없는 기본 서버에는 `vault.audit`, `ideas.index.refresh`, `ideas.curate`가 활성화된다. 이 가운데 `ideas.curate`만 검증된 Idea 전용 경로를 commit한다.

| Operation | 허용 역할 | 설명 |
|---|---|---|
| `briefing.daily` | scheduler, operator, viewer | `briefing` 설치 시 일일 브리핑 생성 |
| `briefing.project` | operator, viewer | `briefing` 설치 시 지정 프로젝트 브리핑 생성 |
| `vault.audit` | scheduler, operator | 프로젝트 metadata와 브리핑 연결 점검 |
| `service.maintenance_due` | scheduler, operator, viewer | `briefing` 설치 시 서비스 점검 기한 계산 |
| `ideas.index.refresh` | scheduler, operator | Vault Idea 검증과 canonical JSON 게시 |
| `ideas.curate` | scheduler, operator | pending Idea와 Set을 검증하고 Idea 전용 경로에 batch commit |

## 목표 Content 기능

빠른 MVP에서 제공할 콘텐츠 범위는 다음 세 영역이다.

### 일일 브리핑

- 오늘 확인할 작업
- 활성 프로젝트의 Task와 진행 상태
- 서비스 점검 예정 항목
- 마지막 생성 시각과 기준 Vault commit

### Idea

- Idea 목록과 상세 조회
- 제목, 키워드 및 요약 기반 검색
- 유사 Idea 및 중복 후보
- 주기적인 정리와 그룹 후보 생성
- 새 Idea는 clone-local `00_Inbox`에 접수하고 Scheduler가 정리·검증한 뒤 commit

### Project와 Service

- 프로젝트 목록, 상세 문서 및 간단한 일정 조회
- 서비스 상태와 유지보수 예정 항목 조회
- 프로젝트 작성과 유지보수 요청은 확인 응답을 거친 proposal 작업으로 설계
- 승인 전에는 기본 브랜치의 Vault 문서를 수정하지 않음

## 공식 확장

확장은 APS Server가 제공한 읽기 전용 내용을 이용해 정해진 결과를 생성하는 공식 기능 패키지다. 현재 커뮤니티 플러그인은 계획하지 않으며 공식 저장소에서 제공한 패키지만 허용한다.

확장은 다음 제약을 가진다.

- Vault 문서를 직접 작성, 수정 또는 삭제하지 않는다.
- Git merge, reset, checkout, commit 또는 push를 수행하지 않는다.
- 인증과 권한 검사를 우회하지 않는다.
- 임의의 HTTP 경로나 shell 명령을 등록하지 않는다.
- APS Server가 전달한 입력만 읽는다.
- 결과를 사전에 정의된 JSON Schema로 반환한다.
- HTML이 필요하면 JSON 필드를 표시하는 템플릿만 제공한다.

기본 APS Server는 활성 확장 없이 시작한다. Docker image에는 설치 가능한 공식 package 원본만 `/opt/aps/official-extensions`에 들어가고, 활성 확장은 영속 볼륨의 `/data/extensions`에 별도로 설치한다. 실행 중 hot loading은 하지 않으며 설치 후 컨테이너를 재시작해 활성화한다.

```text
aps extensions list
aps extensions install <official-id>
```

`list`, `install`은 현재 구현되어 있다. update, disable, uninstall과 API를 통한 설치는 아직 제공하지 않는다. 임의 URL, 사용자 설치 스크립트 및 커뮤니티 package도 허용하지 않는다.

첫 공식 package인 `briefing`의 배포 원본은 저장소의 `extensions/briefing`에 있다. 설치 전에는 Operation과 Schedule이 등록되지 않는다. 설치 후 재시작하면 manifest의 `briefing.daily`, `briefing.project`, `service.maintenance_due`와 기본 Schedule 두 개가 자동 등록된다.

```bash
docker compose exec aps-server aps extensions list
docker compose exec aps-server aps extensions install briefing
docker compose restart aps-server
```

설치 명령은 Core schedule 파일을 수정하지 않는다. 서버 시작 시 Core 일정, 설치된 확장 manifest 일정, 사용자 override를 순서대로 합쳐 실제 Scheduler 목록을 만든다.

## Idea 검색과 선택형 `aps-index`

기본 APS Server에는 임베딩 모델을 포함하지 않는다. `aps-index` 없이도 제목, 키워드와 요약을 이용한 lexical 검색을 제공하는 것이 목표다.

```text
기본 검색
제목 일치 + 키워드 교집합 + 요약 전문 검색 + 문자열 유사도
```

규모가 커지거나 표현이 다른 유사 Idea까지 찾아야 할 때 공식 GPU 보조 서비스인 `aps-index`를 추가한다. `aps-index`는 플러그인이 아니라 배포 규모에 따라 선택하는 별도 컨테이너다.

```text
APS Server
├─ 제목·키워드·요약 추출
├─ 기본 lexical 검색
└─ aps-index 연결 시 semantic 결과와 결합

aps-index
├─ 공식 다국어 임베딩 모델
├─ 제목 + 키워드 + 요약 임베딩
├─ 벡터 저장과 유사도 검색
└─ 그룹 및 중복 후보 계산
```

Vector 인덱스는 삭제 후 다시 만들 수 있는 파생 데이터이며 Vault Markdown이 항상 원본이다. `aps-index`가 없거나 장애 상태이면 APS Server는 기본 검색으로 동작한다. 검색 API는 동일하게 유지하고 응답의 `search_mode`로 `lexical` 또는 `hybrid`를 표시한다.

현재 저장소에는 Core lexical Idea 검색 API가 구현되어 있으며, `aps-index` 컨테이너와 hybrid 검색은 아직 구현되어 있지 않다.

## 인증과 배포 단위

- APS Server 한 개는 한 명의 마스터 사용자를 대상으로 한다.
- 사용자는 여러 기기에서 접근할 수 있으며 요청 출처 IP를 고정하지 않는다.
- 각 기기는 별도 Bearer token을 사용할 수 있게 확장한다.
- 개인 서버에서는 reverse proxy 없이 사용할 수 있지만 APS Server 자체 인증은 항상 수행한다.
- 외부 공개 시 TLS reverse proxy 또는 개인 VPN 사용을 권장한다.
- 공동 작업은 사용자별 컨테이너 모델과 별도로 ProjectContext 공유 정책으로 확장한다.

현재 구현은 역할별 정적 token을 환경변수로 받는다. 기기 token 발급, 회전 및 폐기는 후속 구현 범위다.

## 실행

`.env.example`을 기준으로 token, Vault mode와 AI provider를 설정한다. `APS_AI_PROVIDER`에는 `codex`, `openai-compatible`, `agent-http` 중 하나를 반드시 선택해야 하며 기본값은 없다. 기본 `local` mode는 named volume에 새 Vault를 자동 생성하고, `git` mode는 원격 repository를 자동 clone한다. 기존 host clone은 `mounted` mode로 연결한다.

개인 서버 QA에서는 실사용 Vault가 아닌 disposable Vault로 먼저 시작하고 세 역할 token을 모두 서로 다른 무작위 값으로 교체한다.

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose ps
```

기본 image는 Node.js나 Codex CLI를 포함하지 않는 provider-neutral Python runtime이다. `openai-compatible`과 `agent-http`는 위 구성을 그대로 사용한다. `APS_AI_PROVIDER=codex`를 선택할 때만 Core image를 빌드한 뒤 Codex 전용 override를 적용한다.

```bash
docker compose build aps-server
docker compose -f compose.yaml -f compose.codex.yaml build aps-server
docker compose -f compose.yaml -f compose.codex.yaml up -d
```

공식 확장은 `APS_INITIAL_EXTENSIONS=briefing`, 선택형 index 주소는 `APS_INDEX_URL=http://aps-index:8090`으로 지정할 수 있다. Scheduler 설정은 기본적으로 `deploy/config`가 `/config:ro`에 mount된다. 전체 설정 예시는 [컨테이너 배포 가이드](docs/CONTAINER_DEPLOYMENT.md)를 따른다.

`briefing`의 AI 실행은 [AI provider 설정](docs/AI_PROVIDERS.md)에 따라 별도 Codex runtime, vLLM을 포함한 OpenAI 호환 API 또는 APS Agent HTTP 서비스 중 하나를 사용한다. provider와 model은 서버 설정이며 API 요청자가 선택할 수 없다.

기본 bind 주소는 `127.0.0.1:8080`이다.

```bash
curl http://127.0.0.1:8080/health/live

curl http://127.0.0.1:8080/v1/content/briefing/daily?format=json \
  -H "Authorization: Bearer $APS_VIEWER_TOKEN"
```

Job 생성 예시:

```bash
curl -X POST http://127.0.0.1:8080/v1/jobs \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: daily-2026-08-31" \
  -d '{"operation":"briefing.daily","input":{},"context":{}}'
```

위 `briefing.daily` 요청은 `briefing` 확장을 설치하고 서버를 재시작한 뒤 사용할 수 있다.

내장 Scheduler는 첫 실행 시 Core 전용 `${APS_DATA_PATH}/schedules.json`과 사용자 전용 `${APS_DATA_PATH}/schedule-overrides.json`을 생성한다. 확장이 없는 기본 서버에는 다음 세 일정만 활성화된다.

| Schedule | Cron | Operation |
|---|---|---|
| `idea-index` | `0 */6 * * *` | `ideas.index.refresh` |
| `idea-curate` | `15 */6 * * *` | `ideas.curate` |
| `vault-audit` | `30 4 * * *` | `vault.audit` |

`briefing` 설치 후 재시작하면 manifest에서 다음 일정이 추가된다.

| Schedule | Cron | Source |
|---|---|---|
| `briefing.daily-refresh` | `0 6 * * *` | `extension:briefing` |
| `briefing.service-maintenance` | `15 5 * * *` | `extension:briefing` |

확장 일정의 시간은 package를 수정하지 않고 `schedule-overrides.json`에서 바꾼다.

```json
{
  "version": 1,
  "overrides": [
    {
      "schedule_id": "briefing.daily-refresh",
      "cron": "30 7 * * *",
      "timezone": "Asia/Seoul",
      "enabled": true
    }
  ]
}
```

변경 후 서버를 재시작하면 적용된다. 임의 command, 실행 파일, AI 인자와 Vault 경로는 어떤 schedule에도 넣을 수 없다.

## 로컬 개발과 검증

```powershell
py -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/uvicorn aps_server.main:app --host 127.0.0.1 --port 8080
```

변경 후에는 별도 테스트 코드를 추가하는 대신 해당 API와 권한 흐름을 직접 실행해 검증한다. 최소한 live/readiness, 역할별 인증, Content JSON·HTML, Job 생성·조회·취소와 잘못된 입력 거부를 확인한다.

## MVP 이후 개발 후보

1. 공식 확장 update·disable과 checksum/서명 검증
2. Project·Service proposal branch와 명시적 승인 흐름
3. 선택형 `aps-index` 내부 API와 배포 profile
4. 기기별 token 발급·회전·폐기

위 항목은 현재 Core MVP 실행에 필요하지 않은 후속 범위다.

## 보안과 공개 전 QA

취약점은 공개 Issue 대신 [Security Policy](SECURITY.md)의 비공개 절차로 제보한다. 저장소 관리자는 공개 전에 GitHub private vulnerability reporting을 활성화해야 한다.

개인 서버에서는 [Pre-release QA](docs/PRE_RELEASE_QA.md)에 따라 Core-only 실행, 역할별 인증, Job과 Scheduler, Idea 제한 쓰기, Git 안전 경계, 공식 extension, 재시작 복구와 24시간 soak를 검증한다. QA blocker가 남아 있으면 release tag를 만들지 않는다.

## 기여

기여 방법과 변경 불가 안전 원칙은 [Contributing Guide](CONTRIBUTING.md)를 따른다. 공개 API 변경은 구현, 관련 문서와 `specs/aps-api.openapi.json`을 같은 pull request에서 갱신해야 한다.

## 라이선스

APS Server의 코드와 문서는 [Apache License 2.0](LICENSE)으로 제공된다. 수정·재배포·상업적 사용과 별도 extension 개발이 가능하며, 재배포 시 라이선스 조건과 [NOTICE](NOTICE)의 출처 고지를 보존해야 한다. Apache License는 APS, APS Server, APS Vault 또는 Labb32의 이름과 로고를 수정 제품의 보증이나 독자적인 브랜드로 사용할 권리를 부여하지 않는다.

## 운영 안전 규칙

- Vault clone이 dirty하거나 upstream과 diverged 상태이면 동기화를 중단한다.
- 자동 merge, reset, 강제 checkout과 force push를 하지 않는다.
- 생성 결과와 Vector 인덱스는 Vault 외부 데이터 경로에 저장한다.
- token, AI 인증정보 및 내부 비밀값을 Git, image, Job 결과나 일반 로그에 기록하지 않는다.
- 일부 생성 작업이 실패해도 직전 정상 결과를 보존한다.
- 외부 AI 또는 `aps-index` 장애가 기본 조회 API 전체를 중단시키지 않게 한다.
- API 요청은 미리 정의된 operation과 입력 schema만 허용한다.
