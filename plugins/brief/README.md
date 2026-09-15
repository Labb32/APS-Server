# .brief 확장

상태: 목표 설계. 현재 실행 코드는 [extensions/briefing](../../extensions/briefing/README.md)에 있으며 이번 단계에서는 이동하지 않는다.

## 목적과 범위

기본 서버에 설치해 진행 중 Project와 운영 중 Service에 한해 briefing을 생성한다. 일반 문서 목록·상세는 Core 소유이며 이 확장이나 생성 결과를 요구하지 않는다.

- Project는 현재 Vault 표기 `status: In_Progress`, Service는 `service_status: Active`를 대상으로 한다. 사용자 표현 `progress` 등 다른 표기는 명시적 정규화 규칙을 정의한 경우에만 수용한다.
- 일일 종합·대상별 생성 모두 같은 필터를 적용한다. 진행 전/완료 Project와 중지/종료 Service, 개인 일정은 제외한다.
- AI 생성은 Core의 선택 AI 실행 경계를 사용한다. AI가 없으면 생성은 비활성이며 이전 결과의 조회·stale·대상 상태 변경 정책을 정의한다.
- 파생 JSON/HTML을 게시하며 Project·Service 원본을 직접 수정하지 않는다.

## 작업

- [ ] **BRIEF-01** — daily/project/maintenance operation과 legacy materializer에서 일반 문서 기능을 분리.
- [ ] **BRIEF-02** — 대상 status 공통 필터를 cron·수동 요청에 적용하고 대상 제외/상태 변경 오류 정의.
- [ ] **BRIEF-03** — 운영 Service briefing의 입력·출력 schema 정의. 기존 `service.maintenance_due`를 완성된 Service briefing으로 간주하지 않음.
- [ ] **BRIEF-04** — `briefing_id`와 `.brief` ProjectContext가 일반 Project 조회의 필수 요건이 되지 않도록 템플릿·검증 분리.
- [ ] **BRIEF-05** — 내부 cron/외부 AI 결과 검증·게시 및 원본 revision·생성 시각·실패/stale 기록.
- [ ] **BRIEF-06** — package 이름/경로 호환 전환, 기존 API·설치 데이터·schedule 처리 및 비활성화 정책 확정.

완료 조건: 미설치 시 Core가 독립 동작하고 설치·AI 연결 시 대상 상태에 해당하는 문서만 briefing을 생성한다. 기존 JSON/HTML 계약과 이전 정상 결과 보존 원칙을 유지한다.

선행: CORE-01, CORE-02와 선택 AI 실행 계약. 외부 큐는 adapter가 준비된 경우에만 사용한다.
