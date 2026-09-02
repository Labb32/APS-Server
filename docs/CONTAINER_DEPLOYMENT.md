# APS Server container deployment

APS Server의 기본 배포 단위는 web API, in-process queue, worker, Scheduler와 공식 확장 실행기를 포함하는 컨테이너 하나다. web process는 항상 하나만 실행한다. Vault와 runtime data는 image 밖의 volume에 저장한다.

## 1. 설정 입력 우선순위

컨테이너는 다음 순서로 설정을 결정한다.

1. 컨테이너 environment 또는 Compose `env_file` (`APS_ENV_FILE`, 기본 `.env`)
2. `APS_CONFIG_FILE`로 지정한 read-only `KEY=VALUE` 파일
3. 애플리케이션 기본값

Environment가 설정 파일보다 우선한다. 설정 파일은 `APS_`로 시작하는 key와 `CODEX_HOME`만 허용하며 shell expansion이나 command 실행을 지원하지 않는다.

기본 Compose는 `./deploy/config`를 `/config:ro`에 mount한다. 파일 기반 설정을 사용할 경우 다음과 같이 준비한다.

```bash
cp deploy/config/aps.env.example deploy/config/aps.env
```

호스트 `.env`에는 다음 한 줄을 둔다.

```dotenv
APS_CONFIG_FILE=/config/aps.env
```

Token이 들어간 `deploy/config/aps.env`는 Git에 commit하지 않는다.

## 2. Vault 연결

### 새 local Vault

기본값이다. `aps-vault` named volume이 비어 있으면 image의 빈 Vault 템플릿을 복사하고 `main` branch와 최초 commit을 만든다. local Vault에는 remote가 없으므로 bootstrap이 `APS_SYNC_BEFORE_JOB=false`를 적용한다.

```dotenv
APS_VAULT_MODE=local
APS_VAULT_MOUNT=aps-vault
```

```bash
docker compose up -d --build
```

### 원격 Git Vault

빈 Vault volume에 지정한 repository를 한 번 clone한다. 이후 재시작에서는 같은 volume을 재사용하고 `origin` URL이 설정값과 같은지 확인한다. Job sync는 기존 정책대로 clean worktree에서 fetch와 fast-forward-only merge만 수행한다.

```dotenv
APS_VAULT_MODE=git
APS_VAULT_GIT_URL=ssh://git@example.com/owner/aps-vault.git
APS_VAULT_GIT_BRANCH=main
APS_VAULT_MOUNT=aps-vault
```

Private repository 인증은 URL에 token을 넣기보다 read-only deploy key, SSH agent 또는 Docker credential mount를 사용한다. APS Server는 자동 merge, reset, force checkout과 force push를 수행하지 않는다.

### 기존 host Vault mount

이미 clone된 Vault를 직접 연결할 수 있다. 컨테이너의 `node` 사용자 UID/GID가 host 경로를 읽고 Idea 전용 파일을 쓸 권한이 있어야 한다.

```dotenv
APS_VAULT_MODE=mounted
APS_VAULT_MOUNT=/srv/aps/vault
APS_SYNC_BEFORE_JOB=true
```

remote가 없는 기존 local repository라면 `APS_SYNC_BEFORE_JOB=false`로 설정한다.

## 3. 초기 공식 확장

`APS_INITIAL_EXTENSIONS`는 쉼표로 구분한 공식 확장 ID 목록이다. bootstrap이 image에 포함된 `/opt/aps/official-extensions`에서만 설치한다. 설치는 idempotent하며 애플리케이션 registry 생성 전에 끝나므로 별도 재시작 없이 첫 실행부터 활성화된다.

```dotenv
APS_INITIAL_EXTENSIONS=briefing
```

빈 값이면 Core-only 서버로 시작한다. 임의 URL이나 community package는 설치할 수 없다.

## 4. AI provider 선택

APS Server는 AI Agent 의존 서비스이므로 최초 배포에서 Core AI gateway provider를 반드시 하나 선택한다. 기본 provider는 없으며 `.env` 또는 mount한 `APS_CONFIG_FILE`에서 설정한다.

Codex를 선택할 때:

```dotenv
APS_AI_PROVIDER=codex
APS_CODEX_HOME_MOUNT=aps-codex-home
```

기본 APS Server image는 Python Core runtime이며 Node.js와 Codex CLI를 포함하지 않는다. Codex adapter는 별도 파생 image로 빌드하고 Codex Compose override를 함께 사용한다.

```bash
docker compose build aps-server
docker compose -f compose.yaml -f compose.codex.yaml build aps-server
docker compose -f compose.yaml -f compose.codex.yaml up -d
```

첫 명령은 `Dockerfile.codex`가 기반으로 사용할 `aps-server:local`을 만든다. Codex 버전은 필요할 때 `CODEX_VERSION`, 기반 image는 `APS_SERVER_BASE`로 고정할 수 있다. `/codex-home` volume도 override를 사용할 때만 생성된다.

별도 vLLM 또는 OpenAI 호환 서비스를 사용할 때는 같은 container network의 base URL과 서버 관리자가 고정한 model을 설정한다.

```dotenv
APS_AI_PROVIDER=openai-compatible
APS_AI_BASE_URL=http://vllm:8000/v1
APS_AI_MODEL=Qwen/Qwen3-8B
APS_AI_STRUCTURED_OUTPUT=true
```

별도 Agent 서비스는 `APS_AI_PROVIDER=agent-http`와 task endpoint의 정확한 URL을 사용한다. 인증이 필요하면 Git에 포함되지 않는 env 또는 secret mount에서 `APS_AI_API_KEY`를 전달한다. 공개 API 요청자는 provider, URL, model과 credential을 지정할 수 없다.

`APS_AI_PROVIDER`가 없거나 빈 값이면 container bootstrap이 실패한다. `openai-compatible`은 `APS_AI_BASE_URL`과 `APS_AI_MODEL`, `agent-http`는 `APS_AI_BASE_URL`이 함께 필요하다. Codex를 선택했지만 실행 파일이 없을 때도 bootstrap이 중단된다. bootstrap을 거치지 않고 Uvicorn을 직접 실행한 개발 환경에서는 같은 문제가 readiness 실패로 표시된다.

전체 provider 계약과 호환 모드는 [AI provider 설정](AI_PROVIDERS.md)을 참고한다.

## 5. 선택형 aps-index 연결

```dotenv
APS_INDEX_URL=http://aps-index:8090
```

같은 Compose network의 service 이름이나 접근 가능한 내부 주소를 사용한다. 현재 값은 향후 hybrid 검색 adapter를 위한 예약 설정이며 Core는 이 주소로 요청하지 않는다. 값을 생략하면 기존 lexical Idea 검색만 사용한다.

향후 별도 서비스를 함께 배포할 때의 형태는 다음과 같다.

```yaml
services:
  aps-server:
    environment:
      APS_INDEX_URL: http://aps-index:8090
  aps-index:
    image: aps-index:stable
    expose:
      - "8090"
```

`aps-index`는 외부 port를 공개하지 않고 Docker 내부 network에서만 연결하는 것을 기본으로 한다.

## 6. Scheduler 설정 mount

기본 Compose는 다음 파일을 read-only로 mount한다.

```text
deploy/config/schedules.json          → /config/schedules.json
deploy/config/schedule-overrides.json → /config/schedule-overrides.json
```

```dotenv
APS_SCHEDULES_PATH=/config/schedules.json
APS_SCHEDULE_OVERRIDES_PATH=/config/schedule-overrides.json
```

파일에는 사전에 등록된 고정 Job request만 들어갈 수 있다. shell command, executable, AI argument와 Vault path는 schema 검증에서 거부된다. 파일을 변경한 후에는 컨테이너를 재시작한다. mounted 파일은 APS Server가 덮어쓰지 않으며 실행 상태만 `/data/scheduler-state.json`에 저장한다.

다른 host 디렉터리를 사용하려면 다음 값을 변경한다.

```dotenv
APS_CONFIG_MOUNT=/srv/aps/config
```

## 7. Port와 Nginx

```dotenv
APS_HTTP_PORT=8080
APS_BIND_HOST=127.0.0.1
APS_BIND_PORT=8080
```

- `APS_HTTP_PORT`: 컨테이너 내부 Uvicorn port
- `APS_BIND_HOST`: host에서 publish할 주소
- `APS_BIND_PORT`: host publish port

같은 host의 Nginx로만 연결할 때는 기본 `127.0.0.1:8080` publish를 유지한다.

```nginx
location /aps/ {
    proxy_pass http://127.0.0.1:8080/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization $http_authorization;
}
```

외부에서 직접 접근해야 할 때만 `APS_BIND_HOST=0.0.0.0`으로 바꾸고 TLS reverse proxy, VPN 또는 방화벽을 적용한다. 다른 Compose service가 접근할 때는 host port 대신 `http://aps-server:8080`을 사용한다.

## 8. 영속 데이터

| Mount | 기본값 | 내용 |
|---|---|---|
| `/vault` | `aps-vault` | local/clone/mounted APS Vault |
| `/data` | `aps-data` | Job, content, Scheduler state, 설치된 확장 |
| `/codex-home` | `aps-codex-home` | `compose.codex.yaml`을 적용한 Codex runtime의 인증과 설정 |
| `/config` | `./deploy/config:ro` | APS env와 Scheduler 설정 |

named volume을 제거하면 해당 영속 데이터도 사라질 수 있다. 운영 환경에서는 Vault remote 또는 별도 backup을 준비한다.

## 9. 실행 확인

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs aps-server
```

```bash
curl http://127.0.0.1:8080/health/live
curl http://127.0.0.1:8080/health/ready \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
```

`health/ready`는 Vault와 token 설정, 활성 확장 및 선택된 AI provider의 필수 설정을 확인한다. 외부 provider에 실제 생성 요청을 보내지는 않는다.

개인 서버에서 공개 전 검증을 수행할 때는 [Pre-release QA](PRE_RELEASE_QA.md)의 Core-only smoke flow부터 시작해 Git 안전 경계, extension, 장애 복구와 24시간 soak 순서로 진행한다.
