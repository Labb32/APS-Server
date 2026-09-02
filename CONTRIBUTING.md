# Contributing to APS Server

APS Server는 FastAPI API, 단일 프로세스 queue, Scheduler, Vault 안전 경계와 공식 extension runtime을 함께 관리한다. 기여는 현재 공개 API와 보안 원칙을 보존해야 한다.

## 시작하기

1. 큰 API 변경, Vault 쓰기 또는 extension 계약 변경은 구현 전에 Issue에서 범위를 합의한다.
2. 하나의 pull request에는 하나의 목적만 포함한다.
3. `README.md`, 관련 `docs/` 문서와 `specs/aps-api.openapi.json`을 구현과 함께 갱신한다.
4. 실제 실행한 API·권한·컨테이너 흐름과 결과를 pull request에 기록한다.

```powershell
py -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/uvicorn aps_server.main:app --host 127.0.0.1 --port 8080
```

## 변경 불가 원칙

- 자유 형식 agent query와 요청자 지정 Vault path를 추가하지 않는다.
- API를 통해 shell command, executable path, AI provider credential 또는 Codex 인자를 받지 않는다.
- Vault sync에 자동 merge, reset, force checkout 또는 force push를 추가하지 않는다.
- Idea 이외의 tracked Vault 쓰기는 proposal branch와 명시적 승인 흐름 전까지 추가하지 않는다.
- in-process queue를 유지하는 동안 web process를 여러 개로 늘리지 않는다.
- 공식 package allowlist를 우회하는 community 또는 원격 extension 설치를 추가하지 않는다.

## 검증

현재 MVP 단계에서는 maintainer가 명시적으로 요청하지 않는 한 새 test file이나 test case를 추가하지 않는다. 대신 변경과 직접 관련된 API, 인증, 권한, Job, Scheduler와 container 실행 흐름을 수행하고 재현 가능한 명령과 결과를 남긴다. 기본 점검 범위는 [Pre-release QA](docs/PRE_RELEASE_QA.md)를 참고한다.

## 기여 라이선스

별도 서면 고지가 없는 한 이 저장소에 제출한 기여는 [Apache License 2.0](LICENSE) 제5조에 따라 프로젝트와 같은 조건으로 제공된다. 기여자는 제출할 권리가 있는 코드와 문서만 포함해야 하며, 외부 자료를 포함하면 원본과 라이선스를 명확히 기록한다.
