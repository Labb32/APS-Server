# Idea 저장 형식

## 경로

```text
00_Inbox/<idea_id>.md     Git에서 제외된 원문
01_Ideas/<idea_id>.md     정리·검증된 추적 Idea
01_Idea_Sets/*.md         추적 Idea Set
```

API 접수 파일은 frontmatter 없이 본문만 저장한다. ID는 서버가 만든 파일명에 있고, 표시·검색·멱등 metadata는 `${APS_DATA_PATH}/ideas/intake.json`에 둔다. pending PATCH는 metadata만 수정하며 원문을 바꾸지 않는다. 0.2.0 형식의 Inbox 문서는 처리될 때까지 읽을 수 있다.

## 추적 Idea

```yaml
---
type: idea
idea_id: idea_EXAMPLE
title: 문서 제목
keywords:
  - keyword
summary: 짧은 설명
idea_type: general
status: incubator
idea_set_ids: []
created_at: 2026-09-01
updated_at: 2026-09-01T00:00:00+00:00
---
```

`idea_id`는 생성 후 바꾸지 않는다. `title`, `summary`, `status`, `updated_at`은 필수이고 ID와 Set 참조는 catalog 전체에서 유효해야 한다.

## Idea Set

```yaml
---
type: idea_set
idea_set_id: idea_set_EXAMPLE
title: 관련 Idea 묶음
keywords:
  - keyword
summary: 묶음 설명
status: suggested
member_idea_ids:
  - idea_EXAMPLE
created_at: 2026-09-01
updated_at: 2026-09-01T00:00:00+00:00
---
```

Set은 한 개 이상의 기존 Idea ID를 참조한다. `suggested` Set은 후보이며 원본 Idea의 `idea_set_ids`를 자동 변경하지 않는다.
