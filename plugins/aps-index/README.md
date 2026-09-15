# aps-index 추가 서비스

상태: 목표 설계. 현재 `APS_INDEX_URL`은 예약 설정이며 대규모 RAG/Vector DB adapter의 구현 완료를 뜻하지 않는다.

## 목적과 범위

Inbox/Idea의 저장·검색 처리를 대규모 RAG/Vector DB 기반으로 대체할 수 있는 별도 서비스다. 대용량 수집·색인·검색을 담당하며 Core 확장 subprocess 대신 독립 서비스로 배포한다.

검색 backend 교체와 Inbox/Idea 영속 저장 backend 교체를 구분한다. Vector index만으로 원문 저장을 대체하지 않는다. DB가 원본을 맡는 모드에는 durable 원문·metadata 저장, 변경 이력, Markdown export와 복귀 경로가 필요하다. 이는 현재 Vault 원본 원칙의 변경이므로 소유권·쓰기 계약을 명문화한 뒤 구현한다. Project·Service 원본은 계속 Vault 소유다.

## 작업

- [ ] **INDEX-01** — 내부 인증 API, collection/document ID·원문 revision·schema/model version·색인 상태 계약 정의.
- [ ] **INDEX-02** — Vault 원본을 유지하는 검색 backend와 Inbox/Idea 원본을 DB로 대체하는 저장 backend를 명시적 설정으로 구분.
- [ ] **INDEX-03** — 대규모 embedding·chunking·Vector DB·RAG retrieval 및 문서/인용 출처 반환 구현. 생성형 답변은 선택 AI와 별도 계약으로 처리.
- [ ] **INDEX-04** — 기존 Inbox/Idea API·사서 작업을 storage/search adapter에 연결. 외부 서비스에 임의 Vault 경로·Git 실행 권한을 부여하지 않음.
- [ ] **INDEX-05** — 초기 이관·증분 동기화·삭제·중복 방지·재색인·취소·재시작 복구. 원본 수/hash 대조 완료 전 기존 원본 제거 금지.
- [ ] **INDEX-06** — 장애·제거 정책 정의. Vault 원본 모드는 로컬 검색으로 대체하고 DB 원본 모드는 복제본 가용성에 따른 읽기/쓰기 제한을 명시. 없는 데이터로 정상 fallback을 가장하지 않음.
- [ ] **INDEX-07** — Compose 선택 구성·독립 volume·자원 예산·원문/DB 백업·Markdown export 및 복귀 절차 문서화.

완료 조건: 미연결 시 Core 검색이 동작하고 연결 시 기존 Inbox/Idea API 의미를 유지하며 대규모 backend를 사용한다. 원본 대체는 이관 검증·백업·export·복귀까지 준비되어야 완료다.

선행: Core 공통 검색/문서 ID·Inbox 계약. 백업 확장과 DB 원본 보존 범위를 연계한다. 기존 제목·키워드·요약 전용 외부 색인 설계는 대규모 RAG 계약 확정 시 갱신한다.
