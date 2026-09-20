# 전체 Vault 백업·마이그레이션 확장

상태: 설계 단계. 기존 Git 동기화는 전체 백업이 아니다.

## 목적과 범위

Vault 전체를 백업하고 새 서버·저장 위치로 복원/이전한다. 추적 Markdown뿐 아니라 Git-ignored `00_Inbox`, 첨부 파일과 ProjectContext를 포함한다. Git 이력·ignored 로컬 설정·민감 정보의 포함 여부는 백업 profile에 명시한다. 서버 token·AI credential은 Vault 데이터와 분리한다.

복원·이전은 별도 관리 작업이며 운영자가 사전에 등록한 대상 ID만 사용한다. 베타의 archive 다운로드는 인증된 operator가 만료·크기·보존 정책이 적용된 Artifact를 받는 흐름이다. 업로드는 신규 Vault 시작을 위한 staging 영역에만 받으며, 무결성 검사 전에는 사용하지 않는다. 기존 Vault 덮어쓰기는 별도 diff·복구 지점·명시적 승인 흐름 전까지 활성화하지 않는다. 요청자가 임의 경로·shell·Git 옵션을 넘기거나 Core 일반 문서 쓰기 권한을 확대하지 않는다.

archive의 허용 형식, 파일 수·총 크기·압축 해제 한도, symlink/경로 탈출·중첩 archive 처리, 민감 정보 포함 profile, 암호화와 키 보관을 계약으로 고정한다. 업로드/다운로드 endpoint의 이름과 요청 schema는 구현 전에 별도로 확정하며, 일반 Content endpoint로 archive를 반환하지 않는다.

## 작업

- [ ] **BACKUP-01** — 전체 파일 inventory·manifest/schema/version/checksum, 포함/제외 정책과 암호화·키 보관 방식 정의.
- [ ] **BACKUP-02** — Inbox 접수·사서 commit과 충돌하지 않는 일관된 snapshot, 임시 archive·완료 후 원자적 게시 구현.
- [ ] **BACKUP-03** — 등록 저장소의 예약/수동 백업·보존 기간·용량·실패 상태·다운로드 권한 정의.
- [ ] **BACKUP-04** — archive 경로 탈출·symlink·손상·용량 검증 후 staging 복원. 기존 Vault 덮어쓰기 전 대상·diff/충돌·복구 지점을 제시하고 명시적으로 승인받는 흐름 구현.
- [ ] **BACKUP-05** — 버전/schema 변환·새 환경 경로 재연결·전환 중 쓰기 제어·복귀 절차 구현. 자동 reset/강제 checkout/force push 금지.
- [ ] **BACKUP-06** — 원본/복원본 파일 수·hash·Inbox·첨부·참조 대조 및 파생 색인 재구축. aps-index DB 원본 모드에는 해당 원문 저장소의 일관된 export 포함.

완료 조건: Git에 없는 Inbox까지 복원 가능하고 실패한 복원/이전이 기존 Vault를 훼손하지 않는다. 백업 자료에서 복원 범위와 제외 항목을 확인할 수 있다.

선행: snapshot/작업 잠금·고정 관리 대상 계약. AI와 `.brief`는 필요하지 않다.
