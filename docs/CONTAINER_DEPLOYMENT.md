# APS Server container deployment

APS Server의 기본 배포 단위는 web API, in-process queue, worker, Scheduler와 공식 확장 실행기를 포함하는 컨테이너 하나다. web process는 항상 하나만 실행한다. Vault와 runtime data는 image 밖의 volume에 저장한다.

## 1. 설정 입력 우선순위

컨테이너는 다음 순서로 설정을 결정한다.

1. 컨테이너 environment 또는 Compose `env_file` (`APS_ENV_FILE`, 기본 `.env`)
2. `APS_CONFIG_FILE`로 지정한 read-only `KEY=VALUE` 파일
3. 애플리케이션 기본값

Environment가 설정 파일보다 우선한다. 설정 파일은 `APS_`로 시작하는 key만 허용하며 shell expansion이나 command 실행을 지원하지 않는다.

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

Git 인증은 `/git-auth` named volume에 영속화된다. 한 번 등록한 HTTP(S) credential 또는 SSH key는 container를 다시 만들어도 재사용하며 `/vault`에 mount한 기존 clone에도 그대로 적용된다. URL에 token이나 password를 넣는 방식은 설정 검증에서 거부된다.

HTTP(S) private repository는 image를 build한 뒤 아래 명령을 한 번 실행한다. token은 대화형 hidden prompt로만 입력되며 command line이나 environment에 넣지 않는다. GitHub, GitLab, Gitea와 표준 Git HTTP credential을 지원하는 서비스에 같은 방식으로 사용할 수 있다. 평문 HTTP는 credential을 보호하지 못하므로 신뢰된 내부망이 아니라면 HTTPS를 사용한다.

```bash
docker compose build aps-server
docker compose run --rm --entrypoint aps-git-auth aps-server \
  login-http https://git.example.com/owner/aps-vault.git
```

SSH private repository는 persistent deploy key를 한 번 만들고 출력된 public key를 Git 서비스에 등록한다. `ssh-keyscan`으로 수집된 host key의 fingerprint는 서비스가 공개한 값과 별도로 대조해야 한다.

```bash
docker compose run --rm --entrypoint aps-git-auth aps-server \
  init-ssh git.example.com
```

컨테이너 Git은 대화형 credential prompt를 끄고 SSH `BatchMode`와 strict host key 검증을 강제하므로 저장된 인증이 없거나 host key가 맞지 않으면 즉시 실패한다. 인증 등록 후 `docker compose up -d`를 실행하면 clone, pull과 push에 같은 credential을 자동 사용한다.

```dotenv
APS_VAULT_PUSH_AFTER_COMMIT=true
```

`APS_VAULT_PUSH_AFTER_COMMIT=true`이면 문서화된 tracked Idea commit 흐름에서 생성한 commit을 현재 branch의 tracking upstream으로 즉시 push한다. push 전에 해당 remote를 다시 fetch하고 remote tip이 local HEAD의 ancestor일 때만 명시적인 branch refspec으로 push한다. 경합이나 divergence가 생기면 merge, reset, 강제 checkout 또는 force push 없이 실패하며 local commit은 보존된다. `false`이면 기존처럼 commit만 생성한다.

같은 mount 인증으로 운영자가 container 내부에서 직접 동기화 상태를 확인하거나 수동 동기화할 수도 있다.

```bash
docker compose exec aps-server git -C /vault pull --ff-only
docker compose exec aps-server git -C /vault push
```

수동 명령에서도 merge commit이나 force push는 사용하지 않는다.

### 기존 host Vault mount

이미 사용 중인 clone을 remote URL 방식과 관계없이 직접 연결할 수 있다. 저장소의 `.git/config`, 현재 branch와 remote 설정은 그대로 유지하며 인증만 `/git-auth`에서 공급한다. upstream tracking이 없지만 같은 이름의 `origin/<현재 브랜치>`가 있으면 그 branch를 pull/push 대상으로 사용한다. 컨테이너의 `aps` 사용자 UID/GID `10001:10001`이 host 경로를 읽고 Idea 전용 파일을 쓸 권한이 있어야 한다.

```dotenv
APS_VAULT_MODE=mounted
APS_VAULT_MOUNT=/srv/aps/vault
APS_SYNC_BEFORE_JOB=true
```

remote가 없는 기존 local repository라면 `APS_SYNC_BEFORE_JOB=false`로 설정한다.

### local Vault를 원격에 최초 게시

`local` mode로 사용하던 named volume도 container 내부의 일반 Git 명령으로 GitHub, GitLab, Gitea 등에 최초 게시할 수 있다. 먼저 위 절차로 인증한 뒤 remote를 추가하고 현재 branch를 push한다.

```bash
docker compose exec aps-server git -C /vault remote add origin git@github.com:owner/aps-vault.git
docker compose exec aps-server git -C /vault push -u origin HEAD
```

HTTPS remote도 동일하며 URL에 token을 포함하지 않는다. 최초 게시 후 `.env`의 `APS_VAULT_MODE=mounted`, `APS_SYNC_BEFORE_JOB=true`를 설정하고 container를 다시 시작하면 기존 volume을 유지한 채 자동 pull과 선택형 push를 사용할 수 있다. remote 이름 변경, branch 변경과 최초 remote 추가는 운영자가 위와 같이 명시적으로 수행한다.

## 3. 초기 공식 확장

`APS_INITIAL_EXTENSIONS`는 쉼표로 구분한 공식 확장 ID 목록이다. bootstrap이 image에 포함된 `/opt/aps/official-extensions`에서만 설치한다. 설치는 idempotent하며 애플리케이션 registry 생성 전에 끝나므로 별도 재시작 없이 첫 실행부터 활성화된다.

```dotenv
APS_INITIAL_EXTENSIONS=briefing
```

빈 값이면 Core-only 서버로 시작한다. 임의 URL이나 community package는 설치할 수 없다.

## 4. AI provider 선택

기본값 `APS_AI_PROVIDER=none`으로 Core API, 문서 조회, Inbox 접수와 Vault catalog 갱신을 사용할 수 있다. AI 사서와 AI 의존 확장을 사용할 때만 `.env` 또는 mount한 `APS_CONFIG_FILE`에서 provider를 선택한다.

OpenAI Responses API를 선택할 때:

```dotenv
APS_AI_PROVIDER=openai
APS_AI_API_KEY=replace-with-openai-api-key
APS_AI_MODEL=replace-with-an-available-responses-model
```

기본 APS Server image가 고정된 OpenAI Responses endpoint를 직접 호출한다. Codex 계열 API 모델도 `APS_AI_MODEL`로 선택하며 Codex CLI, Node.js 또는 별도 runtime image를 설치하지 않는다.

별도 vLLM 또는 OpenAI 호환 서비스를 사용할 때는 같은 container network의 base URL과 서버 관리자가 고정한 model을 설정한다.

```dotenv
APS_AI_PROVIDER=openai-compatible
APS_AI_BASE_URL=http://vllm:8000/v1
APS_AI_MODEL=Qwen/Qwen3-8B
APS_AI_STRUCTURED_OUTPUT=true
```

별도 Agent 서비스는 `APS_AI_PROVIDER=agent-http`와 task endpoint의 정확한 URL을 사용한다. 인증이 필요하면 Git에 포함되지 않는 env 또는 secret mount에서 `APS_AI_API_KEY`를 전달한다. 공개 API 요청자는 provider, URL, model과 credential을 지정할 수 없다.

`APS_AI_PROVIDER`의 기본값은 `none`이다. 선택한 provider의 key·model·endpoint가 부족해도 Core는 기동하며 AI operation만 `PROVIDER_NOT_CONFIGURED`로 비활성화한다. 필수 값은 `openai`의 key/model, `openai-compatible`의 base URL/model, `agent-http`의 base URL이다.

전체 provider 설정과 호환 모드는 [AI 실행·provider 안내](AI_EXECUTION.md)를 참고한다.

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

기본 일정 `vault-content`는 AI 없이 `vault.content.refresh`를 실행해 Project·Service·Idea·Idea Set catalog를 게시한다. `idea-curate`는 AI 사서가 설정된 경우에만 실행되며, `none` 모드에서는 `AI_DISABLED`로 비활성화된다. 기존 영속 설정의 `idea-index` 일정은 호환을 위해 유지되지만 새 기본 설정에는 포함하지 않는다. 기존 override의 `enabled: true`도 operation의 AI 가용성 제한을 우회하지 못한다.

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
limit_req_zone $binary_remote_addr zone=aps_api:10m rate=10r/s;

location /aps/ {
    client_max_body_size 1m;
    limit_req zone=aps_api burst=20 nodelay;
    proxy_pass http://127.0.0.1:8080/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization $http_authorization;
}
```

`limit_req_zone`은 Nginx의 `http` context에서 운영 환경에 맞게 별도로 정의한다. APS Server의 token은 고엔트로피여야 하지만 reverse proxy rate limit과 body limit도 함께 적용한다.

외부에서 직접 접근해야 할 때만 `APS_BIND_HOST=0.0.0.0`으로 바꾸고 TLS reverse proxy, VPN 또는 방화벽을 적용한다. 다른 Compose service가 접근할 때는 host port 대신 `http://aps-server:8080`을 사용한다.

## 8. 영속 데이터

| Mount | 기본값 | 내용 |
|---|---|---|
| `/vault` | `aps-vault` | local/clone/mounted APS Vault |
| `/data` | `aps-data` | Job, content, Scheduler state, 설치된 확장 |
| `/config` | `./deploy/config:ro` | APS env와 Scheduler 설정 |
| `/git-auth` | `aps-git-auth` | 영속 HTTPS credential helper, SSH key와 `known_hosts` |

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

`health/ready`는 Vault와 token 설정의 Core 준비 상태를 확인한다. 선택 AI의 설정 상태는 `/v1/operations`에서 확인하며, 실제 provider 연결 장애는 생성 Job 결과에 나타난다.

개인 서버에서 공개 전 검증을 수행할 때는 [Pre-release QA](PRE_RELEASE_QA.md)의 Core-only smoke flow부터 시작해 Git 안전 경계, extension, 장애 복구와 24시간 soak 순서로 진행한다.

## 개인 서버 배포에서 확인할 점

- 로컬 buildx 결과를 즉시 사용할 때는 `docker buildx build --load --tag aps-server:local .`처럼 tag와 `--load`를 명시한다.
- Compose base와 override는 같은 commit에서 준비한다. 배포 전에 사용한 `-f` 조합 그대로 `docker compose ... config`와 `config --volumes`를 확인한다. 필요한 named volume 선언이 빠진 파일 조합은 기동하지 않는다.
- `.env`의 host/port 값에는 공백·scheme·inline comment·숨은 CR 문자가 없어야 한다. Windows에서 복사한 파일은 Linux에서 줄바꿈을 확인한다.
- 수동 Job만 확인할 때는 기동 전에 `APS_SCHEDULER_ENABLED=false`로 설정한다. 기본 Scheduler는 별도 cron 파일 없이도 등록된 일정을 실행할 수 있다. 환경변수 변경은 container 재생성이 필요하다.
- 설정이 깨져 `down`도 실패하면 먼저 원래 Compose 파일과 env를 복구하고 같은 `-f` 조합으로 종료한다. 복구할 수 없을 때만 대상 container를 확인해 중지한다. Vault·data·인증 named volume은 삭제하지 않는다.
