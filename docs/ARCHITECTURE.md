# 구조와 데이터 경계

APS Server는 한 사용자와 하나의 Vault를 연결하는 단일 web process 서비스다.

```text
API routers
  ├─ Content / Idea / Search
  └─ Job / Scheduler
        ↓
Operation registry → in-process queue → Core service
        ↓
Vault / Data / 선택형 AI provider
```

## 코드 구조

- `main.py`: application 조립, 인증과 공통 오류 처리
- `*_api.py`: HTTP route와 권한 검사
- `operations.py`: 허용된 operation 연결
- `runner.py`: Job queue와 실행 상태
- `scheduler.py`: 내장 cron 실행과 외부 backend 상태
- `schedule_config.py`: schedule·override·extension 설정 조립
- `idea_service.py`: 고정 Inbox와 tracked Idea 쓰기
- `content_store.py`: 검증된 조회 결과 게시

## 데이터 소유권

- Vault: tracked Idea, Project와 Service 원본
- `00_Inbox`: Git에서 제외된 Idea 원문
- `/data`: Job, 검색 색인, materialized 결과와 Inbox metadata
- `/config`: schedule과 서버 선택 설정

Vault와 `/data`를 함께 백업해야 pending Idea의 원문과 metadata가 일치한다.

## 실행 경계

Job은 operation registry에 등록된 request schema만 받는다. API, 내장 cron과 외부 Scheduler CLI는 같은 Job API와 queue를 사용한다. Core만 결과를 검증하고 tracked Vault 문서를 commit한다.

queue가 process 내부에 있으므로 container는 web worker 하나만 실행한다. AI와 외부 Scheduler는 선택 기능이며 연결 실패가 일반 조회·검색·Inbox 접수를 중단하지 않는다.

## 쓰기 경계

- Idea 접수는 고정 `00_Inbox`만 사용한다.
- Curate는 검증된 `01_Ideas` 대상만 하나의 commit으로 반영한다.
- Project와 Service 원본은 API로 수정하지 않는다.
- Vault sync는 clean worktree에서 fast-forward만 허용한다.
- API 요청으로 경로, remote, shell 명령, 실행 파일이나 AI prompt를 지정할 수 없다.
