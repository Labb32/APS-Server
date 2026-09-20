# Security Policy

APS Server는 개인 Vault, 인증 token과 선택형 AI provider credential을 다루는 네트워크 서비스다. 현재 `0.1.x`는 개인 서버 검증 단계의 pre-release이며, 인터넷에 직접 노출하는 운영을 권장하지 않는다.

## 지원 범위

| Version | Security updates |
|---|---|
| `0.1.x` | 개인 서버 QA 기간 동안 최신 commit만 지원 |
| `< 0.1` | 지원하지 않음 |

공개 release 이후에는 최신 minor release와 지원 종료 일정을 이 문서에 명시한다.

## 취약점 제보

인증 우회, Vault 경로 탈출, 임의 명령 실행, secret 노출 또는 승인되지 않은 Git 쓰기를 발견했다면 공개 Issue를 만들지 않는다. 이 저장소의 GitHub **Security → Report a vulnerability** 기능으로 비공개 제보한다. 저장소 공개 전에 관리자는 GitHub private vulnerability reporting을 활성화해야 한다.

제보에는 가능한 범위에서 다음 내용을 포함한다.

- 영향을 받는 version 또는 commit
- 재현 조건과 최소 재현 절차
- 예상 영향과 공격자가 필요한 권한
- log와 응답에서 token, credential, 개인 Vault 내용은 제거한 증거
- 알려진 완화책

유효한 제보를 확인하면 접수 사실, 영향 범위와 수정 계획을 비공개 채널로 공유한다. 수정과 배포 준비가 끝나기 전에는 상세 재현 절차를 공개하지 않는다.

## 운영자 보안 기준

- `APS_OPERATOR_TOKEN`, `APS_VIEWER_TOKEN`, `APS_SCHEDULER_TOKEN`에 서로 다른 충분히 긴 무작위 값을 사용한다.
- 설정된 API token은 각각 32자 이상이어야 하며 역할 간 같은 값을 재사용할 수 없다.
- `.env`, provider API key와 Git credential을 Git 또는 container image에 포함하지 않는다.
- Git credential은 `/git-auth` 전용 volume에만 저장하고 host에서 해당 Docker volume 접근을 제한한다. HTTP credential store는 token을 복원 가능한 형태로 저장하므로 volume backup과 접근 권한도 secret으로 취급한다. 원격 URL에는 token이나 password를 넣지 않는다.
- 원격 Vault에서 경계를 벗어나는 symlink는 문서로 읽지 않으며 Vault 문서 하나의 크기는 2 MiB로 제한한다.
- 기본 `127.0.0.1` bind를 유지하고 외부 접근에는 TLS reverse proxy 또는 개인 VPN을 사용한다.
- 브라우저용 HTML upstream에 token을 주입한다면 proxy 자체 인증 없이 공개하지 않는다.
- `/vault`와 `/data`의 host 권한과 backup을 별도로 관리한다.
- 공식 extension만 설치하고 image tag와 AI model version을 운영자가 고정한다.
- Vault sync 실패, dirty worktree와 diverged branch를 자동 merge·reset·force push로 해결하지 않는다.
- 자동 push를 켠 경우에도 현재 tracking upstream에 대한 fast-forward push만 허용하며 push 실패 뒤 local commit을 운영자가 확인한다.
- container는 non-root UID/GID `10001:10001`, read-only root filesystem, 전체 Linux capability drop과 `no-new-privileges`로 실행한다.
- 공식 extension은 API token과 Git 환경을 상속하지 않지만 AI 작업에는 provider credential이 필요하다. 설치된 extension과 `/data` volume을 신뢰 경계로 취급한다.
- 현재 커뮤니티 extension은 지원하지 않는다. 제3자 package를 허용하려면 별도 격리 runner, 검증된 package·서명, Core가 강제하는 최소 capability와 권한 확대 시 승인, 원본 Vault·Git·secret 비노출, 제한된 network broker·자원 한도·감사를 먼저 구현해야 한다. 문서나 AI 출력은 권한 근거로 사용하지 않는다.
- 공개 reverse proxy에서 요청 body 크기 제한과 rate limiting을 적용한다. 정적 API token 회전에는 container 재시작이 필요하다.

배포 전 검증은 [Pre-release QA](docs/PRE_RELEASE_QA.md)를 따른다.
