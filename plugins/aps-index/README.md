# aps-index 설계

`aps-index`는 대량 Idea 검색과 유사 후보 생성을 담당하는 별도 서비스 구상이다. 현재 `APS_INDEX_URL`은 예약 설정이며 adapter는 구현되지 않았다.

- 첫 단계는 Vault를 원본으로 유지하고 검색 backend만 교체한다.
- DB가 Idea 원본을 맡으려면 durable 저장, 이력, 백업, Markdown export와 Vault 복귀가 먼저 필요하다.
- 외부 서비스는 Vault 경로나 Git 실행 권한을 받지 않는다.
- 연결 장애 시 Vault 원본 모드는 로컬 검색을 사용한다. DB 원본 모드는 없는 데이터를 정상 fallback으로 표시하지 않는다.
- Project와 Service 원본은 계속 Vault에 둔다.
