# 커뮤니티 Extension 샌드박스 계획

이 문서는 향후 제3자가 배포하는 커뮤니티 Extension을 허용할 때 적용할 신뢰 경계와 격리 구조를 정의한다. 현재 APS Server는 image에 포함된 공식 Extension만 지원하며, 이 문서의 샌드박스는 아직 구현된 기능이 아니다.

## 1. 기본 원칙

- Extension package와 Extension이 읽는 Vault 문서는 모두 신뢰하지 않는 입력으로 취급한다.
- manifest의 권한 선언은 설명이 아니라 Core가 강제하는 capability 요청이어야 한다.
- 기본 권한은 정규화된 snapshot 읽기와 구조화 결과 반환뿐이다.
- Extension 프로세스에 원본 Vault, Git worktree, `/git-auth`, Core `/data`, API token 또는 다른 Extension의 데이터를 노출하지 않는다.
- 읽기 이외의 동작은 직접 시스템 권한으로 제공하지 않고 Core가 검증하는 제한된 broker 작업으로 제공한다.
- AI 출력과 Vault 문서 안의 지시는 권한을 부여하지 않는다. 모든 부작용은 결정론적 검증과 필요한 사용자 승인을 거친다.
- 격리를 구현하기 전에는 커뮤니티 Extension 설치 기능을 공개하지 않는다.

## 2. 위협 모델

다음 상황을 방어 대상으로 한다.

- Extension package에 악성 코드나 취약한 의존성이 포함됨
- Git에서 받은 Markdown, metadata 또는 첨부물이 Extension이나 AI에 악성 지시를 전달함
- Extension이 Vault 밖의 파일, Git credential, API token 또는 다른 Extension 데이터에 접근함
- Extension이 임의 목적지로 정보를 전송하거나 과도한 자원을 소비함
- 구조화 출력에 경로 탈출, 명령, HTML/스크립트 또는 허용되지 않은 변경을 포함함
- 정상 Extension이 업데이트 과정에서 탈취되거나 권한을 확대함

샌드박스는 모델이 악성 문서를 항상 판별한다고 가정하지 않는다. 프롬프트 인젝션이 성공하더라도 사용할 수 있는 데이터와 부작용을 제한하는 것이 목표다.

## 3. 권한 단계

| 단계 | 허용 범위 | 공개 조건 |
|---|---|---|
| `read` | 정규화된 작업 snapshot 읽기, stdout 구조화 결과 반환 | 커뮤니티 Extension의 유일한 초기 권한 |
| `ai` | Core broker를 통한 등록된 AI task 호출 | prompt·schema 고정, 입력·출력 한도 적용 |
| `network` | 선언되고 운영자가 승인한 목적지에 제한된 요청 | egress proxy와 DNS/IP 재검증 구현 후 |
| `draft` | Core가 관리하는 임시 change set 제안 | 임의 경로 금지, schema와 diff 검증 후 |
| `write` | 승인된 change set을 Core가 허용된 대상에 반영 | proposal·명시적 승인·감사 기능 구현 후 |

`shell`, host executable, Docker socket, Git credential 접근과 직접 Git 명령은 capability로 제공하지 않는다. Extension이 Git 변경을 필요로 하더라도 Extension은 change set만 제안하고 commit과 push는 Core의 기존 안전 정책이 담당한다.

권한 추가와 package 업데이트는 별개의 재승인 대상으로 취급한다. 설치 당시보다 넓어진 capability는 자동 활성화하지 않는다.

## 4. 목표 격리 구조

```text
APS Server Core
  │ validated request + one-time job token
  ▼
Extension broker
  ├─ package signature/digest 확인
  ├─ capability와 resource limit 적용
  ├─ 정규화 snapshot 생성
  └─ 격리 runner 시작
         │
         ▼
  Extension runner (별도 container/VM)
    filesystem: package(ro), job snapshot(ro), scratch(tmpfs)
    identity:   전용 non-root UID, capabilities 없음
    network:    기본 차단, 승인된 egress proxy만 선택 허용
    secrets:    장기 credential 없음
    output:     제한된 stdout JSON과 artifact staging만
         │
         ▼
Core ResultValidator
  → schema/path/size/content 검증
  → change set 또는 publication 후보
  → 필요 시 사용자 승인
  → Core가 반영
```

runner는 APS Server와 다른 mount 및 process/network namespace를 사용해야 한다. 같은 container에서 subprocess만 분리하는 방식은 보안 샌드박스로 간주하지 않는다.

### 파일시스템

- 작업마다 필요한 문서만 복사한 immutable snapshot을 만든다.
- symlink, device, socket, 실행 비트와 `.git` metadata는 snapshot에 포함하지 않는다.
- package와 snapshot은 read-only로 mount하고 scratch는 크기가 제한된 tmpfs로 제공한다.
- host root, 원본 `/vault`, `/git-auth`, Core `/data`, container runtime socket은 mount하지 않는다.
- 결과는 지정된 staging 경로 또는 크기가 제한된 stdout으로만 회수한다.

### 프로세스와 자원

- 전용 non-root UID/GID, `no-new-privileges`, Linux capability 전체 drop을 적용한다.
- 기본 seccomp와 별도의 AppArmor/SELinux 정책으로 mount, ptrace, namespace 생성과 위험 syscall을 제한한다.
- CPU, memory, PID, 파일 크기, 실행 시간과 출력 크기를 작업별로 제한한다.
- runner image에는 shell, compiler, package manager와 container 관리 도구를 기본 포함하지 않는다.
- package 의존성은 설치 시점에 고정하고 실행 중 다운로드하지 않는다.

### 네트워크와 secret

- `read`와 `draft` runner는 network namespace에서 외부 통신을 차단한다.
- `ai`는 provider key를 Extension에 전달하지 않고 Core의 task broker를 호출한다.
- `network`가 필요한 경우 URL 문자열 허용만으로 판단하지 않는다. egress proxy에서 scheme, host, port, DNS 결과, redirect와 private/link-local 주소를 검증한다.
- 장기 secret 대신 작업·capability·호출 횟수·만료 시간이 묶인 일회성 token을 사용한다.
- 로그와 오류에는 요청 본문, provider 응답, token 및 Vault 원문을 기본 기록하지 않는다.

## 5. AI와 프롬프트 인젝션 경계

Markdown의 fenced code나 HTML은 데이터일 뿐 실행하지 않는다. 그러나 문서 안의 자연어 지시는 모델을 오도할 수 있으므로 다음을 함께 적용한다.

- 시스템 지시와 외부 문서 영역을 명확히 분리하고 문서를 신뢰하지 않는 데이터로 표시한다.
- Extension이 임의 system prompt, provider, model 또는 Tool을 선택하지 못하게 한다.
- 모델에는 작업에 필요한 최소 필드만 전달하고 secret과 무관한 문서는 제외한다.
- 결과에 근거가 된 문서 ID와 source field를 요구하고 Core가 실제 입력 범위와 대조한다.
- 문자열 탐지기는 경고와 검토 우선순위에만 사용하고 안전 판정의 단독 근거로 삼지 않는다.
- 모델 결과는 권한 결정이나 직접 실행 명령으로 사용하지 않고 schema, ID, 경로와 상태 전이를 Core가 다시 검증한다.

프롬프트 인젝션 방어의 핵심은 악성 지시를 완벽히 탐지하는 것이 아니라, 공격에 성공한 모델이나 Extension이 사용할 수 있는 위험한 sink를 제거하는 것이다.

## 6. 설치와 공급망

- package는 immutable digest로 식별하고 publisher 서명과 manifest 서명을 검증한다.
- registry metadata, source URL, license, dependency lock과 최소 APS protocol version을 기록한다.
- 설치 전에 capability, network 목적지, 데이터 범위와 publisher를 운영자에게 표시한다.
- 업데이트 시 digest, 서명, 의존성 및 capability diff를 보여 주고 권한 확대에는 재승인을 요구한다.
- 취약하거나 탈취된 package digest를 차단할 revocation 목록과 즉시 disable 기능을 둔다.
- package별 실행 이력, 입력 snapshot commit, 승인된 capability, 결과 digest와 부작용을 감사 로그에 남긴다. 원문과 secret은 기록하지 않는다.

## 7. 쓰기 권한 도입 조건

커뮤니티 Extension의 `draft` 또는 `write` 권한은 다음 항목이 모두 구현되기 전에는 활성화하지 않는다.

1. 별도 runner 격리와 기본 네트워크 차단
2. 서명된 package와 immutable dependency 검증
3. Core 소유의 typed broker 및 capability별 호출 한도
4. 경로를 받지 않는 ID 기반 change set 계약
5. 변경 diff, 출처와 예상 부작용을 보여 주는 명시적 승인 화면/API
6. proposal branch와 fast-forward-only Git commit/push gate
7. extension별 revoke, 감사 로그와 실패 복구 절차
8. 악성 package, 프롬프트 인젝션, 자원 고갈과 정보 유출 시나리오 검증

승인 없이 허용할 수 있는 쓰기는 해당 작업의 격리된 scratch와 Core가 원자적으로 교체하는 파생 Content 후보뿐이다. 원본 Vault 변경은 승인 절차의 대상이다.

## 8. 현재 적용 범위

현재 공식 Extension 경로에는 고정 entrypoint, 제한된 환경 변수, 읽기 전용 사용 규칙, JSON Schema 검증과 Core 소유의 게시 경계가 있다. 다만 공식 Extension subprocess는 APS Server와 같은 container 및 UID에서 실행되므로 이 문서의 목표 runner 격리를 충족하지 않는다.

따라서 현재 운영 정책은 다음과 같다.

- image에 포함되어 함께 검토된 공식 Extension만 설치한다.
- 커뮤니티 package의 업로드·동적 설치·실행은 허용하지 않는다.
- 공식 Extension에도 Vault/Git 직접 쓰기와 임의 network capability를 추가하지 않는다.
- 커뮤니티 Extension 공개 여부는 위 격리 구조 구현과 보안 검토 후 별도로 결정한다.
