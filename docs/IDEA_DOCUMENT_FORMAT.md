# Idea document format

APS Server는 Inbox 원문과 추적 Idea를 구분한다. Inbox는 frontmatter 없는 원문이고, 추적 Idea는 Vault Markdown frontmatter의 정규화 필드로 조회 JSON을 만든다. 처리 절차는 [Idea 정리 흐름](IDEA_CURATION.md)에 정리했다.

## Inbox와 추적 경로

```text
00_Inbox/<idea_id>.md     Git에서 제외되는 미정리 Idea staging
01_Ideas/<idea_id>.md     Scheduler 정리와 검증을 마친 추적 Idea
01_Idea_Sets/*.md         추적 Idea Set
```

APS Server는 요청자가 지정한 경로를 사용하지 않고 고정 `00_Inbox`만 쓴다. API로 접수한 파일에는 본문만 저장하고, ID는 파일명에 둔다. 표시·검색·멱등 metadata는 `${APS_DATA_PATH}/ideas/intake.json`에서 관리한다. pending PATCH는 metadata만 바꾸며 원문은 유지한다. pending 조회는 Inbox와 `01_Ideas`를 합치되 출처와 commit 상태를 구분한다. commit 성공 전에는 Inbox 원본을 삭제하지 않는다. 0.2.0에서 생성한 frontmatter Inbox 문서는 처리될 때까지 읽기 호환한다.

## Idea frontmatter

```yaml
---
type: idea
idea_id: idea_0123456789AB
title: 문서 제목
keywords:
  - keyword
summary: >-
  검색 결과에 표시할 짧은 요약.
idea_type: 서비스기획
status: inbox
idea_set_ids: []
created_at: 2026-08-31
updated_at: 2026-08-31
---
```

- `idea_id`는 `idea_`와 대문자 영숫자로 구성한 불변 ID다. 문서 이름이나 경로가 바뀌어도 변경하지 않는다.
- `title`은 사람이 읽는 제목이며 120자 이하를 권장한다.
- `keywords`는 중복을 제거한 3~8개의 짧은 검색어다. 표기와 대소문자를 문서 사이에서 일관되게 유지한다.
- `summary`는 Idea의 목적과 차이를 설명하는 1~2문장이다. 상세 구현 목록을 넣지 않는다.
- `idea_set_ids`에는 승인된 Idea set 소속만 기록한다. 유사도 계산으로 만든 후보는 Vault에 자동 기록하지 않는다.
- `created_at`과 `updated_at`은 ISO 8601 날짜 또는 일시를 사용한다. 조회 JSON의 `updated_at`은 APS가 timezone이 포함된 일시로 정규화한다.
- 본문과 링크는 사람이 읽는 설명이다. 임베딩과 기본 lexical 검색 입력은 `title + keywords + summary`로 제한한다.
- 추적 문서의 `status`와 metadata는 frontmatter에 저장한다. Inbox 문서는 서버 metadata를 통해 `status: inbox`, `commit_status: pending`으로 응답한다.
- `Idempotency-Key`를 보낸 접수에는 서버 metadata에 `intake_key_hash`와 `intake_request_hash`를 저장한다. 정리 commit 후에는 두 hash를 추적 문서에도 보존해 같은 ID로 재요청을 처리한다.

## Idea set frontmatter

```yaml
---
type: idea_set
idea_set_id: idea_set_0123456789AB
title: 관련 Idea 묶음
keywords:
  - keyword
summary: >-
  이 묶음에 공통으로 속하는 문제와 범위.
status: suggested
member_idea_ids:
  - idea_0123456789AB
created_at: 2026-08-31
updated_at: 2026-08-31
---
```

`suggested` set은 APS가 만든 검토 후보이며 원본 Idea의 `idea_set_ids`를 변경하지 않는다. 명시적 승인 흐름이 생긴 뒤 `approved`로 바꾸고 양쪽 membership을 함께 갱신한다. 유사도 점수와 모델 정보는 재생성 가능한 materialized JSON에만 저장한다.
