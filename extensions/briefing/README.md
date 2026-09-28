# Briefing 확장

AI가 활성화된 APS Server에서 Project와 Service 문서를 요약해 JSON으로 게시한다. 게시된 결과는 JSON 또는 HTML로 조회할 수 있다.

## 설치

```bash
docker compose exec aps-server aps extensions install briefing
docker compose restart aps-server
```

이미 설치한 경우 같은 명령으로 공식 최신 버전으로 갱신한다. 설치 상태와 AI 사용 가능 여부는 `GET /v1/extensions`, `GET /v1/operations`에서 확인한다.

## 생성

내장 Scheduler는 다음 작업을 실행한다. 외부 Scheduler를 설정해도 같은 schedule과 Job API를 사용한다.

| Schedule | 기본 시각 | 결과 |
|---|---:|---|
| `briefing.daily-refresh` | 매일 06:00 | 일일 요약과 Project별 요약 |
| `briefing.service-maintenance` | 매일 05:15 | Service 유지보수 현황 |

수동 실행은 `POST /v1/jobs`로 요청한다.

```json
{
  "operation": "briefing.daily",
  "input": {},
  "context": {}
}
```

특정 Project만 갱신하려면 `briefing.project`와 `context.project_ids`를 사용한다. AI가 꺼져 있으면 모든 briefing operation과 schedule이 비활성화된다.

## 조회

| Path | 내용 |
|---|---|
| `/v1/content/briefing/daily` | 일일 briefing |
| `/v1/content/projects/{project_id}/briefing` | Project briefing |
| `/v1/content/services/maintenance` | Service 유지보수 현황 |

기본 응답은 JSON이다. `?format=html`을 붙이면 같은 데이터를 HTML로 받는다.

## HTML 사용자 설정

기본 템플릿은 서버 패키지에 포함된다. 일부 파일만 별도 디렉터리에 복사해 수정한 뒤 경로를 설정하면 나머지는 기본 파일을 사용한다.

```dotenv
APS_HTML_TEMPLATES_PATH=/config/templates
```

briefing에서 사용하는 파일은 `daily_briefing.html`, `project_briefing.html`, `service_maintenance.html`, `project_catalog.html`, `content.css`이다. 컨테이너에서는 호스트의 사용자 템플릿 디렉터리를 `/config/templates`에 마운트한다. 설정 변경 후 서버를 다시 시작한다.
