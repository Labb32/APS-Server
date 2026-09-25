# APS Server 구조

한 APS Server는 사용자 한 명과 Vault 하나를 담당한다. Vault는 문서의 원본이고 Server는 인증, API, Job, 검증된 파생 결과를 소유한다. [베타 목표](PROJECT_PLAN.md)는 구현 완료 상태가 아니며, 현재 API는 [API Reference](API_REFERENCE.md)를 따른다.

```text
클라이언트 → 인증된 API → 고정 operation/Job → Core handler
                                      ├─ Vault 읽기·안전 동기화
                                      ├─ 선택 AI/공식 확장
                                      └─ 결과 검증·게시/허용된 commit
클라이언트 → Content GET → 저장된 JSON → JSON 또는 고정 HTML template
```

## Vault와 쓰기

Vault는 Idea, Idea Set, Project, Service와 관련 Markdown·첨부를 보관한다. Git 모드 동기화는 clean worktree에서 fast-forward만 허용한다. 자동 merge·reset·강제 checkout·force push는 하지 않는다.

Inbox 접수와 pending 수정은 서버가 관리하는 Git-ignored `00_Inbox`에만 기록한다. 자동 tracked Idea/Set 쓰기는 검증된 `01_Ideas`·`01_Idea_Sets` 대상 Scheduler commit gate를 통과한다. tracked Idea 직접 `PATCH`는 `409 IDEA_TRACKED_UPDATE_DISABLED`로 거부한다. Project/Service 원본 변경은 proposal branch·diff·명시적 승인 흐름 전까지 막는다.

Core 검색은 materialized catalog와 현재 Inbox에서 고정 collection 문서를 만들고 `${APS_DATA_PATH}/search/index.json`에 증분 색인을 저장한다. lexical 점수와 내장 subword 임베딩을 결합하며 외부 AI·GPU·Vector DB를 요구하지 않는다. source 오류 시 이전 정상 색인을 stale 결과로 유지한다.

## Core 실행

Core는 Bearer token 역할, 고정 API·operation schema, bounded in-process queue, cron, Vault sync, 결과 schema/checksum, 원자적 게시, Artifact와 감사 정보를 관리한다. API와 cron은 같은 Job 경로를 사용한다. 조회는 저장된 결과를 읽을 뿐 AI·동기화·생성 Job을 시작하지 않는다. 생성 실패 시 이전 정상 결과를 보존한다.

기본 AI provider 목표 설정은 `none`이다. 선택 AI는 [Agent 실행 설계](AGENT_EXECUTOR_DESIGN.md)의 제한된 task와 Tool만 사용한다. 외부 AI 큐를 연결해도 Server가 결과와 기준 Vault revision을 검증하고 게시·commit을 결정한다. 외부 worker에 Vault/Git 쓰기 권한을 주지 않는다. in-process queue가 남는 동안 web process는 하나다.

JSON은 정규화 metadata와 필요한 Markdown 본문을 포함하는 목표 계약을 따른다. HTML은 같은 검증된 JSON을 서버의 사전 등록 template으로 표시하며 AI가 HTML·CSS·JavaScript를 만들지 않는다. 일반 문서 조회와 브리핑 결과는 응답 의미를 구분한다. [API 목표 계약](CONTENT_API.md)을 따른다.

## 확장과 aps-index

공식 확장은 Core의 인증·Job·결과 검증 경계를 사용한다. 현재 설치 가능한 package는 `briefing`이다. 목표 베타의 `migration` archive 업로드/복원과 `service-security` 외부 조회는 현행 read-only 확장 host의 권한이 아니며 각각 제한된 관리·네트워크 capability가 필요하다. [공식 확장 계획](EXTENSION_PLAN.md)을 따른다. 커뮤니티 확장은 현재 지원하지 않으며 공개 조건은 [보안 정책](../SECURITY.md)에 있다.

Core 검색은 로컬 lexical·소형 임베딩을 목표로 한다. 별도 `aps-index`는 Vault 원본을 유지하는 검색 backend로 시작할 수 있다. 선택적인 Inbox/Idea DB 원본 모드는 소유권·이관·백업·Markdown export·복귀 계약을 갖춘 뒤 활성화한다. DB 원본이 없을 때 Vault 검색이 정상 대체한다고 표시하지 않는다. [aps-index 설계](../plugins/aps-index/README.md)를 따른다.

## 배포 경계

현재 인증은 `operator`, `viewer`, `scheduler`의 서로 다른 정적 token을 사용한다. IP·Origin·proxy header는 신원 근거가 아니다. 기본 localhost bind를 유지하고 외부 접근에는 TLS reverse proxy 또는 개인 VPN을 사용한다. Vault, Job data와 Git 인증은 별도 영속 volume에 둔다. [배포 안내](CONTAINER_DEPLOYMENT.md)를 따른다.
