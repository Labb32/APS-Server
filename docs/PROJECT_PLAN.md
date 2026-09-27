# APS Server 목표 베타

이 문서는 목표 범위를 정한다. 현재 동작하는 API는 [API Reference](API_REFERENCE.md), 구현 상태와 다음 순서는 [작업 현황](TASKS.md)을 따른다. 목표에 적힌 기능은 구현 완료를 뜻하지 않는다.

## 제품 목표

한 Server는 한 사용자와 한 Vault를 담당한다. AI가 없어도 인증된 API, 문서 조회, Inbox 접수, 고정 Job과 로컬 검색이 동작한다. Vault는 Project·Service와 추적 Idea의 원본이고, Server는 실행·검증·파생 결과를 관리한다.

## 베타 범위

### 1. Vault API

인증된 사용자는 고정 API로 Idea 접수·검색, Project·Service 확인, 제한된 archive 다운로드를 한다. Inbox는 JSON과 제한된 `text/plain` 요청을 받는다. 요청자는 Vault 경로, shell, 실행 파일, provider나 prompt를 지정하지 못한다.

응답은 안정된 JSON envelope와 필요한 Markdown 본문을 제공한다. HTML은 같은 검증 결과를 서버의 고정 template으로 표시한다. Content 조회는 AI, 동기화나 생성 Job을 시작하지 않는다. API 요청·응답은 [API Reference](API_REFERENCE.md)에 정의한다.

### 2. 선택 AI 사서

내부 AgentExecutor와 cron, 또는 외부 AI 큐가 고정 operation 계약으로 Inbox 정리, Idea 중복 후보·Set 구성, 제한된 Project 제안과 Service 현황을 처리한다. Server는 결과 schema와 기준 revision을 확인한 뒤 게시한다. AI가 없거나 장애가 나도 Core 조회와 접수는 계속 동작한다. Project·Service 원본 변경은 승인 흐름 전까지 허용하지 않는다. Idea 정리 단계와 쓰기 경계는 [Idea 정리 흐름](IDEA_CURATION.md)에 정의한다.

### 3. 공식 확장

베타는 세 확장을 목표로 한다.

| 확장 | 범위 | 상태 |
|---|---|---|
| `briefing` | 운영 Project·Service 요약, JSON과 고정 HTML | 기존 package를 목표 계약에 맞게 전환 |
| `migration` | Vault archive 생성·제한 다운로드, 검증된 업로드로 새 Vault 시작 | 설계 단계 |
| `service-security` | 등록된 출처의 취약점 조사, report와 alert | 설계 단계 |

상세 작업과 capability는 [확장 계획](EXTENSION_PLAN.md)을 따른다.

### 4. 대규모 검색

별도 `aps-index` 서비스가 대량 Idea 검색, 중복 후보와 Set 구성을 지원한다. 첫 단계는 Vault를 원본으로 유지하는 검색 backend다. 선택적 DB 원본 모드는 소유권·백업·Markdown export·이관·복귀 계약이 준비된 뒤 허용한다. Project·Service 원본은 Vault에 남긴다. 상세는 [aps-index 설계](../plugins/aps-index/README.md)를 따른다.

## 유지할 경계

- Inbox 쓰기는 고정 `00_Inbox`, 추적 Idea/Set 쓰기는 검증된 Scheduler commit 경로로 제한한다.
- Project·Service 원본 쓰기는 proposal, diff와 명시적 승인 전까지 비활성이다.
- Vault sync는 clean worktree에서 fast-forward만 허용한다.
- in-process queue를 쓰는 동안 web process는 하나다.
- 확장과 검색 서비스 장애가 기본 Core 기능을 막지 않도록 한다. DB가 원본인 모드에서는 없는 데이터를 정상 fallback으로 표시하지 않는다.

## 완료 판단

베타는 네 영역 각각의 계약·구현·권한·서비스 흐름을 확인하고 AI·확장·검색 서비스가 끊겨도 Core가 동작하며 실패 복구가 자료를 보존할 때 완료로 본다. 웹훅은 베타 이후 범위다.
