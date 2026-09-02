# AI provider configuration

APS Server는 AI 호출을 Core `AIGateway`에서 정규화한다. 공식 `briefing` 확장은 고정 bridge만 호출하며 provider, endpoint, model, credential을 선택하지 않는다. HTTP API 요청과 Schedule에도 이 설정을 넣을 수 없다.

## 지원 provider

| `APS_AI_PROVIDER` | 용도 | 필수 설정 |
|---|---|---|
| `codex` | 별도 Codex runtime image의 Codex CLI 사용 | `/codex-home` 인증 |
| `openai-compatible` | vLLM, OpenAI 호환 chat completions API | `APS_AI_BASE_URL`, `APS_AI_MODEL` |
| `agent-http` | 별도 AI Agent 서비스의 APS JSON 계약 | `APS_AI_BASE_URL` |

기본 provider는 없다. 설치 시 `codex`, `openai-compatible`, `agent-http` 중 하나를 `.env` 또는 `APS_CONFIG_FILE`에 반드시 지정한다. provider가 선택되지 않았거나 필수 설정이 빠지면 container bootstrap이 실패한다. 직접 Uvicorn을 실행하는 개발 환경에서도 선택한 provider가 준비되지 않으면 Core-only 상태의 readiness가 실패한다. API 요청자와 extension은 provider를 변경할 수 없다.

공통 제한:

```dotenv
APS_AI_TIMEOUT_SECONDS=600
APS_AI_PARALLEL_REQUESTS=3
APS_AI_MAX_INPUT_CHARS=200000
```

- timeout은 10~7200초, 병렬 요청은 1~8개로 제한된다.
- provider 응답은 최대 2 MiB만 읽는다.
- 입력과 출력은 등록된 task schema로 검증한다.
- credential, 전체 prompt와 provider 원문은 Job 결과나 일반 오류에 넣지 않는다.

## Codex

```dotenv
APS_AI_PROVIDER=codex
APS_CODEX_HOME_MOUNT=aps-codex-home
```

Core가 `codex exec --ephemeral --sandbox read-only`와 고정 JSON Schema를 사용한다. API나 확장은 executable 또는 Codex argument를 바꿀 수 없다.

기본 `Dockerfile` image에는 Node.js와 Codex CLI가 포함되지 않는다. Codex를 사용할 때만 Core image를 먼저 만든 뒤 `Dockerfile.codex`와 `compose.codex.yaml`로 파생 runtime을 빌드한다.

```bash
docker compose build aps-server
docker compose -f compose.yaml -f compose.codex.yaml build aps-server
docker compose -f compose.yaml -f compose.codex.yaml up -d
```

두 번째 image에만 Node.js, Codex CLI와 `/codex-home` volume이 추가된다. `openai-compatible`과 `agent-http`는 기본 image를 그대로 사용한다.

## vLLM과 OpenAI 호환 API

```dotenv
APS_AI_PROVIDER=openai-compatible
APS_AI_BASE_URL=http://vllm:8000/v1
APS_AI_MODEL=Qwen/Qwen3-8B
# APS_AI_API_KEY=internal-secret
APS_AI_STRUCTURED_OUTPUT=true
```

Core는 base URL 뒤의 `/chat/completions`에 요청한다. base URL 자체가 이미 `chat/completions`로 끝나면 그대로 사용한다. 요청에는 고정 system message, Vault에서 만든 prompt, `temperature: 0`과 JSON Schema response format이 들어간다.

서버가 `response_format.type=json_schema`를 지원하지 않으면 다음처럼 schema를 system message에 포함하는 호환 모드를 사용할 수 있다.

```dotenv
APS_AI_STRUCTURED_OUTPUT=false
```

두 모드 모두 최종 응답은 Core Pydantic model로 다시 검증되므로 JSON 형식만 맞는 임의 응답은 게시되지 않는다.

같은 Compose network에서 vLLM을 운영하는 예:

```yaml
services:
  aps-server:
    environment:
      APS_AI_PROVIDER: openai-compatible
      APS_AI_BASE_URL: http://vllm:8000/v1
      APS_AI_MODEL: Qwen/Qwen3-8B
  vllm:
    image: vllm/vllm-openai:stable
    expose:
      - "8000"
```

실제 image tag, GPU runtime과 model volume은 운영 환경에서 고정한다. AI service port는 외부에 공개하지 않는 것을 기본으로 한다.

## 별도 AI Agent 서비스

```dotenv
APS_AI_PROVIDER=agent-http
APS_AI_BASE_URL=http://ai-agent:8091/v1/tasks
# APS_AI_API_KEY=internal-secret
```

APS Server 요청:

```json
{
  "contract_version": 1,
  "task": "briefing",
  "input": "Core가 생성한 읽기 전용 prompt",
  "response_schema": {
    "type": "object"
  }
}
```

Agent 서비스 성공 응답:

```json
{
  "output": {
    "today_tasks": ["오늘 처리할 작업"],
    "notes": ["확인할 사항"]
  }
}
```

`output`은 반드시 object여야 하며 task별 Core schema 검증을 통과해야 한다. Agent endpoint는 설정 관리자가 정한 정확한 URL로만 호출되고 외부 API 요청자가 변경할 수 없다.

## Secret과 네트워크

- `APS_AI_API_KEY`는 Git에 저장하지 않고 env secret 또는 read-only 설정 mount로 전달한다.
- `APS_AI_BASE_URL`에 user/password를 포함할 수 없으며 인증은 `APS_AI_API_KEY`만 사용한다.
- 외부 provider에는 HTTPS를 사용하고 내부 provider는 격리된 container network를 사용한다.
- `health/ready`는 네트워크 호출 없이 provider 필수 설정과 Codex 실행 파일만 검사한다.
- provider 장애 시 생성 Job만 실패하거나 부분 실패하며 직전 정상 materialized Content는 유지된다.
