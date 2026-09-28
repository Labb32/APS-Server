# ProjectContext

진행 중인 Project는 `briefing_id`와 같은 이름의 context 폴더를 사용한다.

```text
02_Projects/<project>.md
  briefing_id: example-project

05_ProjectContexts/example-project/
├─ .brief/brief.md
└─ tasks/
```

`.brief/brief.md`에는 목표, 현재 상태와 제약을 기록한다. 추가 작업 문서는 필요할 때만 `tasks`에 만든다.

로컬 저장소 경로와 junction·symbolic link 대상은 Git에 저장하지 않는다.
