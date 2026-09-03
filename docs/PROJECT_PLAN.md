# APS Server 개발 계획

## 목표

현재 FastAPI 골격을 유지하면서 다음 흐름이 실제로 동작하는 서비스 가능한 MVP를 빠르게 완성한다.

```text
Vault safe sync
→ 등록된 Job 실행
→ canonical JSON 검증
→ materialized result 게시
→ JSON API 반환
→ 요청 시 같은 JSON을 HTML로 표시
```

## 현재 상태

Core MVP 완료. 아래 후속 범위는 기본 서비스 완료 조건과 분리해 관리한다.

구현됨:

- FastAPI 애플리케이션
- `operator`, `viewer`, `scheduler` bearer 인증
- 고정 operation과 Idea 전용 `ideas.curate` commit operation
- in-process Job queue와 파일 기반 Job 상태
- Vault clean 검사와 fast-forward-only 동기화
- materialized JSON 조회 API
- JSON 기반 고정 template HTML renderer
- Artifact 경로 격리와 healthcheck
- Job 결과 schema 검증과 canonical checksum
- 검증된 JSON의 ContentStore 원자적 게시
- JSON 전용 생성과 저장 JSON 기반 HTML viewer
- Core-only 기본 실행과 선택 설치형 공식 `briefing` package
- `title + keywords + summary` 기반 Idea와 Idea set 응답 모델
- 고정 Vault 디렉터리 기반 Idea 수집 Job과 Core lexical 검색 API
- 영속 설정 기반 내부 cron Scheduler와 bounded in-process queue
- 서버 시작 시 queued Job 복구와 중단된 Job의 `JOB_INTERRUPTED` 처리
- 공식 확장 manifest 검증·설치와 Schedule 자동 등록
- Core AgentExecutor와 OpenAI Responses·OpenAI 호환·Agent HTTP provider 선택
- immutable OperationRegistry와 공통 Job result/publication pipeline
- manifest task 기반 briefing 확장 bridge와 제한된 ExtensionHost
- read-only Idea·Project·Service Tool registry
- 구조화된 Idea 정규화·병합·Set 후보 검증 및 batch commit

전환 또는 보완 필요:

- Idea 큐레이션은 lexical 후보 수집, AI 구조화 분석과 검증된 batch commit까지 연결됨. 대규모 hybrid 검색은 후속 Index 범위
- 범용 AgentExecutor는 OperationRegistry, briefing 확장과 Idea 큐레이션 handler에 연결됨
- 공식 확장 update·disable·서명 검증과 `aps-index`가 없음
- 역할 token은 있지만 기기 token 수명주기가 없음
- briefing 확장은 범용 bridge를 사용하지만 현재 legacy materializer가 read-only Vault 문서를 직접 읽는 전환 구조

## MVP 구현 범위

### Core 파이프라인

- operation별 고정 입력 model과 역할 유지
- Job 결과의 Pydantic/JSON Schema 검증
- canonical JSON checksum 생성
- ContentStore 원자적 게시
- 생성 실패 시 직전 정상 결과 보존
- JSON 전용 생성과 HTML viewer 분리

### Content

- 일일 브리핑
- Project 목록과 상세 브리핑
- Service 목록·상세·유지보수 상태
- Idea 목록·상세
- 제목·키워드·요약 기반 lexical Idea 검색
- Content별 generated/stale/failure 상태

### 자동 갱신

- 내부 scheduler가 등록된 고정 Job model을 queue에 등록
- 숫자 5필드 cron, schedule별 IANA timezone과 최대 24시간 누락분 1회 복구
- 중복 실행과 idempotency 처리
- 재시작 시 미완료 Job의 안전한 실패 처리
- 외부 queue 서비스는 상정하지 않고 단일 APS 프로세스의 내장 queue만 사용

### 공식 확장

- manifest와 호환 버전 규격 및 Schedule 선언
- 공식 package allowlist와 package-local entrypoint 검증
- image의 공식 원본에서 영속 설치 경로로 복사하는 CLI
- 설치 후 재시작 기반 활성화
- read-only 입력과 canonical JSON 출력
- 커뮤니티 패키지와 hot loading 제외
- checksum·서명 검증과 update·disable은 후속 구현

### 배포

- 단일 Uvicorn process
- Docker Compose 기본 서비스
- persistent data volume
- reverse proxy/VPN 운영 안내
- health/readiness와 장애 시 이전 결과 보존

## 후속 범위

- 승인형 Project proposal을 위한 bounded tool-loop 구현

- 기기별 token 발급·회전·폐기
- Project·Service용 proposal branch, diff와 명시적 승인 기반 Vault 쓰기
- 앱 알림 전달 방식
- 선택형 GPU `aps-index` 서비스와 hybrid 검색
- 공동 ProjectContext 공유 정책

## 제외 사항

- 자유 형식 agent query
- 요청자 지정 Vault 경로
- 임의 shell, executable 또는 Codex 인자
- 자동 merge, reset, 강제 checkout과 force push
- 승인 없는 Vault 문서 변경
- 커뮤니티 플러그인
- 실행 중 확장 hot loading
- 다중 web process에서 in-process queue 공유

## MVP 완료 조건

- Job 하나가 최신 Vault commit을 기준으로 유효한 canonical JSON을 생성한다.
- 검증된 JSON이 ContentStore에 게시되고 즉시 Content API에서 조회된다.
- JSON과 HTML이 동일한 저장 결과와 checksum을 사용한다.
- 조회 요청이 Vault sync, AI 또는 생성 Job을 실행하지 않는다.
- dirty·diverged Vault와 잘못된 operation 입력을 안전하게 거부한다.
- 실패한 생성이 Vault 원본과 직전 정상 결과를 손상시키지 않는다.
- 기본 Idea 검색은 `aps-index` 없이 동작한다.
- 공식 확장은 APS Server의 읽기·검증·권한 경계 안에서만 실행된다.
