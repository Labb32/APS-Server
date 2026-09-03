# 개인 서버 Compose QA 발견사항

기준일: 2026-09-03

이 문서는 APS Server MVP를 개인 Linux 서버에서 직접 빌드·실행·종료하면서 확인한 배포 문제와 후속 수정사항을 기록한다. 기능 오류와 운영상 혼동을 구분하고, 수정 전까지 사용할 수 있는 안전한 복구 절차를 함께 제공한다.

## 1. 확인된 환경

- 기본 Core image: Python 3.12.14, Git 2.39.5
- container 사용자: `aps` UID/GID 999
- 기본 Core image에 Node.js와 Codex CLI가 포함되지 않음을 확인
- Codex 파생 Compose 구성으로 APS Server 기동 성공
- 테스트 종료 시 Compose 설정 검증 오류가 연속 발생해 container를 직접 stop/remove함
- named volume은 직접 삭제하지 않아 Vault, Job data와 Codex 인증 data가 보존됨

## 2. 발견사항

### QA-001. buildx 결과에 image 이름과 tag가 없음

증상:

- `docker buildx build` 후 사용할 image 이름을 찾기 어려움
- builder 설정에 따라 결과가 local image store에 로드되지 않을 수 있음

원인:

- 빌드 명령에 `--tag`와 local 실행용 `--load`가 명시되지 않음

수정사항:

- 로컬/개인 서버용 문서의 표준 빌드 명령을 다음으로 고정한다.

```bash
docker buildx build --load --tag aps-server:local .
```

- multi-platform registry 게시와 local QA 빌드를 문서에서 분리한다.

완료 기준:

- 새 서버에서 명령 한 번으로 `aps-server:local`이 생성된다.
- 빌드 직후 `docker image inspect aps-server:local`이 성공한다.

### QA-002. `invalid IP address: 127.0.0.1`

### QA-003. `invalid containerPort: 8080`

증상:

- `docker compose down` 과정에서 정상처럼 보이는 IP와 port가 유효하지 않다고 표시됨
- Compose는 종료할 때도 전체 project 설정을 다시 해석하므로 잘못된 보간값이 있으면 기존 container를 내리지 못함

유력 원인:

- Windows checkout에서 Linux 서버로 복사한 `.env`의 CRLF 또는 값 뒤 숨은 문자
- `APS_BIND_HOST`, `APS_BIND_PORT`, `APS_HTTP_PORT`의 공백이나 inline comment
- shell environment의 동일 변수가 `.env` 값을 덮어씀

수정사항:

1. `.gitattributes`에서 Compose, dotenv, Dockerfile과 shell 관련 파일의 LF를 고정한다. 저장소 설정 반영 완료.
2. 배포 문서에 다음 preflight를 추가한다.

```bash
sed -i 's/\r$//' .env
grep -nE '^APS_(BIND_HOST|BIND_PORT|HTTP_PORT)=' .env | cat -A
docker compose -f compose.yaml -f compose.codex.yaml config
```

3. 예제 값에는 scheme, 공백과 inline comment를 넣지 않는다고 명시한다.
4. 향후 bootstrap 전 별도 CLI 검증 명령에서 host와 port를 진단한다.

정상 값:

```dotenv
APS_BIND_HOST=127.0.0.1
APS_BIND_PORT=8080
APS_HTTP_PORT=8080
```

완료 기준:

- Windows에서 복사한 배포 묶음을 Linux에서 별도 줄바꿈 수정 없이 사용할 수 있다.
- 잘못된 값은 container 생성 전에 어떤 key가 잘못됐는지 알 수 있다.

### QA-004. `aps-codex-home` undefined volume

증상:

```text
service refers to undefined volume aps-codex-home: invalid compose project
```

확인 결과:

- 서버에서 사용한 `compose.codex.yaml`에 `aps-codex-home` top-level volume 선언이 누락되어 있었음
- 저장소 `main`의 원본 override에는 선언이 존재하므로 불완전한 복사본 또는 서로 다른 버전의 Compose 파일 조합도 확인해야 함

필수 구조:

```yaml
services:
  aps-server:
    volumes:
      - aps-codex-home:/codex-home

volumes:
  aps-codex-home:
```

수정사항:

1. 배포 전에 두 Compose 파일을 항상 같은 commit에서 준비한다.
2. `docker compose ... config --volumes` 결과에 `aps-vault`, `aps-data`, `aps-codex-home`가 모두 있는지 확인한다.
3. release archive에 포함할 파일 목록과 checksum을 제공해 부분 복사를 방지한다.
4. Codex runtime이 유지되는 MVP branch에서는 공통 volume 선언 위치를 단순화한다.

완료 기준:

- 새 clone에서 Codex override를 합친 `docker compose config`가 성공한다.
- 인증 volume이 container 재생성 후에도 유지된다.

### QA-005. 잘못된 Compose 설정 때문에 `down`도 실패

증상:

- 실행 중인 container는 정상이지만 현재 Compose 파일 또는 env가 유효하지 않아 `docker compose down`을 실행할 수 없음

수정사항:

- 운영 가이드에 다음 복구 순서를 추가한다.

```text
1. 사용한 Compose 파일과 env를 정상화한다.
2. 같은 -f 조합으로 docker compose down을 실행한다.
3. 설정 복구가 불가능할 때만 container 이름을 확인해 docker stop/rm을 사용한다.
4. named volume은 명시적으로 승인하지 않는 한 삭제하지 않는다.
```

- `down -v`, broad volume prune과 image prune을 일반 복구 명령으로 안내하지 않는다.

완료 기준:

- 설정 파손 상태에서도 Vault와 인증 volume을 보존한 종료 절차를 문서만 보고 수행할 수 있다.

### QA-006. 별도 cron 설정이 없어도 기본 Schedule이 실행됨

증상 또는 혼동:

- 별도 cron 파일을 작성하지 않으면 요청이 있을 때만 동작할 것으로 예상하기 쉬움
- 실제 기본값은 `APS_SCHEDULER_ENABLED=true`이며 Core와 설치된 확장의 Schedule을 자동 등록함

현재 기본 일정:

| 시간대 | Schedule |
|---|---|
| 6시간마다 정각 | Idea index refresh |
| 6시간마다 15분 | Idea curate |
| 매일 04:30 | Vault audit |
| 매일 05:15 | briefing 서비스 유지보수 |
| 매일 06:00 | daily briefing |

수정사항:

- 빠른 시작에 자동 실행 기본값을 눈에 띄게 표시한다.
- 수동 QA에서는 `APS_SCHEDULER_ENABLED=false`를 기본 예시로 사용한다.
- env 변경 후 단순 restart가 아니라 container recreate가 필요함을 명시한다.

완료 기준:

- 첫 기동 전에 자동 실행 여부와 AI 사용 가능 시간을 사용자가 알 수 있다.
- Scheduler 비활성 상태에서도 수동 Job API는 정상 동작한다.

## 3. 적용 우선순위

1. LF 고정과 Compose preflight 추가
2. Compose 파일 동시 버전 확인 및 volume 선언 검증
3. 수동 QA용 Scheduler 비활성 예시 추가
4. 안전한 종료·복구 절차 문서화
5. buildx local build와 registry build 명령 분리

## 4. 재검증 체크리스트

- [ ] 새 source copy에서 `docker compose ... config` 성공
- [ ] Core와 Codex 파생 image에 이름과 tag 존재
- [ ] `config --volumes`에서 필요한 named volume 3개 확인
- [ ] scheduler disabled 상태로 container 기동
- [ ] liveness/readiness와 Codex 인증 상태 확인
- [ ] 수동 briefing Job 1회 성공
- [ ] 동일 Compose 조합으로 `down` 성공
- [ ] 재기동 후 Vault, Job data와 Codex 인증 유지
- [ ] `.env`와 인증정보가 Git status 및 image layer에 없음

## 5. 브랜치 적용 범위

- `main` MVP: Codex 파생 image의 개인 서버 QA 보완에 이 문서를 사용한다.
- `feature/generic-ai-agent`: CLI runtime을 제거하더라도 buildx, env, Scheduler와 종료 관련 항목은 그대로 적용한다.
- AgentExecutor 구현은 [AgentExecutor 설계](AGENT_EXECUTOR_DESIGN.md)를 기준으로 별도 진행한다.
