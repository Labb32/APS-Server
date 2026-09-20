# 공식 확장 플러그인 기획·개발 계획

상태: 목표 베타 설계. 이 문서의 작업 항목은 완료를 뜻하지 않는다. Core 제품 범위와 순서는 [제품 목표](PROJECT_PLAN.md), 확장별 상세 계약은 [플러그인 문서](../plugins/README.md)를 따른다. `aps-index`는 독립 서비스이므로 이 문서의 확장 구현 범위에서 제외한다.

## 목표와 공통 계약

베타는 `briefing`, `migration`, `service-security` 세 공식 확장을 제공한다. 확장을 설치하지 않아도 Vault 문서 조회, Inbox 접수, Core 검색과 기본 Job API가 동작한다. 확장은 Core의 인증·operation allowlist·입력 schema·Job 상태·결과 검증·감사를 사용하며 임의 route, shell, Vault 경로 또는 provider 선택을 공개 API에 추가하지 않는다.

| 확장 | 주요 기능 | 의존성 | 현재 상태 |
|---|---|---|---|
| `briefing` | 운영 중 Project·Service 분석, 검증된 브리핑 JSON과 고정 HTML | 선택 AI 실행 경계 | `briefing` package 존재, 목표 범위로 전환 필요 |
| `migration` | Vault snapshot archive 생성·제한 다운로드, 업로드 검증 후 새 Vault 시작 | 제한된 archive·staging 관리 capability | 설계 단계 |
| `service-security` | 운영 Service의 최신 이슈·취약점 report와 alert | 선택 AI 실행 경계, 승인된 출처만 조회하는 network capability | 설계 단계 |

확장별 의존성이 없으면 해당 생성·관리 operation만 비활성으로 표시한다. Core readiness와 기본 조회를 막지 않고, 게시된 이전 정상 결과에는 생성 시각·기준 revision·stale 상태를 표시한다. AI 또는 확장이 만든 HTML을 게시하지 않는다. 서버에 사전 등록한 template이 같은 canonical JSON을 렌더링한다.

## 공통 개발 작업

1. **EXT-01: 등록·가용성 계약.** manifest에 확장 ID/version, APS 호환 버전, 고정 operation·schedule, 필요한 `ai`·`archive`·`network` capability를 선언한다. 설치/미설치/비활성/의존성 장애의 응답과 `/v1/extensions` 상태를 구분한다.
2. **EXT-02: 생명주기.** 공식 package의 무결성, 설치·활성화·비활성화·업데이트·제거 시 operation/schedule과 기존 결과의 처리, 재시작 요구를 확정한다. 현행 `briefing` ID·설치 데이터·API 호환을 유지하며 전환한다. 임의 URL 설치와 hot loading은 추가하지 않는다.
3. **EXT-03: 실행·결과 경계.** 내부 cron과 외부 AI 큐가 같은 고정 operation 입력/결과 schema를 사용한다. Core가 기준 Vault revision, 결과 checksum, 게시 위치와 부작용을 검증한 뒤 원자적으로 게시한다. 실패하면 이전 정상 결과를 보존한다.
4. **EXT-04: 특수 권한 분리.** 현행 read-only content-provider host에 archive 복원이나 임의 네트워크 권한을 부여하지 않는다. `migration`은 Core가 통제하는 staging/Artifact 관리 작업으로, `service-security`는 등록 출처만 허용하는 network broker로 구현한다. 권한·자원 한도·감사 기록을 각 operation에 묶는다.
5. **EXT-05: API·문서 정합성.** 활성 route와 계획 route, JSON/HTML·Artifact 응답, 역할별 권한, 오류 코드, 예제를 구현 상태와 일치시킨다. 플러그인 설치 없이 Core API를 직접 호출해 독립성을 확인한다.

## 확장별 개발 순서

### briefing

1. 일반 Project/Service 조회를 briefing 결과와 분리한다. 대상은 현재 Vault 표기 `status: In_Progress` Project와 `service_status: Active` Service로 제한한다. 일일·대상별 생성에 같은 필터를 사용한다.
2. 기존 `briefing.daily`, `briefing.project`, `service.maintenance_due`를 유지하면서 운영 Service briefing의 별도 입력·출력 계약을 정한다. 유지보수 기한 결과를 완성된 Service briefing으로 간주하지 않는다.
3. 기준 revision·생성 시각·대상 ID·근거·stale을 포함한 JSON을 검증하고 고정 HTML template으로 표시한다. AI가 없으면 새 생성은 비활성으로 표시한다.

세부 작업과 완료 조건: [briefing 설계](../plugins/brief/README.md)의 BRIEF-01~06.

### migration

1. Vault 전체 inventory와 archive manifest·schema·checksum, 포함/제외 profile, 암호화·키 보관 방식을 확정한다. Git-ignored `00_Inbox`, 첨부 파일, ProjectContext를 포함할 수 있어야 하며 서버 token·AI credential은 분리한다.
2. Inbox 쓰기·사서 commit과 충돌하지 않는 일관된 snapshot을 만들고, 원자적으로 게시된 archive만 operator가 만료·용량·보존 제한 아래 다운로드한다.
3. 업로드 archive는 파일 수·총 크기·압축 해제 한도·경로 탈출·symlink·손상·checksum을 확인한 후 staging에만 푼다. 사전 등록된 새 Vault 대상에서 시작하며, 실패 시 기존 Vault는 그대로 둔다.
4. 기존 Vault 덮어쓰기나 이전은 대상·diff/충돌·복구 지점과 명시적 승인 흐름이 준비된 뒤 별도로 활성화한다. 원본/복원본 파일 수·hash·참조를 대조하고 파생 색인을 재구축한다. aps-index DB 원본 모드의 백업 범위도 연계한다.

세부 작업과 완료 조건: [migration 설계](../plugins/backup-migration/README.md)의 BACKUP-01~06.

### service-security

1. 운영 Service의 제품·버전 식별 정보를 정규화하고, 정보가 부족하면 추측하지 않고 부족 상태를 반환한다.
2. 운영자가 등록한 출처만 조회하는 network broker를 구현한다. 요청자가 URL·prompt·provider를 고르지 못하며 출처 시각·조회 실패·캐시 상태를 보존한다.
3. AI 조사 결과에 service ID, 기준 revision, 출처 URL·게시 시각, 영향 버전, 심각도, 불확실성, 재검토 시각을 요구한다. Core가 근거와 schema를 검증해 JSON report를 게시하고 고정 HTML을 제공한다.
4. alert의 중복 식별·생성·해제·만료·감사를 정의한다. 외부 알림 발송은 별도 승인된 알림 기능을 통해서만 연결한다. Service 원본이나 배포 상태를 자동 변경하지 않는다.

세부 작업과 완료 조건: [service-security 설계](../plugins/service-security/README.md)의 SEC-01~05.

## 선행 조건과 완료 판단

- 공통 선행: [001 Core 가용성](../tasks/001-none-mode-capabilities.md), [002 일반 문서 API](../tasks/002-core-document-api.md), 선택 AI 큐의 고정 operation·결과 검증 계약.
- `briefing`: Project/Service 대상 상태와 JSON/HTML 호환 계약.
- `migration`: 일관된 snapshot·작업 잠금, 제한된 Artifact/업로드·staging·새 Vault 대상 계약. AI는 필요하지 않다.
- `service-security`: Service 식별 metadata, 제한 network broker와 AI 실행 계약.

완료는 세 확장의 계약·구현·권한·서비스 흐름을 각각 확인하고, 미설치·AI/네트워크 장애 시 Core 독립성을 확인한 뒤 판단한다. 문서 작성만으로 완료 표시하지 않는다. 별도 사용자 요청 없이 테스트 파일·케이스를 생성하거나 테스트 명령을 실행하지 않는다.
