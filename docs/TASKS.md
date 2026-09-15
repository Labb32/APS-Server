# APS Server 개선 작업

기준일: 2026-09-15. 목표는 [PROJECT_PLAN](PROJECT_PLAN.md)을 따른다. 아래 상태는 기존 미커밋 변경을 포함한 작업 트리를 읽어 확인한 것이며 실행 검증·배포 완료를 뜻하지 않는다.

## 현재 구현과 차이

| 영역 | 확인한 코드 | 현재 상태와 남은 차이 |
|---|---|---|
| AI 선택화 | `config.py`, `main.py`, `agent/providers.py`, `bootstrap.py` | 작업 트리에 `none` 기본값·선택 executor 변경 있음. readiness와 안내까지 정합성 확인 필요 |
| 작업 차단 | `operations.py`, `scheduler.py` | `AI_DISABLED`와 일부 schedule 필터 있음. AI operation은 registry에 남고 분류가 하드코딩됨 |
| 비AI 문서 | `vault_catalog.py`, `content_store.py`, `models.py` | `vault.content.refresh`와 Project·Service materializer 추가 중. 공개 목록·상세 및 기존 briefing 계약과 통합 필요 |
| Inbox·Idea | `idea_api.py`, `idea_service.py` | Inbox 축적·overlay 조회, AI curate 및 merge/Set 요청 존재. none 모드 정책과 초기 조회 보완 필요 |
| 검색 | `idea_search.py`, `pyproject.toml` | Idea 전용 lexical/문자열 유사도. 소형 임베딩·공통 문서 검색 없음 |
| 내부 실행 | `runner.py`, `scheduler.py` | in-process queue·cron·Job 상태 있음. AI 가용성에 따른 정책 보완 필요 |
| 외부 AI 실행 | `agent/providers.py` | Agent HTTP provider 있음. 비동기 외부 큐의 접수·상태·결과 계약은 별도 구현 필요 |
| 선택 기능 | `extensions/briefing`, `extensions.py`, `config.py` | briefing 패키지와 index URL 설정 있음. 기능별 후속 작업은 plugins 문서에 격리 |

## P0 — AI 없는 Core 경계

- [ ] **CORE-01 — none 모드와 capability 통일**
  - 대상: `config.py`, `bootstrap.py`, `main.py`, `operations.py`, `runtime/operations.py`, `scheduler.py`, `extensions.py`.
  - AI 없는 정상 상태와 AI 설정 오류·외부 장애를 구별한다. 선택 서비스 장애가 기본 API를 막지 않도록 readiness와 선택 기능 상태를 분리한다.
  - operation별 AI 필요 여부를 공통 metadata로 정의하고 수동 요청·cron·확장 실행에서 동일하게 검사한다.
  - 기존 operation 계약을 유지하며 비활성 이유를 노출하고 실행을 거부한다. 비활성 AI 작업을 cron이 반복 등록하지 않게 한다.
  - 완료 조건: provider/key/model과 확장 없이 기동·기본 API 사용이 가능하며 AI 작업은 실행·원본 변경 없이 일관된 비활성 상태를 반환한다.

- [ ] **CORE-02 — 일반 문서 API와 briefing 분리**
  - 대상: `vault_catalog.py`, `content_models.py`, `content_store.py`, `content_api.py`, `html_renderer.py`, `templates/`, `models.py`, `operations.py`.
  - Idea·Idea Set·Project·Service의 목록·상세를 AI 없이 제공한다. 기본 목록은 진행 중·운영 중 상태로 제한하지 않는다.
  - 논리 ID, 이름 변경 시 ID 안정성, frontmatter 파싱, 누락·중복·잘못된 metadata 처리를 정리한다.
  - `vault.content.refresh`의 최초 생성·갱신 및 원자적 게시 정책을 확정한다. 문서 오류 시 이전 정상 결과를 보존한다.
  - 일반 문서 API와 기존 Project catalog/Service maintenance/briefing 응답의 호환 방식을 정의한다. 기존 응답 의미를 임의로 교체하지 않는다.
  - 완료 조건: 확장 없이 목록·상세와 JSON/HTML이 일관되며 Content GET이 AI나 생성 Job을 실행하지 않는다.

- [ ] **CORE-03 — Inbox 축적과 사서 정리 분리**
  - 대상: `idea_api.py`, `idea_service.py`, `idea_catalog.py`, `operations.py`, `agent/tasks/ideas.py`.
  - none 모드 신규 입력은 Inbox에 남고 자동 Idea 승격·병합·Set 정리를 하지 않는다. 기존 tracked Idea·Set은 계속 조회한다.
  - catalog가 아직 생성되지 않은 최초 실행에서도 접수한 Inbox를 읽을 수 있게 초기화/빈 catalog 계약을 정의한다.
  - merge/Set 생성 요청의 비활성 오류 또는 명시적 pending 정책을 정하고, 기존 추천 결과 조회와 신규 AI 생성 요청을 구분한다.
  - tracked Idea 직접 수정 API와 Scheduler commit 지침의 차이를 문서화하고 호환 전환안을 정한다.
  - 완료 조건: 접수·재시작 후 조회가 가능하며 AI 없는 상태에서 정리 commit이나 Inbox 원본 삭제가 발생하지 않는다.

- [ ] **CORE-04 — 배포·API·문서 정합성**
  - 대상: `README.md`, `.env.example`, `deploy/config/aps.env.example`, `deploy/config/schedules.json`, `compose.yaml`, `docs/AI_PROVIDERS.md`, `docs/CONTAINER_DEPLOYMENT.md`, `docs/CONTENT_API.md`, `docs/API_REFERENCE.md`, `specs/`.
  - AI 필수 안내를 선택 설정으로 전환하고 Core만 실행하는 구성을 기본 예시로 둔다.
  - Core catalog 갱신과 AI schedule을 분리하며 기존 설정·override에도 capability 정책을 적용한다.
  - 작업 트리 model/route와 OpenAPI·예제 차이를 정리한다. 새 endpoint/필드는 구현 전 호환 계약을 정의한다.
  - 완료 조건: 안내만으로 none 모드 구성이 가능하고 실제 route·응답 schema·문서가 일치한다.

## P1 — 내장 경량 검색

- [ ] **SEARCH-01 — 공통 검색 문서 모델** (CORE-02, CORE-03 이후)
  - Idea 전용 검색을 공통 계층으로 분리하고 Inbox·Idea·Idea Set·Project·Service를 고정 collection과 논리 ID로 식별한다.
  - 제목·키워드·짧은 요약을 중심으로 색인한다. 누락된 키워드/요약의 비AI 추출 규칙과 입력 길이 제한을 정한다.
  - 기존 Idea search/similar API는 호환 유지하고 일반 문서 검색 계약을 별도로 추가한다.
  - 완료 조건: 종류·상태 필터와 결과 ID·일치 근거를 제공하며 요청자가 임의 경로를 지정하지 않는다.

- [ ] **SEARCH-02 — 소형 임베딩 내장** (SEARCH-01 이후)
  - CPU 모델·runtime·라이선스·한국어 지원·배포 크기를 선정하고 메모리·처리량·문서 수 예산을 기록한다.
  - 모델 버전을 고정하고 배포/최초 다운로드/오프라인 정책을 정한다. 생성형 AI provider 설정과 분리한다.
  - lexical 점수와 embedding 유사도를 조합한다. 모델 실패 시 lexical로 동작하며 실제 사용한 검색 방식을 표시한다.
  - 완료 조건: 외부 AI·GPU·aps-index 없이 실제 임베딩 유사도 검색이 가능하다. 현재 문자열 유사도를 임베딩으로 표기하지 않는다.

- [ ] **SEARCH-03 — 로컬 색인 수명주기** (SEARCH-02 이후)
  - Vault commit·문서 hash·Inbox revision·model version으로 변경과 삭제를 감지하고 증분 갱신한다.
  - 서버 data 영역의 색인 저장·재시작 복구·모델 교체 재색인·실패 시 이전 정상 색인 보존을 구현한다.
  - 완료 조건: Git commit이 바뀌지 않는 Inbox도 반영되고 삭제 문서가 결과에 남지 않는다.

## P2 — 선택 AI 사서와 실행 서비스

- [ ] **AI-01 — 내부 cron 기반 사서 작업** (CORE-01, CORE-03 이후)
  - 기존 AgentExecutor/Idea curation을 선택 서비스 경계로 묶고 AI 연결 시에만 정규화·중복 정리·Set 구성을 실행한다.
  - timeout·취소·실패·재시작·중복 요청에서 Inbox를 보존하고 검증된 대상만 단일 batch commit한다.
  - 완료 조건: none에서 축적한 Inbox를 연결 후 처리하며 실패가 자료 유실·중복 commit을 만들지 않는다.

- [ ] **AI-02 — 외부 AI 큐 adapter** (CORE-01 이후)
  - 동기 Agent HTTP와 별개로 제출·외부 Job ID·상태 조회·취소·결과 수신 계약을 정의하고 polling/callback 방식을 정한다.
  - 내부/외부 실행은 동일 operation 입력·결과 검증을 사용한다. 외부에는 고정 task와 제한된 snapshot만 전달한다.
  - 인증·idempotency·timeout·재시도·늦은/중복 결과·기준 Vault revision 변경을 처리한다. 외부 worker에 Vault 직접 쓰기나 Git 권한을 주지 않는다.
  - 완료 조건: 외부 장애 중 Core가 동작하고 APS Server가 결과를 검증한 뒤 기존 게시/commit 경계에서 한 번만 반영한다.

- [ ] **AI-03 — Project 정리·제안** (CORE-02, AI-01 이후)
  - 고정 task로 관련 Idea·Project를 분석해 정리안·제안을 파생 결과로 제공한다. none 모드에는 생성 기능이 없다.
  - 원본 반영이 필요하면 proposal branch·기준 commit·diff·승인/거부·만료를 먼저 구현한다. 준비 전에는 초안만 저장한다.
  - 완료 조건: 제안은 조회 가능하고 승인 전 Project·Service 원본은 바뀌지 않는다. 기본 branch 자동 병합은 추가하지 않는다.

## 선택 기능 작업 위치

- [.brief](../plugins/brief/README.md): 상태 필터·Service briefing·일반 문서와의 분리.
- [aps-index](../plugins/aps-index/README.md): 대규모 RAG/Vector DB와 Inbox/Idea 저장·검색 대체.
- [백업·마이그레이션](../plugins/backup-migration/README.md): 전체 보존·복원·이전.
- [웹훅](../plugins/webhooks/README.md): 조건 등록·Discord/메일 요청·응답·전달.

## 진행 순서와 확인 정책

CORE-01~04 → SEARCH-01~03 → AI-01~03 순으로 진행한다. 외부 큐 계약은 검색 구현과 독립적으로 설계할 수 있다. 선택 기능은 필요한 Core 계약이 준비된 뒤 별도 진행하며 Core 완료 조건에 포함하지 않는다.

코드·문서·공개 계약을 함께 맞춘 후 작업을 체크한다. 이번 문서 작성에서는 코드 변경이나 테스트 생성·수정·실행을 하지 않았다. 후속 구현 확인은 관련 API·권한·서비스 흐름의 직접 실행으로 계획하며 테스트 파일·케이스·명령은 사용자 명시 요청 시에만 다룬다. 기존 QA 문서도 새 범위로 갱신하되 실행 완료로 간주하지 않는다.
