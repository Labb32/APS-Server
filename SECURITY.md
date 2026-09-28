# 보안 안내

## 취약점 제보

인증 우회, 경로 노출, 명령 실행, secret 노출 또는 허용되지 않은 Git 쓰기는 공개 Issue 대신 GitHub의 **Security → Report a vulnerability**로 제보한다.

영향받는 버전과 최소 재현 절차를 포함하고 token, credential, Vault 원문은 제거한다.

## 운영 원칙

- 역할마다 서로 다른 32자 이상의 무작위 token을 사용한다.
- `.env`, AI key와 Git credential을 저장소·image·로그에 넣지 않는다.
- 기본 localhost bind를 유지하거나 TLS reverse proxy·개인 VPN 뒤에서 공개한다.
- `/vault`, `/data`, `/git-auth`를 분리하고 함께 백업한다.
- 공식 extension만 설치하고 image와 AI model 버전을 고정한다.
- Vault 충돌을 merge, reset 또는 force push로 자동 해결하지 않는다.
- container의 non-root, read-only filesystem, capability drop 설정을 유지한다.

배포 방법은 [설치와 운영](docs/CONTAINER_DEPLOYMENT.md)을 참고한다.
