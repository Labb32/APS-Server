# 구조와 데이터 경계

APS Server 한 개는 한 사용자의 Vault 하나를 연결한다.

```text
Client
  └─ FastAPI: 인증, 조회, Idea 접수, Job API
       ├─ Vault: Idea·Project·Service 원본
       ├─ Data: Job, 검색 색인, materialized 결과, Inbox metadata
       ├─ Queue/Scheduler: 고정 operation 실행
       └─ 선택 기능: AI provider와 공식 확장
```

## 데이터 소유권

- Vault는 추적 Idea, Project와 Service의 원본이다.
- `00_Inbox`는 Git에서 제외된 원문 staging 영역이다.
- `/data`는 Job, 검색 색인, materialized 결과와 서버 상태를 저장한다. pending Idea metadata는 원문과 함께 백업한다.
- 조회 API는 저장된 결과만 읽으며 Job이나 동기화를 자동 실행하지 않는다.

## 쓰기 경계

- API Idea 접수는 고정 `00_Inbox`만 사용한다.
- 추적 Idea·Set은 검증된 Scheduler commit 흐름만 쓴다.
- Project·Service 원본은 API로 수정하지 않는다.
- 요청자가 경로, Git branch·remote, shell, 실행 파일이나 AI 인자를 지정할 수 없다.

Vault sync는 clean worktree의 fast-forward만 허용한다. 자동 merge·reset·강제 checkout·force push는 제공하지 않는다.

## 실행 모델

Job은 allowlist에 등록된 operation과 schema만 받는다. API와 Scheduler는 같은 실행 경로를 사용하고, Core가 결과 형식과 게시 권한을 검증한다. queue가 process 내부에 있으므로 web process는 하나만 운영한다.

공통 검색은 Inbox와 materialized Idea·Set·Project·Service를 `${APS_DATA_PATH}/search/index.json`에 색인한다. 문서 변경분만 갱신하며 source 오류가 발생하면 이전 정상 색인을 stale 상태로 제공한다.

AI와 확장은 선택 사항이다. 사용할 수 없더라도 인증, 문서 조회, Idea 접수와 Core 검색은 계속 동작한다.
