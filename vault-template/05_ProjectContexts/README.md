# ProjectContext 운영

진행 중 Project는 `02_Projects` frontmatter의 `briefing_id`와 같은 폴더를 사용한다.

```text
02_Projects/<project>.md
  briefing_id: example-project

05_ProjectContexts/example-project/
├─ .brief/
│  └─ brief.md
└─ tasks/
```

`.brief/brief.md`는 Project 목표, 현재 상태, 제약과 브리핑 규칙을 담는 필수 입력이다. `tasks` 등 추가 문서는 필요할 때 만든다.

개발 프로젝트에서 같은 문서를 직접 편집해야 하는 기기만 `.aps.local.json`에 로컬 경로를 기록하고 junction 또는 symbolic link를 만든다. 로컬 절대경로와 link 대상은 Git에 commit하지 않는다.
