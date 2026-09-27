# Idea 정리 흐름

상태: 다음 구현을 위한 설계. 현재 활성 요청·응답은 [API Reference](API_REFERENCE.md), 저장 중인 Idea 형식은 [Idea 문서 형식](IDEA_DOCUMENT_FORMAT.md)을 따른다.

이 문서는 기존 베타 목표 중 **Core Vault 사서의 Idea 처리**를 먼저 구체화한다. 플러그인, 외부 AI queue와 `aps-index`보다 먼저 기존 Job API·in-process queue·Scheduler를 사용한다. 나중에 외부 queue가 추가돼도 같은 고정 operation 계약을 호출한다.

흐름은 **원문 접수 → Idea 정리 → Idea Set 정리 → Project 제안**이다. Idea 정리와 Set 정리는 서로 다른 Job이다. API는 입력 검증과 Job 생성만 하고, Agent는 구조화된 계획을 반환하며, APS Core만 Vault 파일과 Git을 변경한다.

## API와 Job 경계

| 요청 | 역할 | 입력 | 내부 처리 | 원본 변경 |
|---|---|---|---|---|
| `POST /v1/ideas/text`, `POST /v1/ideas` | operator | 사용자 Idea 본문 | Inbox 접수 | 고정 `00_Inbox`에 원문 저장 |
| `POST /v1/jobs` — `ideas.curate` | operator, scheduler | 비어 있는 고정 입력 | Inbox와 기존 Idea 비교 | 검증 후 `01_Ideas`에 한 번 commit |
| `POST /v1/jobs` — `ideas.sets.curate` | operator, scheduler | 비어 있는 고정 입력 | 추적 Idea를 주제별로 구성 | 검증 후 `01_Idea_Sets`에 한 번 commit |
| `POST /v1/jobs` — `projects.propose` | operator | 생성된 Set ID | 선택 Set을 근거로 짧은 제안 생성 | Vault 변경 없음. 결과는 Job에 저장 |

세 Job은 기존 `/v1/jobs` 접수, `/v1/jobs/{job_id}` 상태 조회와 역할 검사를 사용한다. `ideas.curate`와 `ideas.sets.curate`는 각각 수동 요청과 독립 Scheduler 실행을 지원한다. API가 AI prompt, Vault 경로나 대상 파일명을 받지 않는다.

현재 `POST /v1/idea-sets`는 사용자가 입력한 후보 Set을 Inbox에 접수하는 별도 API다. 자동 Set 정리 Job을 대체하지 않으며, 별도 호환 변경이 승인되기 전까지 유지한다.

## 내부 Job 처리

1. Job API가 operation schema와 역할을 확인하고 기존 queue에 등록한다. Scheduler도 동일한 고정 operation을 호출한다.
2. Runner가 Vault lock 안에서 clean 상태와 기준 revision을 확인하고, operation에 필요한 Inbox·Idea·Set 데이터만 읽는다.
3. Agent는 action plan 또는 짧은 제안 결과만 반환한다. 파일 경로·파일 쓰기·Git 명령은 수행하지 않는다.
4. Core가 출력 schema, 기준 revision, source ID, 중복·누락 여부와 허용된 대상 경로를 확인한 뒤 파일 변경을 적용한다.
5. Idea/Set Job은 허용된 파일만 검증해 batch commit한다. Project 제안 Job은 Vault를 변경하지 않고 결과를 Job에 저장한다.

한 단계라도 실패하면 Job을 실패 처리하고 Inbox 원문 및 직전 정상 catalog를 보존한다. AI가 없는 경우 curation/proposal Job은 비활성이고, Idea 접수·조회·검색은 계속 사용할 수 있다.

## 1. 원문 접수

`POST /v1/ideas/text`와 `POST /v1/ideas`는 아이디어를 서버가 만든 ID의 파일로 고정 `00_Inbox`에 저장한다. text endpoint는 본문을 그대로 보존한다. JSON endpoint는 현재 입력 필드를 호환 유지하며 `content`, `title`, `keywords`, `summary`의 사용자 작성 값을 읽기 쉬운 일반 본문으로 기록한다. 어느 경로도 frontmatter나 Vault Idea 템플릿을 넣지 않는다. UTF-8 검증과 줄바꿈 정규화만 적용하고, 빈 입력·크기 초과는 거부한다.

Idempotency-Key와 접수 시각 등 서버 관리 정보는 원문 본문과 분리해 저장한다. Idea 목록 API가 Inbox 항목을 보여줄 때는 파일에서 제목과 미리보기를 계산해 응답에만 채운다. 원문 파일은 바꾸지 않는다.

## 2. Inbox에서 Idea로 정리

`ideas.curate`는 Inbox의 원문과 기존 추적 Idea를 비교한다. AI는 경로가 아닌 ID만 반환하는 제한된 정리 계획을 만든다. APS Core는 모든 ID와 작업을 검증한 뒤 대상 문서를 작성한다.

| 분류 | 결과 |
|---|---|
| 서로 비슷한 Inbox 항목 | 하나의 새 Idea로 묶고 원문을 모두 새 문서 본문에 보존 |
| 기존 Idea와 유사한 Inbox 항목 | 기존 Idea 본문 끝에 원문을 추가. 기존 frontmatter의 제목·키워드·요약·상태·Set 연결은 변경하지 않음 |
| 대응하는 기존 Idea가 없는 항목 | AI가 정규화한 metadata와 Vault Idea 템플릿으로 새 Idea 문서 생성. 본문에는 원문 보존 |

정리 계획은 `append` 또는 `create` action으로 구성한다. `append`는 Inbox ID와 추적 Idea ID만 지정하며 Core가 원문을 본문에 붙인다. `create`는 하나 이상의 Inbox ID와 새 Idea의 title·keywords·summary를 지정한다. 모든 Inbox ID는 action 하나에만 포함돼야 한다. 판단할 수 없거나 결과가 검증에 실패한 항목은 남겨 둔다. Core는 `01_Ideas` 대상 전체 변경을 검증하고 한 commit으로 게시한다. commit이 성공한 뒤 처리된 Inbox 파일만 삭제한다. 재시작·재시도 때 본문이 중복 추가되지 않도록 추가 내용에 원문 ID를 기록한다. tracked 쓰기는 기존 Scheduler commit 경계를 유지한다.

이 Job은 Idea Set을 만들거나 수정하지 않는다. 기존 구현의 `set_candidates` 결과는 다음 Job으로 옮긴다.

## 3. Idea Set 별도 정리

새 `ideas.sets.curate` Job은 추적된 `01_Ideas` 문서만 분석한다. 의미가 가까운 Idea와 함께 확장할 수 있는 두 개 이상의 Idea를 묶어 `01_Idea_Sets`에 `suggested` Set을 만든다. AI 결과는 Set별 title·keywords·summary·member IDs로 제한한다.

- Idea 문서는 수정하지 않는다. Set 문서의 `member_idea_ids`만 관계의 원본으로 둔다.
- 동일한 구성원의 Set을 중복 생성하지 않는다. 같은 `suggested` Set은 갱신할 수 있지만 `approved`, `rejected`, `archived` Set은 자동 변경하지 않는다.
- 결과 ID와 멤버가 검증된 Set 문서만 한 번에 commit한다. AI가 없거나 Job이 실패하면 기존 Idea와 Set을 보존한다.
- Scheduler 등록은 `ideas.curate`와 독립한다. 한 Job의 실패나 실행 주기가 다른 Job을 막지 않는다.

## 4. Set 기반 Project 제안

Project 제안은 `POST /v1/jobs`의 고정 operation `projects.propose`로 요청한다. 요청은 하나 이상의 생성된 `idea_set_id`만 선택하고, Core가 `suggested` 또는 `approved` Set과 구성 Idea를 읽기 전용으로 전달한다. 초기 권한은 `operator`로 둔다. API 요청은 자유 형식 agent prompt나 Vault 경로를 받지 않는다.

결과는 Vault의 Project 템플릿을 따르지 않는 짧은 제안 텍스트다. `Job.result`에 제안 본문과 근거가 된 Set ID를 담는다. Project 문서나 tracked Vault 파일은 만들거나 수정하지 않는다. Project 원본 반영은 proposal branch, diff와 명시적 승인 흐름이 별도로 준비된 뒤에만 다룬다.

## 구현 순서

1. 원문 Inbox 저장과 목록용 읽기 전용 미리보기, 기존 Idempotency-Key 동작을 분리한다.
2. `ideas.curate` 계획을 새 분류 규칙으로 변경하고 기존 Idea 본문 append의 중복 방지와 단일 commit을 적용한다.
3. Set 계획·검증을 `ideas.sets.curate` operation과 별도 Scheduler 설정으로 분리한다.
4. `projects.propose`의 고정 Set ID 입력, 역할, 결과 schema와 Job 출력을 정의한다.
5. API·권한·Job·Git 흐름을 각각 직접 확인하고 OpenAPI와 문서를 맞춘다.

원문 Inbox 저장과 metadata 분리는 0.2.1에 반영되었다. `ideas.curate`는 아직 Inbox Idea를 각각 tracked Idea로 옮긴 뒤 merge 결과와 Set 후보를 추가 생성하므로, 그룹을 하나로 소비하거나 기존 Idea 본문에 원문을 추가하지 않는다. Set 생성도 같은 Job 안에서 처리한다. 현재 `projects.propose`와 독립 Set 정리 Job은 없다. 활성 계약은 [API Reference](API_REFERENCE.md)를 기준으로 한다.
