# Idea 문서

## 경로

```text
00_Inbox/<idea_id>.md   접수 원문, Git 제외
01_Ideas/<idea_id>.md   정리된 Idea, Git 추적
01_Idea_Sets/*.md       Idea 묶음, Git 추적
```

API 접수 파일은 frontmatter 없이 원문 그대로 저장한다. 표시와 멱등성 metadata는 `${APS_DATA_PATH}/ideas/intake.json`에 저장한다.

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

`idea_id`는 생성 후 바꾸지 않는다. `title`, `summary`, `status`, `updated_at`은 필수다.

AI Curate가 원문을 새 Idea로 만들거나 기존 Idea에 추가하면 본문에 `<!-- aps-source:<idea_id> -->` marker를 남긴다. 보류된 원문은 Inbox에 유지된다.
