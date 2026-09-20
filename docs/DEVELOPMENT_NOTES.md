# 개발 노트: 초기 구현과 개인 서버 QA

이 문서는 이전 `tasks/001-container-api-foundation.md`, `002-personal-server-compose-qa.md`, `003-agent-executor-core.md`의 기록을 통합한 것이다. 체크 상태는 당시 문서의 기록이며, 이 문서 작성 시점에 재검증한 결과가 아니다. 현재 개발 우선순위는 [`tasks/001`](../tasks/001-none-mode-capabilities.md)부터 따른다.

## 1. 컨테이너 Job API 기반 (이전 001)

목표는 APS Vault를 volume으로 사용하는 단일 컨테이너에서 인증된 비동기 Job API, worker와 CLI를 실행하는 것이었다. 범위에는 FastAPI Job 생성·조회·취소·Artifact, operator/viewer/scheduler token, JSON Job 상태와 제한된 in-process worker, Vault clean 검사와 fast-forward-only 동기화, briefing·audit·maintenance operation, Dockerfile·Compose·healthcheck가 포함됐다.

외부 queue·다중 worker host, Vault 기본 브랜치 자동 쓰기, 임의 shell/Codex 인자 전달, 프로젝트 코드 저장소 동기화, 외부 공개 인증 proxy는 범위에서 제외했다.

당시 완료로 기록된 항목: Python 테스트 전체 통과, Docker image build, 컨테이너 live/ready 확인, 임시 또는 read-only Vault의 `vault.audit`, dirty/diverged Vault 안전 실패, 자유 질문·요청자 지정 Vault 경로의 operation 배제. 미완료 항목: 운영 token·Codex 인증정보가 Git과 image에 없는지 확인.

## 2. 개인 서버 Compose QA (이전 002, 진행 중)

당시 개인 Linux 서버에서 Core image의 Python/Git와 non-root `aps` 실행, Core image에 Node.js/Codex CLI가 없음, Codex 파생 구성 기동, 강제 stop/remove 시 named volume 보존, 서버 Compose의 `aps-codex-home` 선언 누락을 확인했다. 기록된 주요 증상은 buildx 결과의 image tag 누락, Windows 복사 `.env`의 CRLF/숨은 문자로 보이는 IP·port 해석 오류, 서로 다른 버전의 Compose 파일 조합, 잘못된 설정 때문에 `down`도 실패한 경우, 기본 Scheduler 자동 실행에 대한 혼동이었다. 당시 추정 원인은 확정 진단으로 간주하지 않는다.

남은 작업은 Docker/Compose/dotenv의 LF 정책 고정, buildx local QA의 `--load`·`--tag` 명시, 배포 전 `docker compose config`·`config --volumes` 확인, 수동 QA의 `APS_SCHEDULER_ENABLED=false` 안내, invalid env/Compose 상태의 안전한 종료 절차, 동일 commit의 Compose base/override 동시 배포 확인이다.

완료 기준은 Linux 배포에서 수동 수정 없이 Compose 설정 확인, Scheduler 동작을 통제한 수동 briefing Job, 같은 구성으로 정상 종료, 재기동 후 Vault·Job data·인증 volume 보존, 오류와 복구 방법의 배포 문서화다. 기존 Vault/data/인증 volume 삭제와 `docker compose down -v`·broad prune을 일반 복구 수단으로 사용하지 않는다.

## 3. Core AgentExecutor (이전 003, 2026-09-03 완료 기록)

목표는 모델 provider와 APS 기능을 분리하고 Core가 허용한 task와 Tool만 실행하는 runtime을 구축하는 것이었다. provider-neutral 계약, OpenAI Responses/OpenAI-compatible/Agent HTTP adapter, task registry, 구조화 출력과 제한된 재시도, 최대 8단계 tool loop, Pydantic·capability 검사, 호출·출력·timeout 제한, 민감한 원문을 제외한 trace, briefing 확장 분리, 단일 action envelope, Linux용 LF 정책이 완료로 기록됐다.

당시 후속 항목도 완료로 기록됐다: 공통 Operation registry, application composition root 조립, read-only Idea/Project/Service Tool, briefing task의 공식 확장 이전, `ideas.curate-plan`의 검증 및 단일 commit gate.

유지할 제약: 공개 API는 task ID·prompt·Tool·provider·model·실행 제한을 받지 않는다. Tool은 path·shell·executable·credential을 입력받지 않는다. AgentExecutor는 Vault sync·Git commit·Content 게시·Scheduler 등록을 수행하지 않는다. Project/Service tracked 문서는 proposal branch와 명시적 승인 흐름 전까지 수정하지 않는다.
