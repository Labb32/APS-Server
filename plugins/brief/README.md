# Briefing 설계

현재 실행 코드는 [공식 briefing 확장](../../extensions/briefing/README.md)에 있다.

Briefing은 진행 중 Project와 운영 중 Service를 읽어 JSON 요약을 만들고, 서버의 고정 HTML template으로 표시한다. 일반 문서 조회는 Core가 담당한다.

- Project·Service 원본을 수정하지 않는다.
- AI가 없으면 새 생성만 비활성화하고 Core API는 유지한다.
- 내부 Scheduler와 외부 AI queue는 같은 입력·결과 schema를 사용한다.
- 결과에는 기준 Vault revision, 생성 시각, 대상 ID와 stale 상태를 포함한다.

package 이름과 기존 API 호환을 정리한 뒤 현재 `extensions/briefing` 구현을 이 계약에 맞춘다.
