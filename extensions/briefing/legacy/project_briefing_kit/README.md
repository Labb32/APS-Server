# Project Briefing Kit

새 프로젝트를 APS 브리핑에 게시할 때 사용하는 컨텍스트 템플릿이다. 실제 문서는 `05_ProjectContexts/<briefing_id>`에 두고, 개발 프로젝트에는 선택적으로 디렉터리 링크를 만든다.

## 게시 순서

1. `05_ProjectContexts/<briefing_id>`를 만든다.
2. 이 kit의 `.brief`를 복사하고 `brief.md`의 문서 경로와 선정 규칙을 채운다.
3. 자유로운 이름의 Task 문서 폴더를 함께 둔다.
4. `02_Projects/<프로젝트>.md`에 `status: In_Progress`와 `briefing_id`를 설정한다.
5. 개발 프로젝트에서 `.brief`와 Task 폴더를 ignore한다.
6. 필요하면 현재 Vault 템플릿의 [`05_ProjectContexts/README.md`](../../../../vault-template/05_ProjectContexts/README.md)에 따라 링크를 만든다.
7. `py scripts/daily_briefing.py --project <briefing_id> --dry-run --no-pull`로 확인한다.

브리핑은 로컬 개발 프로젝트나 `.aps.local.json` 경로가 없어도 실행된다. `.aps.local.json`은 링크할 프로젝트 경로, 사용자 지정 실행기와 병렬도만 기록한다.

```json
{
  "projects": {
    "my-project": {
      "path": "~/Projects/my-project",
      "mounts": [".brief", "tasks"]
    }
  },
  "runner": {
    "command": [],
    "timeout_seconds": 600,
    "parallel_projects": 3
  }
}
```

상세 실행 방법은 보존된 [`DAILY_BRIEFING.md`](../docs/DAILY_BRIEFING.md)를 참고한다.
