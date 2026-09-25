# Core document search

APS Server는 외부 AI, GPU, vector DB 없이 Inbox·Idea·Idea Set·Project·Service를 검색한다. `POST /v1/search`만 공통 검색이며 요청자가 Vault 경로나 임의 실행 지시를 전달할 수 없다. 기존 Idea 전용 검색과 유사도 API는 그대로 유지한다.

로컬 인덱스는 최대 100,000개 문서와 64 MiB 파일까지만 읽는다. 체크섬, 필수 필드, 중복 키, 임베딩 차원과 유한 숫자를 검증한 뒤 사용한다.

## 검색 방식

- 제목 55%, 키워드 30%, 요약 15%의 lexical 점수와 로컬 임베딩 cosine 점수를 75:25로 결합한다.
- `aps-hash-subword-v1-256`은 APS Server에 포함된 256차원 signed feature hashing 구현이다. 별도 모델 파일·다운로드·런타임 의존성·외부 라이선스가 없다.
- Unicode NFKC와 영문·숫자·한글 token, 2~3자 subword를 사용해 한국어 조사나 복합어의 일부 일치를 반영한다. 학습된 언어 모델이 아니므로 문맥 동의어 품질은 제한적이다.
- 임베딩 계산에 실패하면 lexical 결과를 반환하고 `search_mode: lexical_fallback`, `embedding_model: null`로 표시한다. 문자열 유사도를 임베딩으로 표기하지 않는다.

## 색인 수명주기

색인은 `${APS_DATA_PATH}/search/index.json`에 저장된다. 각 요청에서 Project·Service·tracked Idea catalog와 현재 Inbox를 비교한다. Vault commit, 문서 hash, Inbox revision, 모델 version이 같으면 기존 vector와 생성 시각을 재사용한다. 변경된 문서만 다시 계산하고 삭제된 문서는 제거한다.

새 색인은 임시 파일을 완성한 뒤 원자적으로 교체한다. source 문서가 잘못된 경우 이전 정상 색인을 `stale: true`로 제공한다. 저장 색인의 checksum이 깨졌거나 모델 version이 바뀌면 source에서 전체 재구축한다. 첫 구축에도 source를 읽을 수 없으면 `500 SEARCH_INDEX_INVALID`다.

현재 한도는 문서 100,000개, 요청 query 200자, 한 페이지 100개, offset 10,000이다. 문서당 256차원 vector를 JSON으로 저장하므로 대규모 운영은 별도 `aps-index` 서비스 범위다.

## API

```http
POST /v1/search
Authorization: Bearer <operator-or-viewer-token>
Content-Type: application/json

{
  "query": "검색 색인",
  "collections": ["inbox", "idea", "idea_set", "project", "service"],
  "statuses": ["organized", "In_Progress"],
  "offset": 0,
  "limit": 20
}
```

빈 `collections`와 `statuses`는 전체를 뜻한다. 필터 값은 정확히 일치한다. 응답은 `total`, 현재 `offset`·`limit`, 다음 페이지가 있을 때 `next_offset`과 결과별 collection·논리 ID·점수·`matched_by`를 제공한다.
