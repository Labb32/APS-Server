# APS Server 구조 및 개발 현황

이 문서는 APS Server의 내부 구성, MVP 구현 범위와 후속 개발 항목을 정리한다. 설치와 기본 사용법은 저장소 [README](../README.md), 세부 설계는 [아키텍처](ARCHITECTURE.md)를 참고한다.

## 1. 시스템 구조

```text
client / cron / reverse proxy
              │ Bearer token
              ▼
┌──────────────────────────────────────────┐
│ APS Server                               │
│ FastAPI · auth · Job queue · scheduler   │
│ Vault sync · JSON store · HTML renderer  │
│ official extensions · AgentExecutor      │
└───────────────┬──────────────────────────┘
                │ read + Idea 전용 제한 쓰기
                ▼
          APS Vault (Markdown)

선택 구성:
APS Server ── internal API ── aps-index
APS Server ── internal API ── AI Agent / model server
```

APS Vault Markdown은 영속 원본이고 canonical JSON, HTML, Job artifact와 Vector index는 다시 생성할 수 있는 파생 데이터다. APS Server 한 개는 한 명의 마스터 사용자와 하나의 Vault를 담당한다.

콘텐츠 생성과 조회는 분리한다.

```text
Vault 동기화
→ cron 또는 Job 실행
→ canonical JSON 생성
→ JSON Schema 검증
→ materialized result 원자적 게시
→ API에서 JSON 반환
                    └─ format=html이면 고정 template 렌더링
```

## 2. MVP 구현 현황

현재 `0.1.0` MVP에 구현된 범위는 다음과 같다.

### Core와 인증

- FastAPI 애플리케이션과 단일 web process
- Bearer token 기반 `operator`, `viewer`, `scheduler` 역할
- live/readiness healthcheck
- 요청 ID, 공통 오류 envelope와 API 입력 검증
- 자유 형식 agent query 및 요청자 지정 경로 제거

### Vault와 Content

- clean working tree 검사와 fast-forward-only 동기화
- canonical JSON checksum 및 Pydantic/JSON Schema 검증
- ContentStore의 원자적 게시와 직전 정상 결과 보존
- 브리핑, 프로젝트, 서비스 유지보수와 Idea Content 조회
- 같은 JSON을 사용하는 서버 측 HTML renderer

### Job과 Scheduler

- bounded in-process 비동기 queue
- Job 생성, 조회, 취소와 artifact 다운로드
- 서버 재시작 시 queued Job 재등록 및 interrupted Job 실패 처리
- 숫자 5필드 cron과 IANA timezone 기반 Scheduler
- Core schedule, 확장 manifest schedule과 사용자 override 병합
- Scheduler와 queue 실행 상태 API

### Idea

- `title`, `keywords`, `summary` 기반 Idea 문서 형식
- Idea 목록, 상세, lexical 검색과 유사 후보 조회
- 고정된 Git-ignored `00_Inbox`에 pending Idea 접수
- pending/tracked Idea 수정
- 병합 Idea와 Idea Set 후보 접수
- Scheduler가 검증한 `01_Ideas`/`01_Idea_Sets` 변경만 batch commit

### 확장과 AI

- image 내부 공식 패키지만 허용하는 확장 installer
- 설치 후 재시작 기반 활성화와 schedule 자동 등록
- 공식 `briefing` 확장과 legacy briefing 코드 이전
- provider-neutral Core AgentExecutor와 manifest task 기반 extension bridge
- `openai`, `agent-http`, `openai-compatible` provider
- provider 응답 크기 제한과 task별 구조화 결과 검증
- Core `AgentExecutor`의 workflow와 bounded JSON tool-loop
- 시작 시 고정되는 Agent task/Tool registry와 capability 검사
- step, timeout, 입출력 크기, Tool별 호출과 draft 부작용 제한
- prompt·문서 원문·Tool 결과를 제외한 안전한 실행 trace
- ID 전용 read-only Idea·Project·Service Tool registry
- AI 구조화 결과를 검증한 Idea 정규화·병합·Set 후보 batch commit
- Node.js와 AI CLI가 없는 provider-neutral Python image

### 배포와 공개 준비

- local/git/mounted Vault bootstrap mode
- Environment 및 read-only 설정 파일 mount
- Scheduler 설정 mount와 영속 data volume
- localhost 기본 bind 및 reverse proxy 연결 설정
- APS Vault 초기 템플릿과 AI용 `AGENTS.md`
- Apache-2.0 LICENSE/NOTICE, 보안 정책과 기여 가이드
- 개인 서버용 pre-release QA 절차

## 3. 코드 구조

| 모듈 | 책임 |
|---|---|
| `main.py` | 애플리케이션 lifecycle, 인증과 Job 제어 API 조립 |
| `config.py` | 환경변수 기반 서버 설정과 provider별 검증 |
| `bootstrap.py` | Vault 준비, 초기 확장 설치와 단일 Uvicorn 실행 |
| `ai_bridge.py` | 공식 확장이 manifest task를 Core AgentExecutor로 호출하는 고정 계약 |
| `agent/contracts.py` | 범용 Agent task, context, action, result와 trace 계약 |
| `agent/providers.py` | OpenAI, OpenAI-compatible와 Agent HTTP model adapter |
| `agent/executor.py` | workflow와 최대 8단계 JSON action loop |
| `agent/tools/registry.py` | 고정 Tool schema, capability와 부작용 제한 dispatch |
| `extension_host.py` | manifest 소유 operation의 제한된 JSON subprocess 실행 |
| `content_api.py` | materialized JSON 및 HTML 조회 route |
| `content_store.py` | canonical JSON 검증과 원자적 게시 |
| `idea_api.py` | Idea 조회, 검색, 접수와 수정 route |
| `idea_service.py` | Inbox 및 Idea 전용 제한 쓰기 |
| `runner.py` | in-process queue와 Job 상태 전이 |
| `scheduler.py` | Schedule 로딩, 영속 상태와 Job 등록 |
| `schedule_models.py` | cron parser와 Schedule 계약 model |
| `operations.py` | Core 및 설치 확장 operation registry 조립 |
| `extensions.py` | 공식 확장 검증, 설치와 registry 구성 |
| `vault.py` | Git 상태 검사와 fast-forward-only 경계 |

관련 배포 파일:

| 파일 | 용도 |
|---|---|
| `Dockerfile` | 모든 API provider가 사용하는 provider-neutral Python Core image |
| `compose.yaml` | 기본 Core 배포 |
| `extensions/briefing` | 공식 briefing package 원본 |
| `vault-template` | local mode에서 복사하는 빈 APS Vault |

## 4. 기본 Operation과 Schedule

확장이 없는 서버에는 다음 operation이 있다.

| Operation | 허용 역할 | 설명 |
|---|---|---|
| `vault.audit` | scheduler, operator | Project 기본 frontmatter와 status 점검 |
| `ideas.index.refresh` | scheduler, operator | Idea 검증 및 canonical JSON 게시 |
| `ideas.curate` | scheduler, operator | pending Idea와 Set을 검증해 batch commit |

기본 일정:

| Schedule | Cron | Operation |
|---|---|---|
| `idea-index` | `0 */6 * * *` | `ideas.index.refresh` |
| `idea-curate` | `15 */6 * * *` | `ideas.curate` |
| `vault-audit` | `30 4 * * *` | `vault.audit` |

`briefing`을 설치하고 재시작하면 `briefing.daily`, `briefing.project`, `service.maintenance_due` operation과 다음 일정이 추가된다.

| Schedule | Cron | Operation |
|---|---|---|
| `briefing.daily-refresh` | `0 6 * * *` | `briefing.daily` |
| `briefing.service-maintenance` | `15 5 * * *` | `service.maintenance_due` |

시간은 확장 package를 수정하지 않고 `schedule-overrides.json`으로 변경한다.

## 5. 현재 제한 사항

- 공식 확장의 update, disable, uninstall 및 서명 검증은 아직 없다.
- Project와 Service tracked 문서 쓰기 및 승인 흐름은 제공하지 않는다.
- 기기별 token 발급, 회전과 폐기 API는 아직 없다.
- `aps-index` 연결 설정은 예약되어 있지만 hybrid 검색 adapter는 구현 전이다.
- community 확장 설치와 runtime hot loading은 지원하지 않는다.
- queue는 in-process이며 web process를 수평 확장하지 않는다.

## 6. MVP 이후 개발 후보

1. 공식 확장 update/disable과 checksum 또는 서명 검증
2. Project·Service proposal branch 및 명시적 승인 흐름
3. `aps-index` 내부 API와 hybrid Idea 검색
4. 기기별 token 발급·회전·폐기
5. 개인 서버 QA 피드백에 따른 운영 진단 및 복구 개선

우선순위와 완료 조건은 [프로젝트 계획](PROJECT_PLAN.md), 공개 전 검증은 [Pre-release QA](PRE_RELEASE_QA.md)에서 관리한다.

Agent 기반 문서 분석과 제한된 쓰기의 구현 경계와 후속 proposal 설계는 [AgentExecutor 설계](AGENT_EXECUTOR_DESIGN.md)를 따른다.
