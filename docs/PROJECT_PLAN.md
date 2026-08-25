# APS Server 프로젝트 기획서

## 1. 프로젝트 개요

APS Server는 Git 원격으로 동기화되는 APS Vault를 서버에서 읽어 일일 브리핑, 프로젝트·서비스 점검과 제한된 에이전트 요청을 자동 실행하는 개인 개발 인프라다.

APS Vault가 아이디어, 프로젝트, Task, 서비스와 유지보수 기록의 원본을 소유하고, 이 프로젝트는 해당 원본을 안전하게 소비하는 API, worker, CLI와 컨테이너 배포를 소유한다.

## 2. 목표

1. 여러 개발 기기에서 갱신한 일정·목표·Task·인계를 서버가 동일한 기준으로 읽게 한다.
2. 매일 브리핑과 관리 작업을 정기 또는 사용자 요청으로 실행한다.
3. CLI, cron, 모바일과 향후 컨시어지가 동일한 Job API를 사용하게 한다.
4. Git 충돌이나 작업 실패가 Vault 원본과 이전 정상 결과를 손상하지 않게 한다.

## 3. 사용자 흐름

### 개발 기기

1. 사용자가 APS Vault를 pull한다.
2. 아이디어, 프로젝트 목표, 일정과 Task를 수정한다.
3. 변경을 commit·push한다.
4. 필요하면 APS CLI로 브리핑이나 점검 Job을 요청한다.

### 자동화 서버

1. cron, systemd timer 또는 API 요청이 허용된 Job을 생성한다.
2. worker가 APS Vault의 clean 상태와 upstream을 확인한다.
3. fast-forward 가능한 경우에만 최신 commit을 적용한다.
4. 고정된 commit에서 브리핑·점검·에이전트 작업을 실행한다.
5. 결과를 검증하고 Job 상태와 Artifact를 저장한다.
6. 실패 시 원본과 이전 정상 결과를 유지하고 원인을 기록한다.

## 4. 시스템 경계

### APS Vault가 소유하는 것

- 개발 아이디어와 프로젝트 생애주기
- 프로젝트 목표, 일정, 마일스톤과 완료 조건
- 프로젝트별 브리핑 규칙, Task와 기기 간 인계
- 서비스 운영 및 유지보수 문서
- `scripts/daily_briefing.py`와 프로젝트별 브리핑 입력

### APS Server가 소유하는 것

- 인증된 비동기 Job API
- operation별 권한과 입력 검증
- Job queue, 상태, 결과와 Artifact 보존
- Vault 동기화와 실행 잠금
- 브리핑·점검·에이전트 worker
- API를 호출하는 CLI
- 컨테이너 image, Compose와 healthcheck
- 서버 배포·관측·복구 절차

### 포함하지 않는 것

- 프로젝트 소스 저장소의 pull과 구현 코드 분석
- 프로젝트와 무관한 개인 일정·생활 관리
- 임의 shell 명령이나 Codex CLI 인자 실행
- Vault 충돌 자동 병합, 강제 checkout과 reset
- APS Vault 기본 브랜치 자동 commit·push
- 익명 인터넷 공개

## 5. 제안 아키텍처

```text
Developer devices
  └─ commit / push
         ↓
Git remote APS Vault
         ↓ fetch + fast-forward only
APS Server container
  ├─ FastAPI
  │   ├─ authentication / roles
  │   ├─ Job creation and query
  │   └─ Artifact download
  ├─ Job store
  ├─ Worker pool
  │   ├─ briefing
  │   ├─ Vault audit
  │   ├─ service maintenance check
  │   └─ scoped agent query
  └─ Codex CLI
         ↓
Validated JSON / HTML / logs
```

서버는 단일 Uvicorn process로 실행한다. 현재 queue가 process 내부에 있으므로 web worker를 여러 개 실행하지 않는다.

## 6. API 운영 모델

### 역할

| 역할 | 주요 사용처 | 권한 |
|---|---|---|
| `scheduler` | cron, systemd timer | 등록된 정기 Job 생성 |
| `operator` | 개발자 CLI | 전체 읽기 Job 생성·조회·취소 |
| `viewer` | 모바일, 컨시어지 | 브리핑·유지보수 결과 조회와 제한 실행 |

### 1차 operation

| Operation | 목적 |
|---|---|
| `briefing.daily` | 진행 중 프로젝트와 활성 서비스 일일 브리핑 |
| `briefing.project` | 특정 프로젝트 브리핑 |
| `vault.audit` | metadata와 프로젝트 컨텍스트 누락 점검 |
| `service.maintenance_due` | 기한이 된 서비스 점검 조회 |
| `agent.query` | 선택한 Vault 문서만 읽는 자유 질문 |

모든 장기 작업은 `202 Accepted`와 `job_id`를 반환하고 별도 조회로 완료 상태를 확인한다. 동일 요청의 중복 실행은 `Idempotency-Key`로 방지한다.

## 7. 데이터와 보안

- API token과 Codex 인증정보는 image나 Git에 포함하지 않는다.
- token은 operator, viewer, scheduler별로 분리한다.
- Vault clone, Job data와 Codex home은 각각 별도 volume으로 제공한다.
- `agent.query`는 허용된 Vault 경로를 Job 전용 디렉터리에 복사한 뒤 그 디렉터리에서만 Codex를 실행한다.
- 절대경로, `..`, Windows drive 경로와 Vault 밖 symlink는 거부한다.
- 사용자 질문과 문서 원문은 기본 감사 로그에 기록하지 않는다.
- 외부 접근은 reverse proxy의 TLS와 추가 인증을 거친다.

## 8. 배포 구조

```text
/srv/aps/
├── repo/          # APS Vault clone
├── codex-home/    # Codex 인증, Git 추적 금지
├── data/          # Job, Artifact와 임시 작업
└── aps-server/    # 이 프로젝트 clone과 Compose
```

컨테이너는 기본적으로 `127.0.0.1:8080`에만 공개한다. reverse proxy가 필요한 경우에만 별도 내부 network 또는 loopback port로 연결한다.

## 9. 마일스톤

### M1. 컨테이너 API 기반

- [x] FastAPI Job API와 역할 인증
- [x] JSON Job store와 in-process worker
- [x] Vault fast-forward adapter
- [x] 브리핑·점검·에이전트 operation 초안
- [x] CLI 초안
- [x] Dockerfile, Compose와 healthcheck
- [x] Python 테스트와 Docker build

### M2. 서버 통합 검증

- [ ] 서버 전용 APS Vault clone과 최소 권한 Git 인증
- [ ] 서버 Codex 비대화형 인증 volume
- [ ] 동기화가 활성화된 `vault.audit` Job
- [ ] 실제 프로젝트의 `briefing.project` HTML Artifact
- [ ] 격리된 `agent.query` 범위 검증
- [ ] 재시작 시 실행 중 Job 복구 정책 결정

### M3. 스케줄과 결과 배포

- [ ] systemd timer 또는 cron의 `briefing.daily` 요청
- [ ] 중복 실행 잠금과 timeout·재시도 정책
- [ ] HTML·JSON 결과 검증
- [ ] 현재 결과의 원자적 교체와 직전 정상본 보존
- [ ] 실행 commit, 소요 시간과 결과 checksum 기록

### M4. 운영·관측성

- [ ] 오래된 결과와 연속 실패 감지
- [ ] Codex·Git 인증 만료 알림
- [ ] Job·Artifact·임시 파일 보존 및 정리 정책
- [ ] token과 Git/Codex 자격증명 교체 절차
- [ ] 백업·복구와 장애 대응 문서

### M5. 확장

- [ ] 외부 queue와 API/worker 분리 필요성 검토
- [ ] 모바일·컨시어지 viewer 연동
- [ ] 전용 브랜치 기반 `vault.propose_change` 설계
- [ ] 변경 미리보기와 사용자 승인 후 병합 흐름

## 10. 1차 완료 기준

- [ ] 실제 서버의 clean Vault clone을 안전하게 동기화한다.
- [ ] 정기 실행과 CLI 요청이 동일한 Job pipeline을 사용한다.
- [ ] 일일 브리핑 HTML을 생성·검증하고 이전 정상 결과를 보호한다.
- [ ] 부분 실패가 다른 프로젝트 결과를 막지 않는다.
- [ ] 임의 명령과 Vault 외부 파일 접근이 불가능하다.
- [ ] 인증정보가 image, Git, API 결과와 일반 로그에 노출되지 않는다.
- [ ] 운영과 장애 복구 절차가 문서화되어 APS 서비스로 인계된다.

## 11. 관련 문서

- 프로젝트 사용법: `README.md`
- API 자동 문서: 실행 서버의 `/docs`, `/openapi.json`
- Vault 운영 범위: `98_Documents/APS/APS_VAULT_SCOPE.md`
- API 계약: `98_Documents/APS/APS_AGENT_API.md`
- Vault 프로젝트 문서: `02_Projects/APS_서버_자동_브리핑_배포.md`
- 작업 계획·Task: 프로젝트의 `.brief`, `tasks` junction
