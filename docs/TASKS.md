# 구현 현황과 다음 작업

문서 기준은 [목표 베타](PROJECT_PLAN.md)다. 이 목록은 저장소 코드 기준이며 배포 완료를 뜻하지 않는다. 활성 API의 세부 계약은 [API Reference](API_REFERENCE.md)에 있다.

## 완료된 Core 개선

| 단계 | 결과 |
|---|---|
| 001 — AI 선택화 | `none` 기본값, Core readiness 분리, AI operation 가용성 정책 |
| 002 — 문서 API | Idea·Idea Set·Project·Service 조회, JSON/고정 HTML, materialized 결과 |
| 003 — Inbox·Idea | 고정 Inbox 접수, pending 수정, 제한된 Scheduler 정리, tracked PATCH 차단 |
| 004 — 계약 정합성 | API·설정·배포 문서와 OpenAPI 동기화 |
| 005 — 공통 검색 | 5개 collection 검색, 로컬 색인·hybrid 점수·증분 갱신·fallback |

`POST /v1/search`는 AI provider와 `aps-index` 없이 동작한다. 검색 한도와 품질 범위는 [Core 검색](SEARCH.md)을 따른다. 변경의 통합 이력은 [개발 노트](DEVELOPMENT_NOTES.md)에 있다.

## 다음 우선순위

### AI 사서와 실행

- 내부 cron을 통한 Inbox 정리, 중복 후보, Idea Set 구성
- 외부 AI queue의 제출·상태·취소·결과 계약
- 제한된 Project 제안과 Service 현황 결과
- 결과 schema와 기준 Vault revision 검증, 재시도·중복·늦은 결과 처리

AI 실행 경계와 provider 설정은 [AI 실행 문서](AI_EXECUTION.md)를 따른다.

### 공식 확장

- `briefing`: 운영 Project·Service 브리핑과 고정 HTML
- `migration`: 일관된 archive, 제한 다운로드, 안전한 새 Vault 복원
- `service-security`: 등록된 출처 기반 취약점 조사와 alert

공통 capability와 단계별 완료 조건은 [확장 계획](EXTENSION_PLAN.md)에 있다.

### aps-index

Vault 원본 검색 backend를 연결한 뒤, 별도 승인 단계로 Idea/Inbox DB 원본 모드를 설계한다. 이관, 백업, Markdown export와 복구 계약이 선행 조건이다. [aps-index 설계](../plugins/aps-index/README.md)를 따른다.

## 완료 확인

새 작업은 공개 계약, 역할별 권한, 외부 의존성 없이 Core가 동작하는지, 실패 시 이전 정상 데이터가 보존되는지를 확인한 뒤 완료로 표시한다. API·권한·서비스 흐름은 직접 실행해 확인한다. 저장소 지침에 따라 별도 요청 없이는 테스트 파일·케이스를 만들거나 테스트 명령을 실행하지 않는다.
