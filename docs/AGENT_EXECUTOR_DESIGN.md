# AgentExecutor와 APS Server 모듈 구조

이 문서는 APS Server AgentExecutor의 책임과 의존 방향, 구현된 경계와 후속 범위를 정의한다. 목표는 API, Queue, Scheduler, 공식 확장과 Agent 기능이 같은 실행 경로를 사용하면서도 서로의 내부 구현을 직접 알지 않게 하는 것이다.

## 1. 설계 목표

- HTTP 요청과 Schedule은 모두 같은 Job 실행 경로를 사용한다.
- Queue는 작업을 운반할 뿐 operation이나 AI를 알지 않는다.
- Operation은 한 곳에서만 실행 순서와 권한을 정의한다.
- AgentExecutor는 모델 호출과 제한된 Tool 반복 실행만 담당한다.
- AI provider는 Vault, Job, API와 Git을 직접 참조하지 않는다.
- Tool은 Core가 소유하며 임의 경로나 명령을 받지 않는다.
- 확장은 operation의 정의와 출력 schema를 제공하지만 Core Tool의 보안 경계를 바꾸지 않는다.
- 검증이 끝난 결과만 Content 또는 허용된 Vault 경로에 반영한다.

## 2. 정리 전 구조와 적용 결과

리팩터링 전에는 다음 책임이 중복되어 있었다.

| 현재 위치 | 겹치는 책임 |
|---|---|
| `operations.py` | Core operation 분기, Idea 처리, briefing 확장 실행과 provider 환경 전달 |
| `runner.py` | Queue 처리, Vault sync, operation 실행, Idea commit 판단, Content 게시 |
| `content_store.py` | operation 이름을 다시 판별해 출력 형식과 게시 위치 결정 |
| `models.py` | Core와 공식 확장의 operation을 하나의 enum과 요청 union에 함께 고정 |
| `brief_extension.py` | 범용 확장 registry와 별개로 briefing만 특별 처리했던 제거 대상 |
| `ai_bridge.py` | schema가 고정된 compatibility gateway 호출 |

현재 operation 정책은 `OperationRegistry`와 handler에 모였고, Queue, Scheduler와 API는 registry를 소비한다. `ContentStore` publisher는 operation별 함수로 분리됐으며 briefing 전용 gateway와 extension 클래스는 제거됐다.

## 3. 목표 계층

```text
API Router ───────┐
                  ├─> JobService -> JobQueue -> JobWorker
Scheduler ────────┘                         │
                                            ▼
                                    OperationRegistry
                                            │
                                   OperationHandler
                          ┌─────────────────┼─────────────────┐
                          ▼                 ▼                 ▼
                    AgentExecutor      Domain Service    ExtensionHost
                          │                 │                 │
                    ModelProvider       Vault/Idea        package protocol
                          │                 │
                          └────── ToolRegistry ──────┘
                                            │
                                            ▼
                                    OperationResult
                          publications · changes · artifacts
                                            │
                                            ▼
                              ResultValidator / CommitGate
```

의존 방향은 위에서 아래로만 흐른다.

- API와 Scheduler는 `JobService`만 호출한다.
- Queue와 Worker는 operation의 의미를 알지 않는다.
- Handler는 필요한 domain service와 AgentExecutor를 조합한다.
- AgentExecutor는 Tool interface만 알고 실제 Vault 구현을 알지 않는다.
- Provider는 prompt/message와 schema만 받고 APS 객체를 알지 않는다.
- ContentStore와 Git commit은 검증된 `OperationResult`만 처리한다.

## 4. 권장 패키지 구조

파일을 지나치게 세분화하지 않고 책임 단위로 여섯 영역만 둔다.

```text
src/aps_server/
├─ app.py                    # FastAPI composition root와 lifecycle
├─ config.py                 # process 설정
├─ bootstrap.py              # container 초기화
├─ api/
│  ├─ auth.py                # token 인증과 역할 검사
│  ├─ errors.py              # 공통 오류 envelope
│  ├─ content.py             # Content 조회 route
│  ├─ ideas.py               # Idea route
│  └─ jobs.py                # Job/operation/scheduler route
├─ runtime/
│  ├─ jobs.py                # JobService와 상태 전이
│  ├─ queue.py               # bounded in-process queue
│  ├─ scheduler.py           # cron 등록과 Job 제출
│  ├─ operations.py          # OperationSpec, Registry, Handler protocol
│  └─ results.py             # OperationResult와 commit/publication gate
├─ agent/
│  ├─ executor.py            # workflow 및 bounded tool loop
│  ├─ contracts.py           # AgentTask, Action, Trace, limits
│  ├─ providers.py           # provider protocol과 registry
│  ├─ openai.py              # OpenAI Responses API
│  ├─ openai_compatible.py   # Chat Completions 호환 API
│  ├─ agent_http.py          # 외부 APS Agent 계약
│  └─ tools/
│     ├─ registry.py         # ToolSpec, capability 검사와 dispatch
│     ├─ vault_read.py       # ID 기반 검색 및 읽기
│     ├─ idea_write.py       # Inbox/Idea 전용 제한 쓰기
│     └─ proposals.py        # 향후 승인용 proposal 작성
├─ vault/
│  ├─ repository.py          # clean/fast-forward-only Git 경계
│  ├─ catalog.py             # Markdown metadata 읽기
│  └─ ideas.py               # Idea 문서 변환과 허용된 쓰기
├─ content/
│  ├─ contracts.py           # canonical response model
│  ├─ store.py               # 검증된 publication 저장
│  ├─ render.py              # JSON 기반 HTML viewer
│  └─ api.py                 # content type별 reader registry
└─ extensions/
   ├─ manifest.py            # package 계약
   ├─ registry.py            # 설치된 공식 package discovery
   ├─ installer.py           # 공식 package 설치
   └─ host.py                # generic stdin/stdout subprocess protocol

extensions/
└─ briefing/                 # Core package 밖의 독립 배포 원본
```

초기 리팩터링에서는 기존 public import를 급하게 모두 깨지 않는다. 새 패키지로 기능을 옮긴 뒤 기존 모듈은 짧은 re-export 또는 assembly module로 줄이고 마지막에 제거한다.

## 5. Operation 계층

`OperationSpec`이 operation에 필요한 모든 정보를 한 곳에 묶는다.

```python
class OperationSpec:
    name: str
    roles: frozenset[str]
    request_model: type[BaseModel]
    handler: OperationHandler
    agent_task: AgentTaskSpec | None
    write_policy: WritePolicy
    publisher: ResultPublisher | None
```

Handler는 Queue나 HTTP 응답을 직접 다루지 않고 하나의 결과만 반환한다.

```python
class OperationResult:
    output: BaseModel | dict
    publications: list[ContentPublication]
    changes: list[ValidatedChange]
    artifacts: list[PendingArtifact]
```

이 구조에서는 다음 분기가 사라진다.

- `JobRunner`의 `ideas.curate` 특별 commit 처리
- `ContentStore.prepare_operation()`의 operation 문자열 분기
- `OperationExecutor`의 긴 `if` 체인
- `main.py`와 Scheduler가 별도로 관리하는 operation 가용성 판단

API의 기존 요청·응답 계약은 유지한다. 요청은 registry의 `request_model`로 검증하고 `/v1/operations`는 같은 registry에서 역할별 목록을 만든다.

## 6. AgentExecutor

AgentExecutor는 두 실행 전략을 제공한다.

### Workflow mode

APS handler가 Tool 호출 순서를 결정하고 모델은 구조화된 분석 결과만 만든다.

```text
Handler가 관련 문서 수집
→ AgentExecutor.generate(task, context)
→ provider의 단일 구조화 모델 호출
→ output schema 검증
→ Handler가 결과를 OperationResult로 변환
```

브리핑, Idea 분류, Idea Set 추천과 유지보수 분석의 기본 방식이다. function calling이 없는 모델도 구조화 JSON을 만들 수 있으면 사용할 수 있다.

### Tool-loop mode

모델이 허용된 Tool 중 다음 행동을 선택하고 AgentExecutor가 반복 실행한다.

```text
model -> ToolAction JSON
      -> schema/capability/step limit 검사
      -> ToolRegistry.execute()
      -> 결과를 conversation에 추가
      -> model
      -> FinalAction JSON
```

Project 초안처럼 관련 문서를 반복 탐색해야 하는 작업에만 사용한다. provider의 native function calling은 adapter 최적화일 뿐 Core 계약으로 강제하지 않는다. 기본 계약을 `ToolAction | FinalAction` 구조화 JSON으로 두면 단순 모델 호출 provider도 같은 loop에 참여할 수 있다.

```python
class AgentTaskSpec:
    task_id: str
    mode: Literal["workflow", "tool-loop"]
    output_model: type[BaseModel]
    allowed_tools: frozenset[str]
    max_steps: int
    max_input_chars: int
    timeout_seconds: int
```

AgentExecutor는 Job 생성, Scheduler 등록, Git commit 또는 Content 게시를 수행하지 않는다.

### 기능별 AgentExecutor 적용 범위

AgentExecutor는 APS Server의 모든 요청을 대신 처리하는 계층이 아니다. 인증, 고정 경로 접근, 날짜 계산, schema 검증과 Git 반영처럼 코드로 결과가 결정되는 작업은 기존 domain service가 담당한다. 문서의 의미를 해석하거나 여러 후보 중 하나를 제안해야 하는 작업에만 AgentExecutor를 사용한다.

| 기능 | Agent 사용 | 실행 방식 | Agent 입력 | 허용 Tool | 구조화 출력 | 쓰기 경계 |
|---|---|---|---|---|---|---|
| 인증, 권한, `/health`, capability 조회 | 사용 안 함 | Core 코드 | 없음 | 없음 | 기존 API model | 없음 |
| Job 생성·상태·취소, Queue, Scheduler | 사용 안 함 | Core 코드 | 없음 | 없음 | 기존 Job model | Job store만 변경 |
| Materialized Content JSON/HTML 조회 | 사용 안 함 | Core 코드 | 저장된 canonical JSON | 없음 | 기존 Content model | 없음 |
| `vault.audit` | 사용 안 함 | Core 코드 | 고정 Vault metadata | 없음 | audit result | 없음 |
| `ideas.index.refresh`와 lexical 검색 | 사용 안 함 | Core 코드 | `01_Ideas`, `01_Idea_Sets`, `00_Inbox` catalog | 없음 | `IdeasData`, 검색 결과 | Content index만 게시 |
| Idea 접수·사용자 지정 수정 | 사용 안 함 | Core 코드 | 검증된 API model | 없음 | `IdeaItem` 또는 `IdeaSet` | 고정 Inbox 또는 명시된 Idea 한 건 |
| `briefing.daily` | 사용 | workflow | Core가 수집한 활성 ProjectContext, Task, 결정과 기준일 | 기본적으로 없음 | project별 task·note 분석 결과 | canonical Content만 게시 |
| `briefing.project` | 사용 | workflow | 선택된 project ID의 정규화된 context bundle | 기본적으로 없음 | 단일 Project briefing 분석 결과 | canonical Content만 게시 |
| `service.maintenance_due` | 조건부 사용 | Core 계산 + 선택적 workflow | Core가 계산한 due/overdue 자료와 서비스 요약 | 없음 | 설명·우선순위 보강 결과 | canonical Content만 게시 |
| `ideas.curate` 문서 승격 | 사용 안 함 | Core 코드 | 검증된 pending 문서 | 없음 | 검증된 catalog | `01_Ideas`, `01_Idea_Sets` batch commit |
| `ideas.curate` 의미 정리·중복 후보·Set 추천 | 사용 | workflow | pending 및 유사 후보의 title, keywords, summary | 필요 시 read-only Idea 조회 | `IdeaCurationPlan` | 결과는 `ValidatedChange`; Core commit gate가 반영 |
| Project 제안 작성 | 사용 | bounded tool-loop | 확인된 사용자 요청과 Vault snapshot | Project·Idea·Service 검색/읽기, proposal 초안 생성 | `ProjectProposal` | 승인 기능 전에는 proposal artifact만 생성 |
| Service 변경 제안 | 사용 | bounded tool-loop 후보 | 유지보수 요청과 관련 문서 snapshot | Service 읽기, 관련 Project 검색, proposal 초안 생성 | `ServiceChangeProposal` | 승인 기능 전에는 proposal artifact만 생성 |
| `aps-index` vector 생성·유사도 계산 | 사용 안 함 | 별도 deterministic service | title, keywords, summary | 없음 | vector 검색 후보 | index volume만 변경 |
| 공식 확장 operation | manifest별 결정 | workflow 우선 | Core가 정규화한 context bundle | manifest에 선언한 Core capability만 | 확장별 output schema | Core의 result/commit gate 적용 |

현재 `ideas.curate`는 pending 문서를 검증하고 추적 폴더로 옮기는 결정적 작업만 수행한다. Agent 기능을 추가할 때에는 이 승격 단계 자체를 모델에 맡기지 않고, 그 앞에 의미 분석을 수행하는 `IdeaCurationPlan` 생성 단계를 둔다. 모델이 제안한 제목·키워드·요약·중복·Set 결과가 schema와 정책을 통과한 경우에만 기존 batch commit 흐름에 전달한다.

### 기능별 필요한 Agent task

초기 구현에서는 task 종류를 다음 네 가지로 제한한다. 아래 task가 모두 Core에 포함된다는 뜻은 아니다. Core는 범용 task 실행 계약만 제공하고, `briefing.project-analyze`는 `briefing` 공식 확장이 등록하고 소유한다.

#### `briefing.project-analyze`

- 소유자: 공식 `briefing` 확장
- mode: `workflow`
- 목적: 하나의 ProjectContext에서 오늘 수행할 작업과 주의 사항을 추출한다.
- 입력: project ID, 기준일, project metadata, task와 decision의 정규화된 텍스트
- 출력: 현재 `BriefingAIResponse`와 호환되는 `today_tasks`, `notes`
- Tool: 없음. Handler가 필요한 문서를 호출 전에 수집한다.
- 제한: ProjectContext 한 건, 출력 task 3개와 note 2개, Content 외 쓰기 없음

`briefing.daily`는 이 task를 활성 프로젝트별로 제한된 병렬 실행하고, 날짜·서비스 기한·최종 집계는 briefing handler가 계산한다. `briefing.project`는 같은 task를 한 번만 호출한다. 따라서 두 operation을 위한 별도 Agent 로직을 만들지 않는다.

#### `ideas.curate-plan`

- mode: `workflow`
- 목적: pending Idea를 정규화하고 유사 Idea, 병합 후보와 Idea Set 후보를 제안한다.
- 입력: pending Idea batch와 Core 검색기가 미리 좁힌 기존 Idea 후보
- 출력: `IdeaCurationPlan` 하나
- Tool: 초기에는 없음. 입력 한도를 넘겨 후보를 추가 탐색해야 할 때만 `vault.search_ideas`, `vault.read_idea`를 허용한다.
- 제한: 모델은 기존 문서 삭제나 source ID 변경을 요청할 수 없고, 모든 결과는 원본 ID와 연결되어야 한다.

`IdeaCurationPlan`은 최소한 다음 항목을 포함한다.

```text
normalized_ideas[]  # title, keywords, summary 정리안
merge_candidates[]  # 원본 ID 목록과 새 통합 Idea 제안
set_candidates[]    # 구성원 ID 목록과 Idea Set 제안
warnings[]          # 불충분하거나 충돌하는 자료
```

모델 출력은 바로 Vault를 수정하지 않는다. Idea handler가 참조 ID 존재 여부, 중복, 길이, 허용 상태와 대상 디렉터리를 검증해 `ValidatedChange`로 바꾼 후 기존 Scheduler commit 흐름이 한 번에 반영한다.

#### `service.maintenance-analyze`

- mode: `workflow`
- 목적: Core가 계산한 유지보수 기한과 문서 내용을 사람이 읽기 좋은 우선순위·요약으로 보강한다.
- 입력: 계산 완료된 service record만 사용한다.
- 출력: service ID별 summary, priority, issue 제안
- Tool: 없음
- 제한: due date와 days overdue는 모델이 다시 계산하거나 덮어쓸 수 없다.

이 task는 선택 사항이다. AI를 사용할 수 없을 때에도 현재의 결정적 `service.maintenance_due` 결과는 정상 생성되어야 한다.

#### `projects.proposal-draft`

- mode: `tool-loop`
- 목적: 사용자 확인을 받은 요구로부터 관련 Project, Idea와 Service를 탐색해 Project 문서 제안을 만든다.
- 입력: 확인된 요청, 고정 Vault commit, 서버가 발급한 proposal ID
- Tool: `vault.search_projects`, `vault.read_project`, `vault.search_ideas`, `vault.read_idea`, `vault.read_service`, `projects.create_proposal`
- 출력: `ProjectProposal`과 사용한 source ID 목록
- 제한: 최대 8 step, 쓰기 Tool 최대 1회, path·branch·remote는 입력받지 않는다.

이 task는 proposal branch와 명시적 승인 계약이 구현되기 전까지 공개 API에 연결하지 않는다. 초기 AgentExecutor 검증용으로도 실제 Vault tracked 문서를 수정해서는 안 된다.

### AgentExecutor 자체에 필요한 공통 기능

기능별 task를 지원하기 위해 Executor에는 다음 책임만 둔다.

1. `AgentTaskSpec` 로드와 operation별 허용 mode·schema·Tool·limit 고정
2. Job이 고정한 Vault commit과 정규화 context를 `AgentExecutionContext`로 전달
3. provider-neutral 구조화 생성 호출과 Pydantic output 검증
4. `workflow` 단일 호출 및 schema 오류의 제한된 재시도
5. `tool-loop`의 `ToolAction | FinalAction` 해석과 최대 step 종료
6. Tool 이름, 입력 schema, capability, 호출 횟수와 side effect 검사
7. task timeout, 최대 입출력 문자, 최대 provider 응답 크기와 누적 Tool 결과 크기 제한
8. credential·절대경로·문서 원문을 제외한 안전한 execution trace 생성
9. provider 실패를 공통 오류 코드로 변환하고 검증되지 않은 결과 폐기
10. native tool calling이 없는 provider를 위한 JSON action fallback

Task와 Tool의 Pydantic input/output model은 `extra="forbid"`를 사용해야 한다. 알 수 없는 필드를 조용히 버리지 않고 registration 시점에 계약 자체를 거부한다.

Executor가 담당하지 않는 것은 Vault sync, Job 상태 변경, Git commit, Content 게시, Scheduler 등록, extension 설치와 HTTP 인증이다.

### vLLM과 OpenAI-compatible provider 요구사항

Core Agent 계약은 provider의 native function calling에 의존하지 않는다.

- 구조화 출력을 지원하는 서버는 JSON Schema response format을 사용한다.
- response format을 지원하지 않는 vLLM 배포는 schema를 system instruction에 포함하고 반환 JSON을 Core에서 검증한다.
- native tool calling을 지원하면 adapter가 이를 `ToolAction`으로 정규화한다.
- native tool calling이 없으면 모델이 고정된 `ToolAction | FinalAction` JSON을 반환하게 한다.
- provider별 endpoint, model, credential과 capability는 서버 설정으로만 결정하며 API 요청에서 받지 않는다.
- schema 검증 실패나 step 초과 시 write 결과는 전부 폐기하고 기존 Content를 유지한다.

이 방식이면 단순 OpenAI-compatible generation endpoint만 제공하는 vLLM도 `workflow` task에 바로 사용할 수 있다. `tool-loop`는 JSON 지시 준수 능력이 충분한 모델에서만 활성화하며 provider readiness와 별도로 task capability를 검사한다.

### Briefing 확장 분리 원칙

`briefing`은 APS Server와 함께 개발하고 공식 package로 배포하지만 Core 기능은 아니다. 확장을 설치하지 않은 기본 image에서는 briefing operation, schedule, prompt와 output schema가 등록되지 않아야 한다.

Core가 소유하는 항목:

- provider 설정과 credential
- 범용 `AgentExecutor`, `AgentTaskSpec`과 실행 제한
- extension manifest 및 task 등록 검증
- 정규화 context bundle 전달 protocol
- JSON Schema 검증, 공통 오류와 execution trace
- Job, Queue, Scheduler와 canonical Content 게시 pipeline
- 확장이 요청할 수 있는 고정 Core Tool capability

`briefing` 확장이 소유하는 항목:

- `briefing.daily`, `briefing.project`, `service.maintenance_due` operation 정의
- `briefing.project-analyze` task ID와 workflow 설정
- briefing 전용 prompt, input/output JSON Schema
- ProjectContext를 briefing 입력으로 바꾸는 변환 규칙
- 일일·프로젝트 브리핑 결과 조립과 service 표시 규칙
- briefing Content publication descriptor와 HTML viewer descriptor
- 기본 briefing schedule

Core에 두지 않는 항목:

- `BriefingAIResponse` 같은 briefing 전용 Pydantic model
- briefing prompt 문자열과 task 개수 제한
- `if operation == briefing...` 형태의 operation 분기
- briefing 전용 subprocess 실행 명령
- briefing 설치를 전제로 한 기본 schedule

목표 호출 경계는 다음과 같다.

```text
briefing extension manifest
→ OperationRegistry에 briefing handler/task descriptor 등록
→ ExtensionHost가 Core 정규화 context를 확장에 전달
→ 확장이 AgentTaskRequest JSON 반환
→ Core AgentExecutor가 설정된 provider 호출
→ 검증된 AgentTaskResult JSON을 확장에 반환
→ 확장이 canonical publication 후보 생성
→ Core ResultValidator와 ContentStore가 게시
```

확장은 provider endpoint, API key, model 또는 실행 파일을 선택하지 않는다. Core도 briefing의 prompt와 결과 의미를 알지 않는다. 양쪽은 versioned JSON protocol과 manifest capability로만 연결한다.

briefing 전용 `brief_extension.py`, `ai_bridge.py --schema briefing`과 Core `BriefingAIResponse`는 제거됐다. 현재 적용 상태는 다음과 같다.

1. extension manifest가 Agent task, contract, prompt와 resource를 선언한다.
2. briefing prompt와 schema는 `extensions/briefing`이 소유한다.
3. ExtensionHost는 manifest가 소유한 operation과 고정 요청 JSON만 entrypoint에 전달한다.
4. 확장의 고정 bridge 요청은 Core AgentExecutor와 선택된 provider가 실행한다.
5. 확장 미설치 상태에서는 briefing operation과 schedule을 등록하지 않는다.

남은 전환 항목은 legacy briefing materializer가 Vault를 직접 읽는 부분을 Core의 정규화된 read-only context bundle로 바꾸는 것이다.

## 7. Tool 계약

Tool은 모델이 호출할 수 있는 임의 Python 함수가 아니라 이름, 입력 schema와 capability가 고정된 Core 객체다.

```python
class ToolSpec:
    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    capability: str
    side_effect: Literal["none", "draft"]
```

초기 Tool 범위:

| Tool | 입력 | 권한 | 부작용 |
|---|---|---|---|
| `vault.search_ideas` | query, limit | read | 없음 |
| `vault.read_idea` | idea_id | read | 없음 |
| `vault.search_projects` | query, limit | read | 없음 |
| `vault.read_project` | project_id | read | 없음 |
| `vault.read_service` | service_id | read | 없음 |
| `ideas.create_draft` | 정규형 Idea | idea-draft | `00_Inbox` 후보 |
| `ideas.propose_merge` | ID와 정규형 결과 | idea-draft | change set 후보 |
| `ideas.propose_set` | ID 목록과 metadata | idea-draft | change set 후보 |
| `projects.create_proposal` | 정규형 Project 초안 | proposal | 향후 proposal 저장 |

안전 규칙:

- Tool 입력은 ID와 제한된 field만 받으며 filesystem path를 받지 않는다.
- Tool은 shell, executable, provider 설정과 credential을 받지 않는다.
- read Tool은 Job 시작 시 고정한 Vault commit snapshot만 읽는다.
- 모델이 만든 write action은 즉시 Git에 반영하지 않고 `ValidatedChange`가 된다.
- operation의 `WritePolicy`가 모든 change를 허용한 뒤 Core commit gate가 한 번만 반영한다.
- Idea Scheduler commit은 `01_Ideas`와 `01_Idea_Sets`만 허용한다.
- Project와 Service는 명시적 승인 기능 전까지 proposal 생성만 허용한다.
- step, 시간, 입력 문자 수, 출력 크기와 Tool별 호출 횟수를 제한한다.

## 8. 확장과 Agent의 경계

공식 확장은 독립 패키지이지만 Agent runtime을 직접 소유하지 않는다.

확장이 제공할 수 있는 것:

- operation manifest
- request/output JSON Schema
- prompt template 또는 context 변환기
- Content publication descriptor
- 필요한 Core Tool capability 목록
- 기본 Schedule

확장이 제공할 수 없는 것:

- provider endpoint, model 또는 credential 선택
- 새로운 filesystem/shell Tool 구현
- Vault commit, merge, reset 또는 push
- API route와 인증 우회
- 다른 확장의 Tool이나 operation 교체

ExtensionHost는 manifest 소유 entrypoint에 고정 operation과 요청 JSON을 전달하고 확장은 stdout JSON만 반환한다. briefing은 이 protocol을 사용하며, 직접 Vault 읽기는 정규화 context bundle로 전환할 예정이다.

## 9. 실행 경계와 상태 전이

하나의 Job은 다음 순서로만 진행한다.

```text
QUEUED
→ SYNCING: Vault clean 및 fast-forward 확인, commit snapshot 고정
→ RUNNING: OperationHandler와 선택형 AgentExecutor 실행
→ VALIDATING: output, publication과 change set 검증
→ COMMITTING: 허용된 change가 있을 때 한 번만 commit
→ PUBLISHING: canonical Content 원자적 게시
→ SUCCEEDED / FAILED
```

`COMMITTING` 상태는 Agent 쓰기를 구현할 때 공개 Job 계약에 추가한다. commit이 실패하면 Content를 게시하지 않는다. Content 게시 실패 시 Vault commit은 되돌리지 않고 Job에 복구 가능한 상태를 기록하며 다음 refresh로 재생성한다.

## 10. 단계별 정리 순서

큰 재작성 대신 다음 순서로 이동한다.

1. `OperationSpec`, `OperationResult`, `OperationRegistry`를 추가하고 기존 operation을 registry handler로 감싼다.
2. `JobRunner`에서 operation별 commit과 publication 분기를 제거하고 공통 result pipeline을 사용한다.
3. `ContentStore.prepare_operation()`을 operation별 publisher 객체로 분리한다.
4. AI provider interface와 provider별 adapter를 `agent/providers`로 옮긴다.
5. workflow mode AgentExecutor와 제한된 ToolRegistry 및 Core read-only Tool을 구현한다. **완료**
6. `ideas.curate`를 workflow mode와 검증·단일 commit gate로 이전한다. **완료**
7. briefing special case를 generic ExtensionHost protocol로 이전하고 전용 Core gateway를 제거한다. **완료**
8. 승인·proposal branch 계약을 구현한 뒤 bounded tool-loop Project proposal task를 추가한다. **후속 범위**

각 단계에서 HTTP API, Job 저장 형식, Schedule 설정과 canonical Content 형식은 유지한다. 별도 테스트 파일을 추가하지 않고 해당 API, 권한, Job 상태 전이와 Vault 쓰기 경계를 직접 실행해 검증한다.

## 11. 확정할 기본값

- 기본 Agent 전략은 `workflow`다.
- `tool-loop`는 operation이 명시적으로 요청할 때만 사용한다.
- 기본 최대 step은 8 이하로 제한한다.
- Tool은 Core만 등록하고 확장은 capability만 요청한다.
- 모델은 path가 아닌 APS ID만 다룬다.
- 모든 write는 change set과 commit gate를 통과한다.
- provider 장애나 schema 오류 시 기존 Content를 유지한다.
- in-process queue를 사용하는 동안 web process는 하나만 유지한다.
