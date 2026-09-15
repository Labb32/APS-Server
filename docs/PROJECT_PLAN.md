# APS Server 목표와 개발 범위

기준일: 2026-09-15. 기존 AI·브리핑 중심 MVP 계획을 대체한다. 현재 구현과 남은 작업은 [TASKS](TASKS.md), 선택 기능은 [plugins](../plugins/README.md)에서 관리한다.

## 제품 목표

APS Server는 APS Vault를 통합 관리하는 백엔드 API다. AI 서비스 없이도 Vault 연결·동기화, 문서 조회, Inbox 축적, 가벼운 유사 문서 검색을 제공한다. AI 사서는 선택적으로 연결하며 기본 실행의 필수 의존성이 아니다.

한 서버는 한 사용자와 한 Vault를 담당한다. Project·Service 원본은 APS Vault가, API·인증·작업 실행·파생 결과는 APS Server가 소유한다.

## 기본 기능

| 영역 | AI 서비스 없음 (`none`) | AI 서비스 연결 시 |
|---|---|---|
| Vault | local/git/mounted 연결, 상태 점검, 안전한 동기화 | 동일 |
| 문서 API | 기존 Idea·Idea Set·Project·Service 목록 및 상세 | 동일 |
| Inbox | 고정 `00_Inbox`에 단순 축적·조회, 자동 Idea 정리 없음 | 검증된 정규화·중복 정리·Set 구성 |
| 검색 | 제목·키워드·요약 중심 lexical 검색과 내장 소형 임베딩 | 사서 작업 후보 탐색에 재사용 |
| Project | 원문·상태 조회, 자동 정리·제안 없음 | 정리·제안 생성, 원본 반영에는 승인 경계 적용 |
| 실행 | 비AI 작업용 내부 cron과 Job queue | 내부 cron 또는 외부 AI 큐 서비스로 사서 작업 실행 |
| 결과 | 검증된 JSON 및 같은 결과의 HTML | 생성 결과도 검증 후 게시, 실패 시 이전 결과 보존 |

`AI 서비스 없음`은 생성형 AI provider/외부 AI 실행 서비스가 없다는 뜻이다. 소형 임베딩은 CPU에서 실행하는 Core 검색 구성요소이며 외부 AI API·GPU·Vector DB를 요구하지 않는다. 대화형 질의응답·대규모 RAG는 기본 검색 범위에서 제외한다.

기본 문서 조회는 briefing 생성과 독립적이다. Content GET은 AI·동기화·생성 Job을 시작하지 않는다. Inbox 즉시 조회는 기존 overlay 방식을 사용할 수 있다.

선택 AI 사서와 내부 cron/외부 AI 큐 지원까지 기본 제품 범위다. 다만 설치 기본값은 `none`이며 AI가 없으면 사서 작업을 실행하지 않는다.

## 선택 기능

| 기능 | 구분 | 상세 문서 |
|---|---|---|
| `.brief` | 진행 중 Project·운영 Service briefing 확장 | [brief](../plugins/brief/README.md) |
| `aps-index` | Inbox/Idea를 대규모 RAG·Vector DB 기반으로 대체하는 추가 서비스 | [aps-index](../plugins/aps-index/README.md) |
| 전체 Vault 백업·마이그레이션 | 보존·복원·이전 확장 | [backup-migration](../plugins/backup-migration/README.md) |
| 웹훅 연동 | 등록 조건에 따른 Discord·메일 API 요청/응답·전달 확장 | [webhooks](../plugins/webhooks/README.md) |

`plugins/`는 현재 설계 문서 격리 위치다. 실행 패키지 `extensions/briefing`이나 installer 경로를 이동하거나 새 설치 명령을 제공하는 것은 아니다.

## 유지할 경계

- 기존 API를 일방적으로 제거하거나 응답 의미를 교체하지 않는다. Core 문서와 briefing 결과 분리에는 호환 계약을 정의한다.
- 임의 Vault 경로·shell·실행 파일·Codex 인자·자유 형식 agent query를 요청받지 않는다.
- Inbox 쓰기는 서버가 관리하는 Git-ignored `00_Inbox`에 한정한다. 자동 tracked Idea 쓰기는 검증된 `01_Ideas`/`01_Idea_Sets` 대상의 Scheduler commit 흐름으로 제한한다.
- 기존 tracked Idea 직접 수정 API는 권한을 확대하지 않고 저장소 지침과 계약의 정합성을 정리한다.
- Project·Service 원본 쓰기는 proposal branch·diff·명시적 승인 흐름이 준비되기 전까지 비활성이다. 제안 생성과 원본 반영을 구분한다.
- Vault 동기화는 fast-forward only다. 자동 merge/reset/강제 checkout/force push를 추가하지 않는다.
- in-process queue를 사용하는 동안 web process는 하나다. 외부 AI 큐 도입만으로 다중 web process를 허용하지 않는다.

## 완료 판단

기존 MVP 완료 표시는 새 목표의 완료를 의미하지 않는다. AI·확장·추가 서비스 없이 기본 API와 내장 검색을 완성하고, 선택 AI 사서의 내부/외부 실행 경계를 구현한다. 네 선택 기능은 Core 완료 조건과 분리해 진행한다.
