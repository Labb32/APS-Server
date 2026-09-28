# APS Vault

Idea, Project와 Service를 Markdown으로 관리하는 APS Server용 Vault다.

## 구조

| 경로 | 내용 |
|---|---|
| `00_Inbox` | 접수된 Idea 원문, Git 제외 |
| `01_Ideas` | 정리된 Idea |
| `01_Idea_Sets` | 관련 Idea 묶음 |
| `02_Projects` | Project |
| `03_Services` | 운영 Service |
| `04_Archives` | 보관 문서 |
| `05_ProjectContexts` | Project 작업 문맥 |
| `99_Templates` | 문서 template |

새 문서는 `99_Templates`의 같은 유형을 복사해 작성한다. ID는 만든 뒤 바꾸지 않는다.

## Git

- 동기화는 fast-forward만 사용한다.
- 충돌은 내용을 확인한 뒤 수동으로 해결한다.
- 자동 merge, reset, force checkout과 force push를 사용하지 않는다.
- `00_Inbox` 내용과 `.aps.local.json`은 commit하지 않는다.

## 백업

`00_Inbox`는 Git에 포함되지 않는다. Vault와 APS Server의 `/data`를 함께 백업한다.

실제 token, credential, 개인 경로 또는 대용량 로그를 Vault에 저장하지 않는다.
