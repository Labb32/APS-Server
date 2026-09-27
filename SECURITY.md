# Security Policy

`0.2.x`는 개인 서버용 beta다. 최신 `0.2.x` release만 보안 수정을 받는다.

## 취약점 제보

인증 우회, 경로 탈출, 임의 명령 실행, secret 노출이나 승인되지 않은 Git 쓰기는 공개 Issue 대신 GitHub **Security → Report a vulnerability**로 제보한다. 영향 version, 최소 재현 절차와 완화책을 포함하고 token·credential·Vault 원문은 제거한다.

## 운영 기준

- 역할별로 서로 다른 32자 이상의 무작위 API token을 사용한다.
- `.env`, AI key와 Git credential을 Git, image와 로그에 넣지 않는다.
- 기본 localhost bind를 유지하고 외부 접근에는 TLS reverse proxy나 개인 VPN을 사용한다.
- proxy에 요청 크기 제한과 rate limit을 적용한다.
- `/vault`, `/data`, `/git-auth`를 분리하고 접근 권한과 backup을 관리한다.
- 공식 확장만 설치하고 image tag와 AI model을 고정한다.
- Vault sync 오류를 merge·reset·force push로 자동 해결하지 않는다.
- read-only root filesystem, non-root 사용자, capability drop과 `no-new-privileges` 설정을 유지한다.

배포 확인 절차는 [Docker 배포](docs/CONTAINER_DEPLOYMENT.md)를 따른다.
