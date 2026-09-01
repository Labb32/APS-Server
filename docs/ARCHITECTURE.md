# APS Server 아키텍처

## 1. 구성 요소

```text
clients / cron / reverse proxy
                │ bearer token
                ▼
┌────────────────────────────────────────────┐
│ APS Server                                 │
│ FastAPI · auth · queue · scheduler         │
│ Vault sync · AI gateway · result store     │
│ JSON validation · HTML renderer            │
│ official extensions                        │
└──────────────┬─────────────────────────────┘
               │ read and fast-forward sync
               ▼
          APS Vault (Markdown)

optional deployment:
APS Server ── internal API ── aps-index
                              GPU embedding
                              vector index
```

APS Server 인스턴스 하나는 사용자 한 명과 Vault 하나를 담당한다. 사용자 수를 늘릴 때는 인스턴스를 분리한다.

## 2. APS Vault

APS Vault는 다음 데이터의 유일한 원본이다.

- Idea
- Project와 Task
- Service 운영 및 유지보수 기록
- ProjectContext
- 문서 template과 metadata

Vault는 HTTP API, 인증, queue, worker, scheduler와 공개 웹 서비스를 제공하지 않는다. APS Server가 Vault 문서를 읽고 외부 기능을 제공한다.

Git remote를 사용하는 경우 APS Server는 다음 조건에서만 동기화한다.

- worktree가 clean 상태
- 현재 HEAD가 upstream의 ancestor
- `merge --ff-only`로 이동 가능

자동 merge, reset, 강제 checkout, force push와 자동 충돌 해결은 금지한다.

## 3. APS Server Core

Core가 소유하는 책임:

- bearer token 인증과 역할별 권한
- 향후 기기 token 발급·회전·폐기
- FastAPI와 고정 API 계약
- operation allowlist와 입력 schema 검증
- in-process Job queue와 scheduler
- Vault clean 검사와 fast-forward-only 동기화
- AI·hosting provider 연결 정책
- canonical JSON schema 검증과 checksum
- materialized result의 원자적 저장
- JSON 기반 HTML 렌더링
- Job, Artifact, 상태와 감사 정보
- 공식 확장의 설치·호환성·활성 상태

Core는 요청자에게 shell 명령, 실행 파일, Vault 경로, AI prompt, 모델명 또는 Codex 인자를 선택하게 하지 않는다.

내장 Scheduler는 Core `schedules.json`, 설치된 확장 manifest와 사용자 `schedule-overrides.json`을 합쳐 숫자 5필드 cron을 구성하고 등록된 고정 Job만 bounded in-process queue에 넣는다. schedule ID와 예정 시각으로 중복 실행을 막고, 서버 시작 시 queued Job은 다시 등록하며 진행 중이던 Job은 안전한 실패로 전환한다. 외부 queue와 다중 web process 공유는 지원하지 않는다.

## 4. Content 생성과 조회

```text
scheduled/manual Job
  → Vault clean + fast-forward sync
  → 정규화된 읽기 전용 입력 생성
  → Core materializer 또는 공식 확장 실행
  → canonical JSON 생성
  → Pydantic/JSON Schema와 checksum 검증
  → 임시 파일 저장
  → 마지막 정상 materialized result 원자적 교체
  → Job 완료

Content GET
  → 저장된 JSON 읽기
  ├─ format=json: 그대로 반환
  └─ format=html: 고정 template에 주입
```

조회 요청은 Vault sync, AI 호출, 확장 실행 또는 재생성을 시작하지 않는다. 실패한 생성 결과는 이전 정상 결과를 덮어쓰지 않는다.

HTML은 canonical JSON의 viewer다. 별도 HTML 생성 Job을 두지 않고 AI가 HTML·CSS·JavaScript를 만들지 않는다.

## 5. 공식 확장

공식 확장은 APS Server 기능을 정해진 범위에서 확장하는 패키지다. Vault 내부의 실행 코드를 플러그인으로 사용하지 않는다.

확장에 전달할 수 있는 것:

- Core가 정규화한 읽기 전용 문서 데이터
- 논리 ID와 기준 Vault commit
- 등록된 operation의 schema 입력
- Core를 통한 AI provider 호출 권한
- 확장 전용 파생 데이터 경로

확장이 반환할 수 있는 것:

- 사전 정의된 canonical JSON
- 상태와 구조화 오류
- JSON을 표시하는 고정 HTML template
- 검증 대상 Artifact

확장이 할 수 없는 것:

- Vault 직접 작성·수정·삭제
- Git 명령 실행
- 인증·권한·scheduler 우회
- 임의 FastAPI route와 shell 명령 등록
- 다른 확장 데이터 직접 접근
- 서버 secret 전체 열람

초기에는 APS image가 제공한 공식 package 원본만 설치할 수 있다. Core는 기본적으로 활성 확장 없이 시작한다. `APS_INITIAL_EXTENSIONS`는 애플리케이션 시작 전에 공식 package를 설치해 첫 실행부터 활성화하고, CLI로 실행 중 설치한 package는 다음 재시작부터 Operation과 Schedule을 활성화한다. 실행 중 hot loading은 하지 않는다.

권장 저장 위치:

```text
/opt/aps/official-extensions/    # image에 포함된 설치 가능 공식 package 원본
/opt/aps/vault-template/         # local mode의 빈 Vault 초기 원본
/vault/                          # local volume, Git clone 또는 host mount
/data/extensions/<id>/           # 설치되어 다음 재시작부터 활성화되는 package
/config/schedules.json           # read-only mount 가능한 Core 일정
/config/schedule-overrides.json  # read-only mount 가능한 시간 재정의
/data/scheduler-state.json       # Scheduler 실행 상태
```

## 6. Idea 검색

### 기본 검색

APS Server Core는 모델 없이 다음 필드를 인덱싱한다.

```text
title + keywords + summary
```

제목 일치, 키워드 교집합, 전문 검색과 문자열 유사도를 조합한다. 결과에는 `search_mode: lexical`을 표시한다.

### 선택형 `aps-index`

`aps-index`는 GPU 임베딩과 Vector 검색을 담당하는 별도 공식 서비스다. 플러그인 패키지가 아니며 Docker Compose profile 등으로 선택 배포한다.

- 외부 port를 공개하지 않는다.
- APS Server가 전달한 정규화 데이터만 인덱싱한다.
- 임베딩 입력은 제목, 키워드와 요약으로 제한한다.
- 문서 hash, Vault commit, model ID와 version을 기록한다.
- model version이 바뀌면 전체 인덱스를 재생성한다.
- 장애 시 기본 lexical 검색으로 강등한다.
- 검색과 그룹 후보만 제공하며 Vault를 수정하지 않는다.

`aps-index`가 준비되면 Core가 lexical과 semantic 점수를 조합하고 `search_mode: hybrid`를 반환한다.

## 7. 쓰기와 승인 경계

Idea는 고정된 Git-ignored `00_Inbox`를 clone-local staging으로 사용한다. 요청자는 경로를 선택할 수 없고 서버가 발급한 Idea ID만 파일명으로 사용한다.

```text
Idea request
  → 00_Inbox/<idea_id>.md 원자적 저장
  → pending Idea로 조회
  → Scheduler의 고정 schema 정리 또는 명시적으로 접수된 통합·Set 후보 처리
  → path/schema/reference 검증
  → 01_Ideas와 01_Idea_Sets의 대상 파일만 stage
  → batch commit
  → commit 성공 후 Inbox 원본 제거
```

이미 commit된 Idea의 제한된 수정은 schema 검증 후 대상 문서만 즉시 commit한다. 새 pending Idea의 수정은 Inbox에만 반영한다. 검증 또는 Git 처리가 실패하면 Inbox를 보존한다. 현재 Core는 raw content의 임시 title/summary 생성과 명시적 통합·Set 후보를 결정적으로 처리하며, AI 기반 자동 요약·중복 분류·Set 추천은 후속 curator 범위다.

Project 작성과 Service 문서 갱신은 다음 승인 절차가 구현된 이후에만 활성화한다.

```text
request
  → staging
  → Vault safe sync
  → isolated proposal branch
  → 문서 생성과 path/schema/diff 검증
  → proposal commit
  → 사용자에게 변경 요약과 diff 제공
  → explicit approve 또는 reject
  → 승인된 proposal branch 게시
  → 기본 branch 병합은 사용자/외부 절차
```

Idea 전용 경계 밖의 승인 전 원본 이동·삭제·덮어쓰기와 기본 branch 자동 push·merge는 금지한다.

## 8. 인증과 배포

- 현재는 `operator`, `viewer`, `scheduler` 역할 token을 환경변수로 구성한다.
- 목표는 같은 사용자에게 기기별 token을 발급하고 역할·회전·폐기를 관리하는 것이다.
- IP, Origin과 proxy header는 사용자 신원의 근거로 사용하지 않는다.
- reverse proxy가 없어도 APS Server 인증은 필수다.
- 외부 공개 시 TLS reverse proxy, VPN 또는 인증 gateway를 사용한다.
- in-process queue를 사용하는 동안 Uvicorn worker는 하나만 실행한다.

## 9. 현재 코드의 전환 상태

현재 구현은 아직 다음 과거 구조를 포함한다.

- 역할별 정적 token만 지원
- 확장 update·disable과 checksum/서명 검증 미구현
- 공식 briefing 확장이 정규화된 Core 입력 대신 Vault 문서를 직접 읽는 전환 구조
- briefing 확장이 Core AI gateway 대신 고정 Codex CLI adapter를 직접 사용하는 전환 구조

Vault의 기존 브리핑 코드와 문서는 삭제하지 않고 `extensions/briefing/legacy`에 복사해 보존했다. APS Server의 활성 실행 경로는 Vault 내부 script가 아니라 `extensions/briefing/entrypoint.py`다.
