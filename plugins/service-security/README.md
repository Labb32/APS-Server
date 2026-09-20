# service-security 공식 확장

상태: 목표 설계. 현재 설치 가능한 공식 package나 공개 endpoint가 아니다.

## 목적과 범위

운영 중인 Service에 대해 최신 이슈·취약점·업데이트 정보를 승인된 외부 정보원에서 조사하고, 근거가 있는 report와 alert 상태를 파생 결과로 제공한다. Service 원본 Markdown을 수정하거나 배포 명령을 실행하지 않는다. Core Service 조회와 운영 현황 API는 이 확장이나 AI 연결을 요구하지 않는다.

## 입력·출력 계약

- 대상은 Core가 식별한 `service_status: Active` Service와 필요한 기술·버전 metadata로 제한한다. 식별 정보가 부족하면 추측하지 않고 `insufficient_data`로 표시한다.
- AI 큐 또는 내부 AgentExecutor가 고정 task를 실행한다. 외부 정보 조회는 운영자가 등록·허용한 출처와 제한된 network broker를 통해서만 수행한다. 요청자가 URL, 명령, provider나 prompt를 전달하지 않는다.
- report는 service ID, 기준 Vault revision, 조사 시각, 출처 URL·게시 시각, 영향받는 제품/버전, 심각도, 불확실성, 권장 확인 사항과 만료/재검토 시각을 검증된 JSON으로 게시한다. HTML은 고정 template이 같은 JSON을 표시한다.
- alert는 확인 가능한 근거와 영향 조건을 충족한 항목만 생성한다. 중복 식별자, 상태 전이, 해제/만료, 통지 실패와 이전 정상 결과 보존 규칙을 정의한다. `alert`는 API 내 상태이며 외부 발송은 별도 알림 기능의 승인된 경계를 사용한다.
- 원격 출처의 내용과 AI 출력은 신뢰하지 않는 입력이다. 출처가 오래됐거나 조회에 실패하면 최신 정보로 표시하지 않고 report의 시각·오류·stale 상태를 드러낸다.

## 작업

- [ ] **SEC-01** — Service 식별 metadata와 대상 필터, 부족한 정보의 오류 계약 정의.
- [ ] **SEC-02** — 고정 출처 registry, 제한된 network broker, 조회 한도·캐시·출처 검증 구현.
- [ ] **SEC-03** — AI 조사 task와 근거 대조, JSON schema, HTML template, source freshness 계약 구현.
- [ ] **SEC-04** — alert의 생성·중복 제거·상태·만료·감사 및 외부 알림 연동 경계 정의.
- [ ] **SEC-05** — AI/네트워크 장애 시 Core API 독립성과 이전 정상 report 보존 확인.

완료 조건: 운영 Service에 근거·시각이 명시된 report/alert를 제공하고, AI·네트워크·확장 미연결 상태에서도 Core 문서 API가 정상 동작한다. 외부 통지나 원본 변경은 별도 승인된 기능 없이는 발생하지 않는다.

선행: Core Service API, 선택 AI 큐 계약, 공식 확장의 제한된 network capability. 네트워크·secret 경계는 [보안 정책](../../SECURITY.md)을 따른다.
