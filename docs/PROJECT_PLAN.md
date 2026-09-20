# APS Server 목표와 개발 범위

기준일: 2026-09-20. 기존 AI·브리핑 중심 MVP 계획을 대체한다. 이 문서는 개선안 완료 후의 **목표 베타 빌드** 범위를 정의한다. 현재 구현과 남은 작업은 [TASKS](TASKS.md), 공식 확장의 기획·개발은 [확장 계획](EXTENSION_PLAN.md)에서 관리한다. 목표로 적힌 기능은 현재 구현 완료를 뜻하지 않는다.

## 제품 목표

APS Server는 APS Vault를 통합 관리하는 백엔드 API다. AI 서비스 없이도 Vault 연결·동기화, 문서 조회, Inbox 축적, 가벼운 유사 문서 검색을 제공한다. AI 사서는 선택적으로 연결하며 기본 실행의 필수 의존성이 아니다.

한 서버는 한 사용자와 한 Vault를 담당한다. Project·Service 원본은 APS Vault가, API·인증·작업 실행·파생 결과는 APS Server가 소유한다. aps-index의 선택적 DB 원본 모드만 Inbox/Idea 소유권을 별도 계약에 따라 이전한다.

## 목표 베타 빌드

### 1. APS Vault 확장 API

인증된 사용자는 일반 조회 요청과 제한된 JSON 또는 `text/plain` POST 요청으로 Inbox 접수, Idea 검색, Project·Service 조회, 허용된 archive 다운로드를 수행한다. 구조화 요청은 JSON을 기본으로 하며 text 요청은 **Inbox 접수처럼 대상과 의미가 고정된 endpoint**에서만 허용한다. 자연어 본문을 자유 형식 agent 지시나 Vault 경로로 해석하지 않는다. text 접수의 길이·문자셋·제목/요약 변환·중복 요청·응답 schema는 API 계약으로 확정한다.

조회 JSON은 안정된 envelope와 정규화된 metadata, 논리 ID, 원본 revision, 필요한 경우 Markdown 본문을 포함한다. 원문 Markdown은 검증된 고정 문서만 제공하며 요청자가 경로를 지정하지 않는다. HTML은 서버에 미리 등록된 template이 **같은 검증된 JSON**을 렌더링한다. JSON과 HTML의 권한·필터·revision은 같고 조회는 AI·동기화·생성 Job을 시작하지 않는다. 브라우저 렌더링 시 Markdown/HTML을 안전하게 처리한다. 전체 Vault archive는 일반 문서 조회가 아니라 백업 확장의 권한·만료·용량 제한을 받는 Artifact다. [API 계약](CONTENT_API.md)과 [백업 확장](../plugins/backup-migration/README.md)을 따른다.

### 2. 선택 AI 큐와 Vault 사서

Core API는 AI 큐의 연결 여부와 관계없이 동작한다. 등록된 일반 AgentExecutor와 내부 cron 또는 별도 AI 스케줄러/큐 서비스가 **같은 고정 operation 계약**을 사용한다. 외부 서비스는 접수·상태·취소·결과의 비동기 계약을 구현하며, APS Server가 최종 결과의 schema·기준 Vault revision·쓰기 권한을 검증한다. 외부 worker에 Vault/Git 직접 쓰기 권한을 주지 않는다.

사서는 Inbox 정규화와 Idea 승격, 중복 후보 정리, Idea Set 구성, 제한된 Project 제안, Service 운영 현황 파생 결과를 제공한다. Idea/Set의 tracked 변경은 검증된 Scheduler commit 경계만 사용한다. Project 제안은 proposal artifact까지 제공하며 원본 반영은 proposal branch·diff·명시적 승인 흐름이 갖춰지기 전까지 막는다. AI가 없거나 큐가 실패하면 사서 생성 operation만 비활성/실패로 표시하고 기존 정상 Content와 기본 조회를 유지한다. AI 의존 플러그인은 자신의 생성 기능만 비활성화한다. [실행 설계](AGENT_EXECUTOR_DESIGN.md)를 따른다.

### 3. 공식 확장 플러그인

베타 목표는 `briefing`, `migration`, `service-security` 세 공식 확장이다. 각 기능의 범위, 개발 순서, 권한·AI 의존성 및 완료 조건은 [공식 확장 기획·개발 계획](EXTENSION_PLAN.md)에서 관리한다. 일반 문서 API는 플러그인 설치를 요구하지 않는다.

### 4. 대규모 aps-index 서비스

별도 서비스가 대량 Idea의 색인, 유사 후보와 Set 후보 탐색을 맡을 수 있다. 첫 단계는 Vault 원본을 유지한 검색 backend 교체다. 선택적인 DB 원본 모드는 Inbox/Idea 원문·metadata·변경 이력의 소유권을 외부 DB로 옮기는 별도 전환으로, Markdown export·백업·이관 검증·복귀 경로가 갖춰진 경우에만 허용한다. Project/Service 원본은 Vault에 남는다. 검색 서비스 장애는 Vault 원본 모드에서 Core 로컬 검색으로 대체하며, DB 원본 모드에서는 없는 데이터를 정상 fallback으로 가장하지 않는다. [aps-index 설계](../plugins/aps-index/README.md)를 따른다.

## 기본 기능

| 영역 | AI 서비스 없음 (`none`) | AI 서비스 연결 시 |
|---|---|---|
| Vault | local/git/mounted 연결, 상태 점검, 안전한 동기화 | 동일 |
| 문서 API | Idea·Idea Set·Project·Service 목록·상세 및 허용된 Markdown 본문 | 동일 |
| Inbox | 고정 `00_Inbox`에 단순 축적·조회, 자동 Idea 정리 없음 | 검증된 정규화·중복 정리·Set 구성 |
| 검색 | 제목·키워드·요약 중심 lexical 검색과 내장 소형 임베딩 | 사서 작업 후보 탐색에 재사용 |
| Project | 원문·상태 조회, 자동 정리·제안 없음 | 정리·제안 생성, 원본 반영에는 승인 경계 적용 |
| 실행 | 비AI 작업용 내부 cron과 Job queue | 내부 cron 또는 외부 AI 큐/스케줄러 서비스로 사서 작업 실행 |
| 결과 | 검증된 JSON 및 같은 결과의 HTML | 생성 결과도 검증 후 게시, 실패 시 이전 결과 보존 |

`AI 서비스 없음`은 생성형 AI provider/외부 AI 실행 서비스가 없다는 뜻이다. 소형 임베딩은 CPU에서 실행하는 Core 검색 구성요소이며 외부 AI API·GPU·Vector DB를 요구하지 않는다. 대화형 질의응답·대규모 RAG는 기본 검색 범위에서 제외한다.

기본 문서 조회는 briefing 생성과 독립적이다. Content GET은 AI·동기화·생성 Job을 시작하지 않는다. Inbox 즉시 조회는 기존 overlay 방식을 사용할 수 있다.

선택 AI 사서와 내부 cron/외부 AI 큐 지원까지 기본 제품 범위다. 다만 설치 기본값은 `none`이며 AI가 없으면 사서 작업을 실행하지 않는다.

## 선택 기능 문서

공식 확장 세 가지는 [확장 계획](EXTENSION_PLAN.md), 독립 서비스 `aps-index`는 [서비스 설계](../plugins/aps-index/README.md), 베타 필수 조건이 아닌 웹훅은 [후속 설계](../plugins/webhooks/README.md)를 따른다. `plugins/`의 설계 문서는 설치 가능한 package 목록을 뜻하지 않는다.

## 유지할 경계

- 기존 API를 일방적으로 제거하거나 응답 의미를 교체하지 않는다. Core 문서와 briefing 결과 분리에는 호환 계약을 정의한다.
- 임의 Vault 경로·shell·실행 파일·Codex 인자·자유 형식 agent query를 요청받지 않는다.
- Inbox 쓰기는 서버가 관리하는 Git-ignored `00_Inbox`에 한정한다. 자동 tracked Idea 쓰기는 검증된 `01_Ideas`/`01_Idea_Sets` 대상의 Scheduler commit 흐름으로 제한한다.
- 기존 tracked Idea 직접 수정 API는 권한을 확대하지 않고 저장소 지침과 계약의 정합성을 정리한다.
- Project·Service 원본 쓰기는 proposal branch·diff·명시적 승인 흐름이 준비되기 전까지 비활성이다. 제안 생성과 원본 반영을 구분한다.
- Vault 동기화는 fast-forward only다. 자동 merge/reset/강제 checkout/force push를 추가하지 않는다.
- in-process queue를 사용하는 동안 web process는 하나다. 외부 AI 큐 도입만으로 다중 web process를 허용하지 않는다.

## 완료 판단

기존 MVP 완료 표시는 새 목표의 완료를 의미하지 않는다. [001~005 개선 작업](../tasks/001-none-mode-capabilities.md)으로 Core와 내장 검색을 완성한 다음, 선택 AI 실행, 세 공식 확장, aps-index의 검색 모드와 선택적 DB 원본 모드를 각각 검증한다. 베타 완료 판단은 이 네 영역의 계약·구현·운영 확인을 모두 요구한다. 웹훅은 별도 후속 설계이며 이 베타의 필수 조건은 아니다.
