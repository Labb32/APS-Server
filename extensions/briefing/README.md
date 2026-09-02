# APS Official Briefing Extension

APS Vault의 기존 `scripts/daily_briefing.py`와 관련 문서를 APS Server 공식 확장으로 이전한 작업 폴더다. 원본 Vault 파일은 삭제하거나 수정하지 않았다.

이 디렉터리는 설치 가능한 공식 package 원본이며 APS Server 기본 상태에서는 활성화되지 않는다.

```text
aps extensions install briefing
# APS Server 재시작
```

재시작 후 manifest의 세 Operation과 `briefing.daily-refresh`, `briefing.service-maintenance` Schedule이 자동 등록된다. 시간 변경은 설치 package가 아니라 `/data/schedule-overrides.json`에서 수행한다.

## 현재 실행 경계

- APS Server가 고정된 이 확장 진입점만 실행한다.
- APS Server가 연결된 Vault 절대경로를 `--vault`로 전달한다.
- 확장은 Vault를 읽기 전용으로 사용한다.
- 확장은 Git pull, commit, push와 HTML 생성을 수행하지 않는다.
- 출력은 일일 브리핑 canonical `data` 후보 JSON뿐이다.
- APS Server가 최종 schema, metadata와 checksum을 검증하고 ContentStore에 게시한다.
- 프로젝트별 AI 실행은 고정 `aps_server.ai_bridge`를 통해 Core AI gateway에 위임한다.

## 디렉터리

```text
briefing/
├─ manifest.json
├─ entrypoint.py
├─ schemas/
│  └─ briefing_response.schema.json
└─ legacy/
   ├─ daily_briefing.py
   ├─ project_briefing_kit/
   ├─ web/
   └─ docs/
```

`legacy/`는 Vault에서 복사한 원본과 문서다. 활성 진입점은 `entrypoint.py`이며 legacy 모듈의 문서 읽기와 구조화 응답 parsing 부분만 재사용한다.

## 확인된 의존성

- Python 3.11 이상 표준 라이브러리
- 연결된 APS Vault의 `02_Projects`, `03_Services`, `05_ProjectContexts`
- Project 문서의 `briefing_id`
- `05_ProjectContexts/<briefing_id>/.brief/brief.md`
- APS Core AI bridge와 `schemas/briefing_response.schema.json`

다음 legacy 기능은 활성 진입점에서 사용하지 않는다.

- 자체 Git pull
- `.aps.local.json`의 사용자 지정 runner command
- HTML 생성과 브라우저 실행
- Vault 내부 script 위치를 기준으로 한 실행

provider, endpoint, model과 credential은 APS Server 설정에만 존재한다. 확장은 이를 요청 인자나 manifest로 받지 않는다. 지원 provider는 [AI provider 설정](../../docs/AI_PROVIDERS.md)을 따른다.

이 저장소에 포함된 `briefing` package는 APS Server 배포물의 일부로서 루트 [Apache License 2.0](../../LICENSE)과 [NOTICE](../../NOTICE)를 따른다.
