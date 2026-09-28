# Docker 배포

## 기본 실행

```bash
cp .env.example .env
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

`.env`에는 서로 다른 32자 이상의 `APS_OPERATOR_TOKEN`, `APS_VIEWER_TOKEN`, `APS_SCHEDULER_TOKEN`이 필요하다. 기본값은 localhost 공개, local Vault, AI 비활성이다.

```dotenv
APS_BIND_HOST=127.0.0.1
APS_BIND_PORT=8080
APS_VAULT_MODE=local
APS_AI_PROVIDER=none
```

설정 우선순위는 Compose `environment`, `env_file`, 기본값 순이다. 다른 환경 파일은 `APS_ENV_FILE`, 설정 mount는 `APS_CONFIG_MOUNT`로 지정한다.

## Vault 연결

### 새 local Vault

기본 `aps-vault` volume에 내장 template을 초기화한다.

```dotenv
APS_VAULT_MODE=local
APS_VAULT_MOUNT=aps-vault
```

### 원격 Git Vault

```dotenv
APS_VAULT_MODE=git
APS_VAULT_GIT_URL=https://github.com/example/vault.git
APS_VAULT_GIT_BRANCH=main
```

원격 URL에 credential을 넣지 않는다. 필요한 Git credential은 `aps-git-auth` volume에 저장한다. 동기화는 현재 branch의 tracking upstream만 사용하며 자동 merge·reset·force push를 하지 않는다.

### 기존 host Vault

절대 경로를 mount로 지정한다.

```dotenv
APS_VAULT_MODE=mounted
APS_VAULT_MOUNT=/srv/aps-vault
```

`00_Inbox` 내용이 Git에서 제외되는지 먼저 확인한다. Windows와 macOS의 host mount는 파일 권한과 성능을 별도로 확인한다.

## 영속 데이터

| 경로 | 내용 |
|---|---|
| `/vault` | Vault 원본과 Git-ignored Inbox |
| `/data` | Job, materialized content, 검색 색인, Idea metadata |
| `/git-auth` | 원격 Git credential |
| `/config` | schedule과 선택 설정 |

Vault와 `/data`를 함께 백업해야 pending Idea의 표시 metadata와 멱등 정보가 유지된다. 일반 복구 과정에서 `docker compose down -v`를 사용하지 않는다.

## 선택 설정

AI가 필요하면 [AI 설정](AI_EXECUTION.md)을 따른다. 공식 확장은 설치 후 재시작한다.

```bash
docker compose exec aps-server aps extensions list
docker compose exec aps-server aps extensions install briefing
docker compose restart aps-server
```

Scheduler 설정은 기본 `/config/schedules.json`, override는 `/config/schedule-overrides.json`에서 읽는다. 형식은 [기본 schedule](../deploy/config/schedules.json)과 [override 예시](../deploy/config/schedule-overrides.json)를 참고하고 변경 후 container를 재시작한다.

### 외부 Scheduler CLI

기본 backend는 `internal`이다. 외부 Scheduler를 사용할 때만 다음 값을 설정한다.

```dotenv
APS_SCHEDULER_BACKEND=external-cli
APS_EXTERNAL_SCHEDULER_CLI=/config/bin/scheduler-adapter
```

CLI는 APS 시작 시 다음 고정 형식으로 호출된다.

```text
/config/bin/scheduler-adapter apply --manifest /data/scheduler/external-manifest.json
```

adapter는 manifest의 cron과 timezone을 외부 Scheduler에 반영한다. 각 실행 명령의 `{scheduled_for}`를 원래 실행 시각의 ISO 8601 값으로 바꿔 호출해야 한다. 실행 환경에는 `APS_API_URL`과 scheduler 권한의 `APS_API_TOKEN`을 별도로 설정한다. manifest와 API에는 token이나 임의 shell 명령을 저장하지 않는다.

## 외부 접근

기본 `127.0.0.1` bind를 유지하고 TLS reverse proxy나 개인 VPN을 사용한다. proxy에는 요청 크기 제한과 rate limit을 설정하고 API token을 URL이나 access log에 넣지 않는다.

Nginx 예시:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    client_max_body_size 2m;
}
```

## 확인과 운영

```bash
curl http://127.0.0.1:8080/health/live
curl http://127.0.0.1:8080/health/ready \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
docker compose logs --tail=100 aps-server
```

처음 연결한 Vault에서는 다음 순서로 확인한다.

1. `GET /v1/operations`에서 Core operation 상태를 확인한다.
2. 임시 Idea를 접수하고 목록·검색에서 조회한다.
3. `vault.audit`와 `vault.content.refresh` Job을 실행한다.
4. container 재시작 후 Job과 Inbox가 유지되는지 확인한다.
5. 원격 Git을 사용한다면 clean worktree와 fast-forward 동기화를 확인한다.

queue가 process 내부에 있으므로 web process는 하나만 운영한다. 시작 시 queued Job은 다시 등록되고 실행 중이던 Job은 `JOB_INTERRUPTED`로 종료된다.
