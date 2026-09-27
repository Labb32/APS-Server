# Plugins

이 폴더는 Core와 분리된 확장·외부 서비스의 설계를 보관한다. 설치 가능한 공식 package는 `extensions/`에 있으며 현재 `briefing`만 제공한다.

| 문서 | 용도 |
|---|---|
| [brief](brief/README.md) | briefing 확장 설계 |
| [aps-index](aps-index/README.md) | 외부 대규모 검색 서비스 |
| [backup-migration](backup-migration/README.md) | Vault 백업·복원 |
| [service-security](service-security/README.md) | Service 보안 보고서 |
| [webhooks](webhooks/README.md) | 외부 알림 연동 |

설계 문서는 설치 가능 여부를 뜻하지 않는다. 공식 확장 목록은 `aps extensions list` 또는 `GET /v1/extensions`로 확인한다. 커뮤니티 package와 임의 원격 설치는 지원하지 않는다.
