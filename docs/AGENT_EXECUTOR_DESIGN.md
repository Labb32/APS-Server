# Agent 실행 설계

이 문서는 선택 AI 사서의 실행 책임을 정한다. 현재 구현 상태는 [작업 목록](TASKS.md), 실제 공개 요청·응답은 [API Reference](API_REFERENCE.md)를 따른다. AI가 없어도 Core API는 동작한다.

## 실행 경로

```text
API 또는 내부 cron/외부 AI scheduler
  → 고정 operation과 입력 schema 검증
  → Job 접수·상태·취소
  → 필요한 Vault revision의 읽기 전용 snapshot
  → Core handler → AgentExecutor → 설정된 provider/외부 AI queue
  → 결과 schema·ID·기준 revision 검증
  → Core의 Content 게시 또는 허용된 commit gate
```

API·Scheduler는 같은 Job 경로를 사용한다. Queue는 작업을 운반하고, operation handler가 실행 순서와 권한을 정한다. AgentExecutor는 모델 호출과 제한된 Tool 반복만 수행한다. Vault sync, Git commit, Content 게시, Scheduler 등록은 하지 않는다. 외부 AI worker도 Vault/Git에 직접 쓰지 못한다. 늦은·중복 결과와 기준 revision 변경은 Core가 처리한다.

## 실행 방식과 제한

| 방식 | 사용처 | 경계 |
|---|---|---|
| `workflow` | Idea 정리, briefing, Service 분석 | 고정 입력에서 구조화 결과 생성. 제한된 schema 재시도 |
| `tool-loop` | 제한된 Project 제안 | `ToolAction`/`FinalAction`, 최대 8단계. 명시된 Tool만 사용 |

Task·Tool은 서버 시작 시 등록한다. Tool 입력/출력은 schema와 capability를 검증하고 호출 횟수·시간·크기를 제한한다. 모델은 path 대신 논리 ID를 다룬다. API 요청은 task ID·prompt·Tool·provider·model·실행 제한을 선택하지 못한다. provider endpoint·credential은 서버 설정만 사용한다. trace에는 원문 문서, prompt, Tool 결과와 secret을 남기지 않는다.

## 주요 operation

| 작업 | Agent 역할 | 최종 부작용 |
|---|---|---|
| `vault.audit`, `ideas.index.refresh`, 일반 문서 조회·검색 | 없음 | 읽기 또는 검증된 색인 게시 |
| `ideas.curate` | pending 정규화·중복/Set 후보 제안 | Core가 `01_Ideas`·`01_Idea_Sets`만 검증해 단일 batch commit. 실패 시 Inbox 보존 |
| `briefing.daily`, `briefing.project` | ProjectContext에서 task·주의 사항 생성 | canonical JSON 게시. HTML은 서버 template |
| Service 운영 분석 | Core가 계산한 기한·상태 설명 보강 | due date 등 결정적 계산값은 모델이 덮어쓰지 못함 |
| Project 제안 | 관련 Idea·Project·Service 검색과 초안 작성 | 승인 기능 전에는 proposal artifact만 생성 |
| 공식 확장 작업 | manifest의 고정 task와 허용 capability | Core가 결과를 검증한 뒤 확장별 정책에 따라 처리 |

Idea task는 pending과 검색으로 좁힌 후보의 제목·키워드·요약을 입력받고 source ID를 유지한다. Project 제안은 기준 Vault commit과 확인된 사용자 요구를 입력받는다. 모델 출력은 즉시 쓰지 않고 검증 가능한 change set으로 변환한다. Project·Service 원본 반영에는 proposal branch, diff와 명시적 승인이 필요하다.

## provider와 외부 AI 큐

현재 adapter는 OpenAI Responses, OpenAI-compatible, Agent HTTP 계약을 사용한다. 설정 방법은 [AI provider 안내](AI_PROVIDERS.md)에 있다. 외부 AI 큐는 별도로 **접수·상태·취소·결과**, 인증, idempotency, timeout·재시도, 중복/늦은 결과의 계약을 구현해야 한다. 내부 실행과 외부 실행은 동일한 operation 입력과 결과 검증을 사용한다. provider/queue 장애나 schema 오류가 나면 새 결과를 게시하지 않고 이전 정상 Content를 유지한다.

## 확장 경계

Core는 provider 설정, AgentExecutor, 고정 Tool registry, Job·검증·게시·commit gate를 소유한다. 확장은 operation/task schema, prompt, context 변환, publication descriptor와 필요한 Core capability만 선언한다. 확장은 provider·credential·filesystem/shell Tool·Git 명령·임의 API route를 추가하지 않는다. [공식 확장 계획](EXTENSION_PLAN.md)을 따른다.

in-process queue를 사용하는 동안 web process는 하나만 운영한다. 외부 AI 큐 연결만으로 다중 web process를 허용하지 않는다.
