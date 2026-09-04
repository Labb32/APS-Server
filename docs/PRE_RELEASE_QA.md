# APS Server pre-release QA

실제 개인 Linux 서버에서 확인된 Compose 문제와 재검증 항목은 [개인 서버 Compose QA 발견사항](PERSONAL_SERVER_QA_FINDINGS.md)에 누적한다.

이 문서는 `0.1.x`를 개인 서버에서 검증한 뒤 공개 release로 전환하기 위한 실행 기준이다. 새 자동 test file을 만드는 대신 실제 container, API, 권한과 Vault 흐름을 직접 확인하고 결과를 기록한다.

## 1. 승인 기준

다음 조건을 모두 만족해야 공개 가능 상태로 판단한다.

- Core-only container가 재시작을 포함해 안정적으로 실행된다.
- 인증 없는 보호 API, 잘못된 역할과 잘못된 입력이 문서화된 상태 코드로 거부된다.
- Vault sync는 clean fast-forward만 수행하고 dirty·diverged 상태를 변경하지 않는다.
- 조회 요청이 Vault sync, AI 또는 생성 Job을 실행하지 않는다.
- canonical JSON과 HTML viewer가 같은 materialized 결과를 사용한다.
- Idea 쓰기가 `00_Inbox`, `01_Ideas`, `01_Idea_Sets`의 문서화된 흐름을 벗어나지 않는다.
- extension 설치 전후 operation과 schedule 차이가 manifest와 일치한다.
- 재시작·AI 장애·Job 실패에도 직전 정상 결과와 Vault 원본이 보존된다.
- token, credential, 개인 Vault 내용이 image, Git, 일반 log와 Artifact에 노출되지 않는다.
- 24시간 이상 soak 동안 queue 중복 실행, 지속적인 오류와 비정상 disk 증가가 없다.

## 2. 준비

실사용 Vault와 분리된 disposable Vault 또는 전용 QA branch를 사용한다. 원격 Git mode를 검증할 때는 별도 repository와 최소 권한 deploy key를 사용한다.

```bash
cp .env.example .env
docker compose config
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --tail=200 aps-server
```

세 역할 token은 서로 다른 무작위 값으로 바꾸고 `.env`가 `git status --short`에 나타나지 않는지 확인한다. `APS_AI_PROVIDER`는 검증할 Agent adapter를 명시적으로 선택한다. 첫 검증은 `APS_BIND_HOST=127.0.0.1`, `APS_VAULT_MODE=local`, `APS_INITIAL_EXTENSIONS=`로 시작한다.

## 3. Core-only smoke flow

```bash
curl -i http://127.0.0.1:8080/health/live
curl -i http://127.0.0.1:8080/health/ready \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
curl -i http://127.0.0.1:8080/v1/operations \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
curl -i http://127.0.0.1:8080/v1/extensions \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
curl -i http://127.0.0.1:8080/v1/scheduler \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
```

확장 없는 상태에서 `vault.audit`, `ideas.index.refresh`, `ideas.curate`만 Core operation으로 노출되는지 확인한다. Scheduler에는 `idea-index`, `idea-curate`, `vault-audit`가 보여야 하며 `briefing.*` operation과 schedule은 없어야 한다.

다음 거부 흐름도 확인한다.

- 보호 API에 token 없음 또는 잘못된 token: `401`
- viewer token으로 operator 전용 Job 실행: `403`
- 등록되지 않은 operation 또는 추가 입력 필드: `422`
- 요청자가 지정한 Vault path, command, executable 또는 provider 인자: schema에 없고 거부됨
- 없는 materialized content: 문서화된 `404`

## 4. Job과 materialized content

고유한 `Idempotency-Key`로 `ideas.index.refresh`와 `vault.audit`를 실행한다. `202` 응답의 Job ID를 조회해 `queued → running → succeeded|failed` 전이를 확인하고, 같은 key와 같은 payload의 재요청 및 다른 payload 충돌을 각각 확인한다.

성공한 content는 다음을 확인한다.

- `schema_version`, `content_type`, `generated_at`, `vault_commit`, `generator_version`, `sha256`
- 같은 JSON의 반복 조회가 Job을 새로 만들지 않음
- `format=html`이 외부 script 없이 고정 template으로 표시됨
- 응답의 CSP와 `Content-Type`이 API Reference와 일치함
- 실패한 후에도 직전 정상 JSON을 읽을 수 있음

## 5. Idea 제한 쓰기

QA용 Idea 하나를 `POST /v1/ideas`로 접수한다.

1. 응답이 `201`, `storage: inbox`, `commit_status: pending`, `vault_commit: null`인지 확인한다.
2. 생성 파일이 서버가 만든 ID를 사용하고 `00_Inbox` 밖에 쓰이지 않았는지 확인한다.
3. pending Idea가 목록·상세·검색에 즉시 나타나는지 확인한다.
4. `PATCH /v1/ideas/{idea_id}`가 Inbox만 갱신하는지 확인한다.
5. `ideas.curate` 실행 전 Git tracked 변경이 없는지 확인한다.
6. 실행 후 schema를 통과한 문서만 `01_Ideas`와 필요 시 `01_Idea_Sets`에 한 batch commit으로 기록되는지 확인한다.
7. commit 성공 뒤에만 처리된 Inbox 원본이 제거되는지 확인한다.
8. push 설정이 꺼져 있으면 자동 push가 없고, 켜져 있으면 현재 tracking upstream으로만 fast-forward push됐는지 확인한다. 두 경우 모두 branch 전환, merge, reset이 없었는지 `git status`, `git log`, `git reflog`로 확인한다.

tracked Idea 즉시 수정은 disposable remote에서만 검증하고 대상 Markdown 외의 파일이 commit되지 않는지 확인한다.

## 6. Git 안전 경계

다음 검증은 실사용 Vault가 아닌 disposable clone에서 수행한다.

- tracked 파일을 수정해 dirty 상태를 만든 뒤 sync Job이 `VAULT_DIRTY`로 중단되는지 확인
- local과 remote에 서로 다른 commit을 만들어 diverged 상태에서 자동 merge·reset하지 않는지 확인
- remote가 없는 local mode에서 `APS_SYNC_BEFORE_JOB=false`가 적용되는지 확인
- Git URL을 바꾼 채 기존 volume을 재사용하면 bootstrap이 거부하는지 확인
- 실패 뒤 worktree, branch와 remote URL이 원래 상태인지 확인

## 7. 공식 briefing extension

```bash
docker compose exec aps-server aps extensions list
docker compose exec aps-server aps extensions install briefing
docker compose restart aps-server
```

설치 뒤 `briefing.daily`, `briefing.project`, `service.maintenance_due`와 manifest의 두 schedule이 추가되는지 확인한다. 같은 설치 명령은 idempotent해야 한다. 설정한 AI provider에 대해 readiness, timeout, 구조화 JSON 검증과 provider 장애 시 이전 결과 보존을 확인한다. API 요청자가 provider, model, base URL, credential 또는 자유 prompt를 지정할 수 없어야 한다.

## 8. 재시작과 장애 복구

- queued Job이 재시작 뒤 다시 등록되는지 확인한다.
- 실행 중 강제 종료된 Job이 `JOB_INTERRUPTED` 실패로 전환되는지 확인한다.
- 손상된 JSON, schema 불일치와 AI timeout이 게시 전 차단되는지 확인한다.
- `/data` volume을 재사용하면 Job·content·scheduler state와 설치된 extension이 유지되는지 확인한다.
- `/data` 없이 새로 시작하면 이전 상태에 의존하지 않고 bootstrap되는지 확인한다.

## 9. 네트워크와 운영 보안

- `docker compose ps`에서 기본 host publish가 `127.0.0.1`인지 확인한다.
- 외부 접근은 TLS reverse proxy 또는 VPN 뒤에서만 검증한다.
- HTML upstream token 주입 시 proxy 인증과 접근 로그의 token 마스킹을 확인한다.
- `.env`, Git key와 provider API key가 image layer 및 일반 log에 없는지 확인한다.
- container가 non-root 사용자, `no-new-privileges`, read-only config mount로 실행되는지 확인한다.
- dependency와 image 취약점 scan 결과를 기록하고 release 차단 수준의 항목을 해소한다.

## 10. 24시간 soak와 공개 승인

최소 하루 동안 실제 cron tick과 수동 요청을 함께 운용하며 다음을 기록한다.

| 항목 | 기록 |
|---|---|
| 검증 commit | Git commit ID |
| image | image digest 또는 local image ID |
| Vault mode | `local`, `git`, `mounted` |
| 활성 extension | ID와 version |
| AI provider | provider와 model, secret 제외 |
| 시작·종료 시각 | timezone 포함 |
| 실행한 API 흐름 | 성공·거부·장애 복구 |
| 발견된 문제 | issue 링크와 severity |
| 공개 판단 | pass / hold 및 승인자 |

공개 직전에는 `git status`, 문서 링크, OpenAPI와 runtime route 차이, `LICENSE`, `NOTICE`, `SECURITY.md`, secret scan, container rebuild를 다시 확인한다. blocker가 하나라도 남아 있으면 tag와 public release를 만들지 않는다.
