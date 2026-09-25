# AI 실행과 Provider

AI는 선택 기능이다. 기본값 `APS_AI_PROVIDER=none`에서도 Core API와 로컬 검색을 사용할 수 있다. Provider, endpoint, model, credential은 서버 설정이며 API 요청·Schedule·확장이 바꿀 수 없다. 활성 route와 schema는 [API Reference](API_REFERENCE.md), 구현 상태는 [작업 현황](TASKS.md)을 따른다.

## 실행 경계

```text
고정 API/cron → Job → Core handler → AgentExecutor → provider
                                      ↓
                        schema·ID·revision 검증
                                      ↓
                         게시 또는 허용된 commit
```

API와 cron은 같은 Job 경로를 사용한다. AgentExecutor는 등록된 task와 Tool만 수행하며 Vault sync, Git commit, Content 게시, Scheduler 등록은 하지 않는다. 외부 worker도 Vault/Git에 직접 쓰지 못한다. Core가 결과 schema와 기준 Vault revision을 확인해 한 번만 게시한다.

Task와 Tool은 시작 시 등록한다. Tool 입력·출력, capability, 횟수, 시간과 크기를 제한한다. 모델은 Vault 경로 대신 논리 ID를 다룬다. API는 task, prompt, Tool, provider, model이나 실행 한도를 전달하지 않는다. 추적 기록에 prompt·문서 원문·secret을 남기지 않는다.

## Provider 설정

| `APS_AI_PROVIDER` | 필수 설정 | 용도 |
|---|---|---|
| `none` | 없음 | Core만 실행 |
| `openai` | `APS_AI_API_KEY`, `APS_AI_MODEL` | 고정 OpenAI Responses API |
| `openai-compatible` | `APS_AI_BASE_URL`, `APS_AI_MODEL` | Chat Completions 호환 서버 |
| `agent-http` | `APS_AI_BASE_URL` | 별도 APS Agent 서비스 |

잘못된 선택 설정은 서버 기동을 막지 않는다. AI operation만 `PROVIDER_NOT_CONFIGURED`로 비활성화한다. 요청과 응답은 등록된 task schema로 검증한다.

공통 설정 기본 예:

```dotenv
APS_AI_TIMEOUT_SECONDS=600
APS_AI_PARALLEL_REQUESTS=3
APS_AI_MAX_INPUT_CHARS=200000
APS_AI_STRUCTURED_OUTPUT=true
```

제한은 timeout 10~7200초, 동시 요청 1~8개, provider 응답 2 MiB다. provider는 Python 표준 라이브러리로 호출한다. 기본 image에 Node.js, Codex CLI, provider SDK는 없다.

### OpenAI Responses API

```dotenv
APS_AI_PROVIDER=openai
APS_AI_API_KEY=replace-with-api-key
APS_AI_MODEL=replace-with-available-model
```

Core는 고정 `https://api.openai.com/v1/responses` endpoint와 task JSON Schema를 사용한다. API key는 모델 호출 권한만 준다.

### OpenAI-compatible API

```dotenv
APS_AI_PROVIDER=openai-compatible
APS_AI_BASE_URL=http://vllm:8000/v1
APS_AI_MODEL=Qwen/Qwen3-8B
```

Core는 `/chat/completions`를 호출한다. Schema response format 미지원 서버에서는 `APS_AI_STRUCTURED_OUTPUT=false`로 전환할 수 있으며 결과는 Core schema로 다시 검증한다.

### Agent HTTP

```dotenv
APS_AI_PROVIDER=agent-http
APS_AI_BASE_URL=http://ai-agent:8091/v1/tasks
```

요청은 `contract_version`, 고정 `task`, Core가 만든 입력과 `response_schema`를 포함한다. 응답은 `{"output": {...}}` 형식이며 task schema를 통과해야 한다. Agent가 자체 Tool을 실행하더라도 Vault 쓰기는 별도 Core 승인 경계가 필요하다.

## 외부 큐와 확장

외부 AI 큐는 동기 Agent HTTP와 별도 계약이다. 제출·상태·취소·결과, 인증, idempotency, timeout·재시도, 중복·늦은 결과와 revision 변경 처리를 정의해야 한다. 내부·외부 실행은 같은 operation 입력과 결과 검증을 사용한다.

확장은 task, schema, prompt, context 변환과 publication descriptor만 선언한다. Provider·credential·shell·임의 파일 접근·Git 명령·API route를 추가할 수 없다. 세부 확장 계획은 [EXTENSION_PLAN](EXTENSION_PLAN.md)에 있다.

## Secret과 장애

- API key는 Git에 넣지 않고 environment secret 또는 read-only 설정 mount로 전달한다.
- `APS_AI_BASE_URL`에는 사용자명·암호를 넣지 않는다. OpenAI provider는 고정 HTTPS endpoint를 쓴다.
- 내부 provider는 외부 port가 없는 격리 container network에 둔다.
- AI 장애는 생성 Job에만 영향을 준다. 실패한 결과는 게시하지 않고 이전 정상 Content를 유지한다.
- `/health/ready`는 Core 상태를 나타낸다. AI 가용성은 `/v1/operations`에서 확인한다.
