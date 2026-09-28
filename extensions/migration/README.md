# Migration 확장

Vault 문서 전체를 ZIP archive로 내보내거나 다른 APS Server에 가져온다. Git 저장소, `.env`, 서버 설정, 플러그인, Job 데이터, credential과 기기별 편집기 상태는 포함하지 않는다.

## 설치

```bash
docker compose exec aps-server aps extensions install migration
docker compose restart aps-server
```

## 내보내기

```bash
curl -X POST http://127.0.0.1:8080/v1/migration/exports \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
```

응답의 `download_url`에서 ZIP을 내려받는다.

기본 archive 제한은 압축 전후 256MB이며 `APS_MIGRATION_MAX_ARCHIVE_BYTES`로 조정한다.

## 가져오기

ZIP을 업로드하면 경로와 파일 해시를 검사하고 migration proposal을 만든다.

```bash
curl -X POST http://127.0.0.1:8080/v1/migration/imports \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: application/zip" \
  --data-binary @aps-vault.zip
```

응답의 `proposal_id`를 확인한 뒤 명시적으로 적용한다.

```bash
curl -X POST http://127.0.0.1:8080/v1/migration/imports/<proposal_id>/apply \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirmation":"<proposal_id>"}'
```

적용 전에 현재 Vault archive를 자동 생성한다. Proposal을 만든 뒤 Vault commit이 바뀌면 적용이 거부된다.
