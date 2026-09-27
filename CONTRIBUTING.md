# Contributing

변경은 공개 API와 Vault 안전 경계를 유지해야 한다.

```powershell
py -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/uvicorn aps_server.main:app --host 127.0.0.1 --port 8080
```

- 하나의 pull request에는 하나의 목적만 담는다.
- API 변경 시 관련 문서와 `specs/aps-api.openapi.json`을 함께 갱신한다.
- 임의 shell·실행 경로·AI 인자·요청자 지정 Vault 경로를 API에 추가하지 않는다.
- Vault sync에 자동 merge·reset·force checkout·force push를 추가하지 않는다.
- in-process queue를 사용하는 동안 web process를 여러 개 실행하지 않는다.
- 실행한 API·권한·Job 흐름과 결과를 pull request에 기록한다.

저장소 지침에 따라 maintainer 요청 없이 테스트 파일이나 테스트 케이스를 추가하지 않는다. 제출한 코드는 [Apache License 2.0](LICENSE) 조건으로 제공한다.
