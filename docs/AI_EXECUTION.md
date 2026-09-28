# 선택형 AI 설정

AI 기능은 기본으로 꺼져 있다. AI 없이 Core API, Inbox 접수, 조회와 검색을 사용할 수 있다.

## 활성화

provider를 설정한 뒤 필요한 schedule을 별도로 켠다.

```dotenv
APS_AI_PROVIDER=openai
APS_AI_MODEL=<model>
APS_AI_API_KEY=<secret>
```

OpenAI 호환 서비스는 `APS_AI_PROVIDER=openai-compatible`과 `APS_AI_BASE_URL`을, 외부 Agent HTTP 서비스는 `APS_AI_PROVIDER=agent-http`와 `APS_AI_BASE_URL`을 사용한다.

`idea-curate` schedule의 기본값은 `enabled: false`다. `deploy/config/schedule-overrides.json`에서 명시적으로 활성화한다.

```json
{
  "version": 1,
  "overrides": [
    {"schedule_id": "idea-curate", "enabled": true}
  ]
}
```

설정 변경 후 서버를 다시 시작하고 `GET /v1/operations`와 `GET /v1/scheduler`에서 상태를 확인한다.

내장 cron이 기본이다. 외부 Scheduler CLI를 선택해도 AI operation의 활성 조건과 결과 검증은 동일하며, 외부 Scheduler는 `aps schedule-run`으로 등록된 schedule만 실행한다.

## 실행 경계

- AI는 고정 task의 구조화된 계획만 반환한다.
- Core가 ID, 대상, 전체 pending 배정과 Vault 상태를 검증한다.
- Core만 tracked 문서를 쓰고 Git commit을 만든다.
- 실패하거나 보류된 Inbox 원문은 유지한다.
- API 요청으로 prompt, model, 도구, Vault 경로를 지정할 수 없다.

credential은 환경 변수나 secret mount에만 저장한다.
