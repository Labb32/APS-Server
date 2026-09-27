# Official Briefing Extension

Project·Service 문서를 읽어 검증 대상 briefing JSON을 만드는 공식 package다. 기본 상태에서는 설치되지 않는다.

```bash
aps extensions install briefing
# 서버 재시작
```

설치 후 briefing operation과 schedule이 등록된다. 시간 변경은 `/data/schedule-overrides.json`에서 관리한다.

- 연결된 Vault를 읽기 전용으로 사용한다.
- Git pull·commit·push와 HTML 생성을 수행하지 않는다.
- 서버가 schema, metadata와 checksum을 검증한 뒤 결과를 게시한다.
- AI 작업은 Core AgentExecutor를 사용하며 provider와 credential을 직접 받지 않는다.

필요 경로는 `02_Projects`, `03_Services`, `05_ProjectContexts/<briefing_id>/.brief/brief.md`다. AI 설정은 [선택형 AI 설정](../../docs/AI_EXECUTION.md)을 따른다.
