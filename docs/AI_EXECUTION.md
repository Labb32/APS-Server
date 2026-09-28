# 선택형 AI

AI는 기본으로 꺼져 있다. AI 없이 조회, 검색, Inbox 접수와 일반 Job을 사용할 수 있다.

## 설정

OpenAI:

```dotenv
APS_AI_PROVIDER=openai
APS_AI_MODEL=<model>
APS_AI_API_KEY=<secret>
```

OpenAI 호환 API:

```dotenv
APS_AI_PROVIDER=openai-compatible
APS_AI_BASE_URL=https://provider.example/v1
APS_AI_MODEL=<model>
APS_AI_API_KEY=<secret>
```

APS Agent HTTP 계약:

```dotenv
APS_AI_PROVIDER=agent-http
APS_AI_BASE_URL=https://agent.example
APS_AI_API_KEY=<secret>
```

`idea-curate` schedule은 기본 비활성이다. `/config/schedule-overrides.json`에서 켠다.

```json
{
  "version": 1,
  "overrides": [
    {"schedule_id": "idea-curate", "enabled": true}
  ]
}
```

재시작 후 `GET /v1/operations`와 `GET /v1/scheduler`에서 상태를 확인한다.

AI는 구조화된 계획만 반환하며 Core가 ID, 대상과 Vault 상태를 검증하고 commit한다. 실패하거나 보류된 Inbox 원문은 유지된다. API 요청으로 prompt, model, 도구 또는 Vault 경로를 지정할 수 없다.

credential은 환경 변수나 secret mount에만 저장한다.
