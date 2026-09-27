# Backup·Migration 설계

Vault 전체를 archive로 백업하고 새 환경의 staging 영역에 복원하는 공식 확장 구상이다. 현재 설치 가능한 기능은 아니다.

- 추적 문서, Git-ignored Inbox, 첨부와 ProjectContext를 포함한다.
- token, AI key와 Git credential은 백업에서 제외한다.
- manifest, checksum, 파일 수·크기와 archive 경로를 검증한다.
- 복원은 기존 Vault를 바로 덮어쓰지 않고 staging에서 검사한다.
- 기존 Vault 교체에는 diff, 복구 지점과 명시적 승인이 필요하다.
- 요청자가 임의 경로, shell이나 Git 옵션을 전달할 수 없다.
