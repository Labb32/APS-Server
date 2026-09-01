# APS Static Web UI Contract

`dashboard.html`과 `briefing.html`이 공유하는 정적 화면 계약입니다. HTML 구조는 AI 응답이 아니라 `scripts/daily_briefing.py`의 고정 렌더러가 결정합니다.

## 화면 역할

- `dashboard.html`: APS 프로젝트와 운영 서비스의 장기 현황표
- `briefing.html`: `--html` 실행 시 생성되는 당일 브리핑 결과

두 파일은 같은 폴더에서 상대경로로 연결합니다. `briefing.html`은 실행할 때 다시 만드는 로컬 생성물이므로 Git에서 추적하지 않으며 `python3 scripts/daily_briefing.py --html`로 갱신합니다.

## 허용 컴포넌트

- 검색 입력
- 프로젝트·서비스 상태 필터
- 티어·기한·이름 정렬
- `<details>` 기반 프로젝트 상세
- 로컬 완료 체크박스
- 후속 질문 맥락 및 재실행 명령 클립보드 복사
- 원본 Markdown 문서 상대경로 링크
- 빈 결과와 비정상 결과 메시지

## 데이터 계약

Codex 응답은 `scripts/briefing_response.schema.json`의 세 필드만 받습니다.

```json
{
  "today_tasks": ["오늘 할 일"],
  "notes": ["기타 특이사항"]
}
```

티어, 형태, 기한과 문서 경로는 Codex가 아니라 `02_Projects` 원본 메타데이터에서 가져옵니다. 서비스 점검 정보도 `03_Services` 원본 메타데이터에서 계산합니다.

## 상태 저장과 원본 경계

- 체크박스 상태는 브리핑 날짜·`briefing_id`·작업 순번을 키로 브라우저 `localStorage`에만 저장합니다.
- 완료 체크는 APS Markdown이나 프로젝트 저장소를 수정하지 않습니다.
- 후속 질문은 자동 실행하지 않고 현재 브리핑 맥락을 클립보드에 복사합니다.
- 비정상 프로젝트의 재실행 버튼도 명령을 복사할 뿐 실행하지 않습니다.

## 보안 경계

- 외부 스크립트, 스타일시트, 폰트와 네트워크 요청을 사용하지 않습니다.
- 프로젝트·서비스·Codex 출력은 HTML에 넣기 전에 이스케이프합니다.
- AI가 반환한 HTML이나 JavaScript를 실행하지 않습니다.
- 정적 HTML은 로컬 명령 실행과 원본 파일 쓰기 권한을 갖지 않습니다.
- MDBoard가 완성되기 전까지 모든 상호작용은 읽기, 로컬 상태 저장과 클립보드 전달로 제한합니다.

