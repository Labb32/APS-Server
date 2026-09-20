# AI provider configuration

APS Server는 AI 호출을 Core `AgentExecutor`와 provider adapter에서 정규화한다. provider, endpoint, model과 credential은 서버 시작 설정이며 HTTP 요청자, Schedule과 확장이 변경할 수 없다.

## 지원 provider

| `APS_AI_PROVIDER` | 용도 | 필수 설정 |
|---|---|---|
| `none` | Core만 사용, AI 작업 비활성 | 없음 |
| `openai` | OpenAI Responses API | `APS_AI_API_KEY`, `APS_AI_MODEL` |
| `openai-compatible` | vLLM 등 Chat Completions 호환 API | `APS_AI_BASE_URL`, `APS_AI_MODEL` |
| `agent-http` | 별도 APS Agent 서비스 | `APS_AI_BASE_URL` |

기본값은 `APS_AI_PROVIDER=none`이다. AI 없이 Core API를 사용할 수 있다. AI provider를 선택했지만 필수 설정이 없거나 endpoint가 잘못되면 서버는 기동하고 AI operation만 `PROVIDER_NOT_CONFIGURED`로 비활성화한다.

기본 image는 Python Core만 포함하며 Node.js, Codex CLI와 provider SDK를 포함하지 않는다. HTTP 요청은 Python 표준 라이브러리로 전송한다.

공통 제한:

```dotenv
APS_AI_TIMEOUT_SECONDS=600
APS_AI_PARALLEL_REQUESTS=3
APS_AI_MAX_INPUT_CHARS=200000
APS_AI_STRUCTURED_OUTPUT=true
```

- timeout은 10~7200초, 병렬 요청은 1~8개로 제한된다.
- provider 응답은 최대 2 MiB만 읽는다.
- 입력과 출력은 등록된 task schema로 검증한다.
- credential, 전체 prompt와 provider 원문은 Job 결과나 일반 오류에 넣지 않는다.

## OpenAI Responses API

```dotenv
APS_AI_PROVIDER=openai
APS_AI_API_KEY=replace-with-openai-api-key
APS_AI_MODEL=replace-with-an-available-responses-model
APS_AI_STRUCTURED_OUTPUT=true
```

Core는 고정된 `https://api.openai.com/v1/responses` endpoint를 호출하고 task의 JSON Schema를 `text.format`으로 전달한다. 모델 ID는 운영자가 계정에서 사용할 수 있는 Responses API 모델로 고정한다. Codex 계열 API 모델을 선택해도 로컬 Codex CLI나 별도 runtime image를 사용하지 않는다.

OpenAI API key는 모델 호출을 인증할 뿐 Vault 접근이나 Tool 실행 권한을 제공하지 않는다. 문서 수집, Tool 허용 범위, 결과 검증과 쓰기는 APS AgentExecutor가 담당한다.

## OpenAI-compatible API

```dotenv
APS_AI_PROVIDER=openai-compatible
APS_AI_BASE_URL=http://vllm:8000/v1
APS_AI_MODEL=Qwen/Qwen3-8B
# APS_AI_API_KEY=internal-secret
APS_AI_STRUCTURED_OUTPUT=true
```

Core는 base URL 뒤의 `/chat/completions`를 호출한다. base URL이 이미 `chat/completions`로 끝나면 그대로 사용한다.

서버가 JSON Schema response format을 지원하지 않으면 다음 호환 모드를 사용할 수 있다.

```dotenv
APS_AI_STRUCTURED_OUTPUT=false
```

이 경우 schema를 system message에 포함하고 최종 결과를 동일한 Core Pydantic model로 다시 검증한다.

## 별도 Agent HTTP 서비스

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

Agent 서비스 응답:

```json
{
  "output": {
    "today_tasks": ["오늘 처리할 작업"],
    "notes": ["확인할 사항"]
  }
}
```

`output`은 object여야 하며 task별 Core schema 검증을 통과해야 한다. 외부 Agent가 자체 Tool을 실행하더라도 APS Vault 쓰기는 Core의 별도 승인 및 change-set 계약 없이 허용하지 않는다.

## AgentExecutor와 provider의 관계

provider adapter는 모델 호출만 담당한다. [AgentExecutor 설계](AGENT_EXECUTOR_DESIGN.md)의 workflow와 tool-loop는 provider 위에서 동작한다.

```text
OperationHandler
→ AgentExecutor
→ ModelProvider
→ 구조화 응답
→ ToolRegistry / ResultValidator
```

따라서 provider가 native function calling을 지원하지 않아도 workflow mode를 사용할 수 있다. tool-loop mode도 표준 `ToolAction | FinalAction` JSON 계약을 사용해 구현하고 native function calling은 adapter 최적화로만 취급한다.

현재 범용 Executor adapter는 OpenAI-compatible 서버의 native Tool API를 요구하지 않는다. 매 step마다 허용된 Tool schema와 실행 이력을 입력하고 다음 `ToolAction | FinalAction`을 구조화 JSON으로 생성하므로, JSON 지시를 따를 수 있는 일반 vLLM 모델도 같은 실행 경로를 사용한다. Tool 자체는 APS Core에서만 실행된다.

## Secret과 네트워크

- `APS_AI_API_KEY`는 Git에 저장하지 않고 env secret 또는 read-only 설정 mount로 전달한다.
- `APS_AI_BASE_URL`에 user/password를 포함할 수 없으며 인증은 `APS_AI_API_KEY`만 사용한다.
- OpenAI provider는 HTTPS 고정 endpoint를 사용한다.
- 내부 provider는 외부 port를 열지 않은 격리 container network 사용을 권장한다.
- `health/ready`는 Core 준비 상태를 확인한다. AI 설정은 `/v1/operations`의 가용성과 비활성 이유로 확인한다. provider 연결 장애는 실제 생성 Job에서 확인한다.
- provider 장애 시 생성 Job만 실패하며 직전 정상 materialized Content는 유지한다.
