# 개발 노트

초기 구현과 개인 서버 QA에서 나온 결정과 이슈를 요약한다. 아래 QA 기록은 당시 확인 사항이며 현재 배포 검증 결과가 아니다. 현재 구현 상태는 [작업 현황](TASKS.md)을 따른다.

## 초기 Job API와 컨테이너

초기 작업은 인증된 Job 생성·조회·취소·Artifact, 제한된 in-process worker, Vault 안전 동기화와 Docker/Compose 실행 기반을 마련했다. 외부 queue, 다중 worker host, 임의 shell/Codex 인자, 기본 branch 자동 쓰기는 범위에서 제외했다.

당시 임시 또는 read-only Vault에서 기본 API와 `vault.audit`, dirty/diverged Vault 거부, container health를 확인했다. 운영 token과 Codex 인증정보가 Git·image에 없는지 확인하는 항목은 남아 있었다.

## 개인 서버 Compose QA

기록된 문제는 buildx image tag 누락, Windows에서 복사한 `.env`의 줄바꿈, 서로 다른 버전 Compose 파일 조합, 잘못된 설정으로 인한 종료 실패, 자동 Scheduler 실행에 대한 혼동이다. 일부 원인은 추정이므로 현재 결함으로 단정하지 않는다.

배포 확인은 `docker compose config`, volume 확인, 수동 Job, 정상 종료·재기동 후 Vault·Job data·인증 정보 보존 순으로 진행한다. 기존 volume 삭제나 `docker compose down -v`를 일반 복구 절차로 쓰지 않는다. 단계별 절차는 [배포 안내](CONTAINER_DEPLOYMENT.md)와 [Pre-release QA](PRE_RELEASE_QA.md)에 있다.

## Agent 실행 경계

Provider-neutral AgentExecutor, 고정 task·Tool registry, 구조화 결과 검증, 제한된 Tool loop, timeout·호출·출력 한도와 민감 정보 없는 trace를 도입했다. 공통 operation 경계와 Idea curation의 검증된 commit 흐름도 여기에 포함된다.

유지 원칙은 API가 prompt·provider·model·Tool·경로를 받지 않는 것, Tool이 임의 파일·shell을 실행하지 않는 것, AgentExecutor가 Vault sync·Git commit·게시를 직접 하지 않는 것이다. 현재 설계는 [AI 실행과 Provider](AI_EXECUTION.md)를 따른다.

## 0.2.1 Core beta

Idea JSON/text 접수는 frontmatter 없는 `00_Inbox` 원문으로 변경했다. 표시·검색·멱등 정보는 `${APS_DATA_PATH}/ideas/intake.json`에 분리하고 pending PATCH는 원문을 바꾸지 않는다. 0.2.0 형식의 Inbox 문서는 자동 변환 없이 계속 읽는다. AI와 확장이 없어도 접수·조회·검색·재시작 복구가 동작하는 흐름을 Core beta 기준으로 삼는다.
