# 설치와 운영

## Docker Compose

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose ps
```

## GitHub Container Registry 배포

`pyproject.toml`과 `aps_server.__version__`의 버전이 같도록 변경한 뒤 GitHub의 `Labb32/APS-Server` 저장소에 tag를 push한다. 현재 버전은 `0.3.0`이다. GitHub remote 이름은 `publish`로 설정되어 있다.

```bash
git status
git push publish main
git tag -a v0.3.0 -m "APS Server 0.3.0"
git show v0.3.0 --no-patch
git push publish v0.3.0
```

Tag push가 `.github/workflows/publish-container.yml`을 실행한다. GitHub 저장소의 **Actions → Publish container**에서 빌드 결과를 확인한다. 성공하면 `linux/amd64`, `linux/arm64` image가 다음 tag로 게시된다.

```text
ghcr.io/labb32/aps-server:0.3.0
ghcr.io/labb32/aps-server:0.3
ghcr.io/labb32/aps-server:latest
```

게시된 manifest 확인:

```bash
docker buildx imagetools inspect ghcr.io/labb32/aps-server:0.3.0
```

Tag는 안정 버전 `vX.Y.Z`만 사용한다. GHCR package는 최초 게시 후 기본 비공개이므로 공개 배포 시 package 설정에서 visibility를 Public으로 바꾼다. GitHub Actions는 GitHub 문서의 `GITHUB_TOKEN` 및 `packages: write` 방식으로 인증한다.

필수 값:

```dotenv
APS_OPERATOR_TOKEN=<32자 이상>
APS_VIEWER_TOKEN=<다른 32자 이상 token>
APS_SCHEDULER_TOKEN=<다른 32자 이상 token>
```

기본 설정은 localhost 공개, local Vault, 내장 Scheduler, AI 비활성이다.

공식 확장 파일은 image에 포함되지만 기본값에서는 설치되지 않는다. 설치할 확장은 CLI로 추가하고 container를 다시 시작한다.

```bash
docker compose exec aps-server aps extensions install migration
docker compose exec aps-server aps extensions install briefing
docker compose restart aps-server
```

새 volume을 처음 구성할 때 자동 설치하려면 `APS_INITIAL_EXTENSIONS=briefing,migration`을 설정한다.

## Vault 연결

내장 volume:

```dotenv
APS_VAULT_MODE=local
APS_VAULT_MOUNT=aps-vault
```

원격 Git:

```dotenv
APS_VAULT_MODE=git
APS_VAULT_GIT_URL=https://github.com/example/vault.git
APS_VAULT_GIT_BRANCH=main
APS_VAULT_PUSH_AFTER_COMMIT=true
```

기존 host Vault:

```dotenv
APS_VAULT_MODE=mounted
APS_VAULT_MOUNT=/srv/aps-vault
```

기존 Vault는 Git 저장소여야 하며 `00_Inbox` 내용이 `.gitignore`에 포함되어야 한다.

## 저장 경로

| 경로 | 내용 |
|---|---|
| `/vault` | Vault와 Inbox 원문 |
| `/data` | Job, 검색 색인, 게시 결과, Inbox metadata |
| `/git-auth` | Git 인증 정보 |
| `/config` | schedule 설정 |

## HTML 템플릿

기본 HTML을 수정하려면 필요한 파일만 호스트 디렉터리에 복사하고 해당 디렉터리를 `/config/templates`에 마운트한다.

```dotenv
APS_HTML_TEMPLATES_PATH=/config/templates
```

사용자 파일이 없는 경우 서버의 기본 템플릿을 사용한다. 변경 후 container를 다시 시작한다.

백업할 때 `/vault`와 `/data`를 함께 보관한다. `docker compose down -v`는 저장 volume을 삭제하므로 복구 절차에서 사용하지 않는다.

## Scheduler

기본 schedule은 `/config/schedules.json`, 변경값은 `/config/schedule-overrides.json`에서 읽는다. 설정 변경 후 container를 재시작한다.

내장 cron이 기본이다.

```dotenv
APS_SCHEDULER_BACKEND=internal
```

외부 Scheduler adapter를 사용하려면 container 안의 절대 경로를 지정한다.

```dotenv
APS_SCHEDULER_BACKEND=external-cli
APS_EXTERNAL_SCHEDULER_CLI=/config/bin/scheduler-adapter
```

APS는 시작할 때 다음 형식으로 호출한다.

```text
<adapter> apply --manifest /data/scheduler/external-manifest.json
```

외부 실행 환경에는 `APS_API_URL`과 scheduler token을 `APS_API_TOKEN`으로 설정한다.

## 운영 확인

```bash
curl http://127.0.0.1:8080/health/live
curl http://127.0.0.1:8080/health/ready \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
docker compose logs --tail=100 aps-server
```

외부 공개 시 TLS reverse proxy 또는 개인 VPN을 사용한다. queue가 process 내부에 있으므로 web worker는 하나만 실행한다.
