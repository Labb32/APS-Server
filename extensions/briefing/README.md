# Briefing Extension

Project와 Service 문서로 JSON briefing을 만들고 HTML 조회를 제공하는 공식 extension이다. AI 설정이 필요하다.

## 설치

```bash
docker compose exec aps-server aps extensions install briefing
docker compose restart aps-server
```

설치 상태는 `GET /v1/extensions`에서 확인한다.

## 제공 기능

- 전체 일일 briefing
- Project별 briefing
- Service 유지보수 현황

Vault 원본을 수정하거나 Git command를 실행하지 않는다. AI 설정은 [선택형 AI](../../docs/AI_EXECUTION.md)를 참고한다.
