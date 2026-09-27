# 선택형 AI 설정

AI는 선택 기능이다. 기본 `APS_AI_PROVIDER=none`에서 Core API와 검색을 모두 사용할 수 있다. provider·model·credential은 서버 설정으로만 관리하며 API 요청으로 바꿀 수 없다.

## 설정

### OpenAI

```dotenv
APS_AI_PROVIDER=openai
APS_AI_MODEL=<model>
APS_AI_API_KEY=<secret>
```

### OpenAI-compatible

```dotenv
APS_AI_PROVIDER=openai-compatible
APS_AI_BASE_URL=https://provider.example/v1
APS_AI_MODEL=<model>
APS_AI_API_KEY=<secret>
```

### Agent HTTP

```dotenv
APS_AI_PROVIDER=agent-http
APS_AI_BASE_URL=https://agent.example
APS_AI_MODEL=<model>
APS_AI_API_KEY=<secret>
```

공통 제한:

```dotenv
APS_AI_TIMEOUT_SECONDS=600
APS_AI_PARALLEL_REQUESTS=3
APS_AI_MAX_INPUT_CHARS=200000
APS_AI_STRUCTURED_OUTPUT=true
```

설정 변경 후 서버를 재시작하고 `GET /v1/operations`에서 AI operation의 `enabled` 상태를 확인한다.

## 실행 경계

- AI 작업은 고정 task, 입력 schema, 결과 schema와 제한된 읽기 Tool만 사용한다.
- provider는 Vault sync, Git commit이나 결과 게시를 직접 수행하지 않는다.
- 자유 형식 agent query, 요청자 지정 prompt·model·경로·Tool은 받지 않는다.
- 결과는 Core가 ID, schema와 기준 Vault revision을 검증한 뒤 사용한다.
- 실패하거나 시간이 초과되면 Inbox와 이전 정상 결과를 보존한다.

API key는 `.env` 또는 secret mount에만 두고 로그·Vault·image에 포함하지 않는다. 외부 provider를 사용할 때는 전송되는 Vault 문서 범위와 provider의 보관 정책을 운영자가 확인한다.
