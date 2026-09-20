# APS Server 선택 기능 문서

Core와 분리한 확장·추가 서비스의 상세 설계를 모은다. 현재 설계 문서만 포함하며 설치 가능한 패키지 목록이 아니다. 베타 공식 확장의 공통 기획·개발 순서와 완료 조건은 [확장 계획](../docs/EXTENSION_PLAN.md), 전체 제품 범위는 [PROJECT_PLAN](../docs/PROJECT_PLAN.md)을 따른다.

| 기능 | 종류 | 문서 | 현재 상태 |
|---|---|---|---|
| `briefing` (`.brief` 목표 명칭) | 공식 확장 | [brief](brief/README.md) | 기존 `extensions/briefing`에서 목표 범위로 전환 필요 |
| `aps-index` | 별도 배포 서비스 | [aps-index](aps-index/README.md) | 연결 설정 존재, adapter·서비스 계약 미구현 |
| `migration` | 공식 확장 목표 | [backup-migration](backup-migration/README.md) | archive 업로드·복원 경계 설계 단계 |
| `service-security` | 공식 확장 목표 | [service-security](service-security/README.md) | AI·제한 network capability 설계 단계 |
| 웹훅·Discord·메일 | 선택 확장 | [webhooks](webhooks/README.md) | 설계 단계 |

미설치 상태에서 Core가 독립 동작해야 한다. 기존 인증·고정 operation·입출력 검증·Vault 쓰기 경계를 재사용하고 선택 기능 장애가 Core 조회를 막지 않게 한다. 기존 package ID `briefing`이나 실행 경로는 별도 호환 전환 전까지 유지한다. `migration`의 업로드·복원과 `service-security`의 외부 조회는 현행 content-provider host 권한에 포함되지 않는다.

공통 작업:

- [ ] manifest의 AI·검색·외부 서비스 의존 capability와 호환 버전 정의.
- [ ] 설치·활성화·비활성화·업데이트·제거 시 operation/schedule/데이터 보존 정책 정의.
- [ ] 공식 package 무결성 확인·최소 권한 적용. 기존 content-provider host로 처리할 수 없는 백업/네트워크 기능은 별도 capability 설계.
- [ ] Core readiness와 선택 기능 상태 및 미설치/비활성 오류 계약 분리.

커뮤니티 패키지·hot loading·일반 shell 실행은 이번 목표에 포함하지 않는다. 제3자 확장의 공개 조건은 [보안 정책](../SECURITY.md)을 따른다.
