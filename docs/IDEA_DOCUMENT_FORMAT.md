# Idea 문서 형식

## 저장 경로

```text
00_Inbox/<idea_id>.md   Git 제외 원문
01_Ideas/<idea_id>.md   검증 후 추적하는 Idea
01_Idea_Sets/*.md       추적하는 Idea Set
```

API 접수 파일은 frontmatter 없이 원문 그대로 저장한다. 표시용 metadata와 idempotency 정보는 `${APS_DATA_PATH}/ideas/intake.json`에 둔다.

## Curate

AI가 활성화된 경우 `ideas.curate`는 각 Inbox 원문을 다음 중 하나로 분류한다.

- 비슷한 Inbox 원문을 합쳐 새 Idea 생성
- 같은 의미의 기존 Idea 본문에 추가
- 판단이 어려운 원문 보류

새 Idea ID는 그룹의 source ID 중 사전순 최솟값을 사용한다. 본문에는 `<!-- aps-source:<idea_id> -->` marker를 남겨 출처를 기록하고 재시도 중복을 막는다. 기존 Idea에 추가할 때는 `updated_at` 외의 frontmatter를 유지한다. Idea Set 생성은 별도 작업이다.

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
merge_source_idea_ids:
  - idea_EXAMPLE
created_at: 2026-09-01
updated_at: 2026-09-01T00:00:00+00:00
---
```

`idea_id`는 생성 후 바꾸지 않는다. `title`, `summary`, `status`, `updated_at`은 필수다.

## Idea Set

Idea Set은 `idea_set_id`, `title`, `summary`, `status`, `member_idea_ids`, `created_at`, `updated_at`을 가진다. `member_idea_ids`는 존재하는 Idea만 참조해야 한다.
