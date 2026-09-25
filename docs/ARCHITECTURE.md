# APS Server 구조

APS Server는 사용자 한 명의 APS Vault를 연결한다. Vault는 Idea·Project·Service 문서의 원본이며, Server는 인증·API·Job·검증된 파생 결과를 관리한다. 현재 제공 API는 [API Reference](API_REFERENCE.md), 제품 범위는 [목표 베타](PROJECT_PLAN.md)를 따른다.

```text
Client → 인증된 API → 고정 operation/Job → Core → Vault·선택 AI·확장
                                  ↓
                         검증된 JSON·Artifact·허용된 commit
Client → Content API → 저장 결과 → JSON 또는 고정 HTML template
```

## 쓰기와 동기화

- Inbox 접수와 pending 수정은 서버가 관리하는 Git-ignored `00_Inbox`에 한정한다.
- 추적 Idea/Set 변경은 검증된 `01_Ideas`·`01_Idea_Sets` 대상 Scheduler commit 경로만 사용한다.
- Project·Service 원본 변경은 proposal, diff, 명시적 승인 흐름이 준비될 때까지 허용하지 않는다.
- Git 동기화는 clean worktree의 fast-forward만 허용한다. 자동 merge·reset·강제 checkout·force push는 하지 않는다.

## 실행과 검색

API와 Scheduler는 같은 고정 Job 경로를 사용한다. Core가 입력, 결과 schema, Vault revision과 게시·commit 권한을 검증한다. 조회는 저장 결과만 읽으며 생성 Job을 시작하지 않는다. in-process queue를 쓰는 동안 web process는 하나다. AI 설정은 [AI 실행·provider 안내](AI_EXECUTION.md)에 있다.

공통 검색은 materialized catalog와 현재 Inbox를 고정 collection으로 색인한다. 색인은 `${APS_DATA_PATH}/search/index.json`에 저장되고, source 오류 때 이전 정상 색인을 `stale`로 반환한다. 검색 계약과 한도는 [Core 검색](SEARCH.md)을 따른다.

## 확장과 배포

현재 설치 가능한 공식 확장은 `briefing`이다. `migration`과 `service-security`는 설계 단계이며, 별도 `aps-index` 서비스도 아직 연결 계약이 구현되지 않았다. 상세는 [확장 계획](EXTENSION_PLAN.md)과 [플러그인 목록](../plugins/README.md)을 따른다.

API token은 `operator`, `viewer`, `scheduler` 역할별로 분리한다. 기본 배포는 localhost에 bind하며 외부 접근은 TLS reverse proxy나 개인 VPN을 사용한다. Vault·Job data·Git 인증정보는 각각 영속 저장한다. [배포 안내](CONTAINER_DEPLOYMENT.md)를 참고한다.
