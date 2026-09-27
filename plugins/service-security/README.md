# Service Security 설계

운영 중 Service의 최신 이슈와 취약점을 승인된 출처에서 조사해 report와 alert를 만드는 공식 확장 구상이다. 현재 설치 가능한 기능은 아니다.

- Service 원본을 수정하거나 배포 명령을 실행하지 않는다.
- 운영자가 등록한 출처만 제한된 network broker로 조회한다.
- 결과에는 Service ID, 조사 시각, 출처, 영향 버전, 심각도와 불확실성을 포함한다.
- 근거가 부족하면 `insufficient_data` 또는 stale 상태로 표시한다.
- AI·네트워크 장애가 Core Service API를 중단시키지 않는다.

네트워크와 secret 경계는 [보안 정책](../../SECURITY.md)을 따른다.
