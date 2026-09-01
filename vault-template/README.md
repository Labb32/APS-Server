# APS Vault

APS Server와 연결되는 빈 Vault 템플릿이다.

- `00_Inbox`: APS Server의 Git-ignored Idea staging
- `01_Ideas`: 정리되고 commit된 Idea
- `01_Idea_Sets`: Idea Set 문서
- `02_Projects`: Project 문서
- `03_Services`: Service 문서
- `04_Archives`: 보관 문서
- `05_ProjectContexts`: Project별 작업 context
- `98_Documents`: 운영 문서
- `99_Templates`: 문서 템플릿

`00_Inbox`의 APS Server 소유 문서는 commit하지 않는다. Project와 Service 쓰기는 별도 승인 흐름이 구현되기 전까지 API에서 수행하지 않는다.
