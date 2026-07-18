# HAZOP AI Agent PoC

업로드한 HAZOP Excel의 `#1 노드리스트`, `#2 가이드워드`를 기준으로 `#3 위험성평가`, `#4 조치계획서` 초안을 생성하는 PoC입니다.

## 실행 준비

### 방법 1. Docker Compose로 한 번에 실행

가장 추천하는 방식입니다. 앱 서버와 Postgres DB가 같이 뜹니다.

```bash
docker compose up --build
```

브라우저에서 아래 주소를 엽니다.

```text
React HAZOP 화면: http://127.0.0.1:8501
```

Docker Compose는 React 정적 화면과 FastAPI API를 함께 실행합니다.

Azure OpenAI를 실제로 쓰고 싶으면 프로젝트 루트에 `.env` 파일을 만들고 아래 값을 넣은 뒤 다시 실행합니다.

```bash
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE-NAME.openai.azure.com/
AZURE_OPENAI_API_KEY=YOUR_AZURE_OPENAI_KEY
AZURE_OPENAI_API_VERSION=2024-08-01-preview
AZURE_OPENAI_DEPLOYMENT=YOUR_DEPLOYMENT_NAME
AZURE_OPENAI_VERIFY_SSL=false
```

사내 프록시 endpoint에서 `self-signed certificate` 연결 오류가 나면 `AZURE_OPENAI_VERIFY_SSL=false`를 둡니다.
운영에서는 이 값을 끄는 대신 사내 CA 인증서를 컨테이너에 설치하는 방식이 더 안전합니다.

MSDS는 기본적으로 KOSHA 안전보건공단 MSDS 사이트를 먼저 조회합니다.
보통 아래 값은 수정하지 않아도 됩니다.

```bash
KOSHA_MSDS_BASE_URL=https://msds.kosha.or.kr
```

Bing 일반 웹 검색 fallback은 현재 PoC 요청에 따라 임시 제외했습니다.
KOSHA 조회를 먼저 시도하고, 그래도 실패하면 PoC 내장 MSDS 요약으로 동작합니다.

실시간 Agent 로그가 너무 빠르게 지나가면 아래 값을 조정합니다.

```bash
AGENT_LOG_DELAY_SECONDS=1.0
AGENT_LLM_HEARTBEAT_SECONDS=2.0
```

### 방법 2. 로컬 Python으로 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Azure OpenAI를 실제로 쓰려면 `.env`에 아래 값을 넣습니다.

```bash
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE-NAME.openai.azure.com/
AZURE_OPENAI_API_KEY=YOUR_AZURE_OPENAI_KEY
AZURE_OPENAI_API_VERSION=2024-08-01-preview
AZURE_OPENAI_DEPLOYMENT=YOUR_DEPLOYMENT_NAME
AZURE_OPENAI_VERIFY_SSL=false
```

주의할 점은 `AZURE_OPENAI_DEPLOYMENT`에는 `gpt-4o` 같은 모델명이 아니라 Azure에서 만든 **배포 이름**을 넣어야 한다는 것입니다.
사내 프록시 endpoint에서 `self-signed certificate` 연결 오류가 나면 `AZURE_OPENAI_VERIFY_SSL=false`를 둡니다.

MSDS는 기본적으로 KOSHA 안전보건공단 MSDS 사이트를 먼저 조회합니다.

```bash
KOSHA_MSDS_BASE_URL=https://msds.kosha.or.kr
```

Bing 일반 웹 검색 fallback은 현재 PoC 요청에 따라 임시 제외했습니다.
KOSHA 조회를 먼저 시도하고, 그래도 실패하면 PoC 내장 MSDS 요약과 demo Agent로 동작합니다.

실시간 Agent 로그 지연 시간은 아래 값으로 조정할 수 있습니다.

```bash
AGENT_LOG_DELAY_SECONDS=1.0
AGENT_LLM_HEARTBEAT_SECONDS=2.0
```

## 샘플 Excel 생성

프로젝트 루트에서 실행합니다.

```bash
cd /Users/zzang/Desktop/me/project/master-aipjt
python scripts/create_sample_excels.py
```

생성 파일:

- `samples/HAZOP_CleanTech_CT-DIW-100.xlsx`
- `samples/HAZOP_ASM_Epsilon3200.xlsx`
- `samples/HAZOP_ThermoVac_TV-ETCH-200.xlsx`
- `samples/HAZOP_ColdChain_NH3-Refrigeration.xlsx`
- `samples/HAZOP_Solvent_IPA-Supply.xlsx`
- `samples/HAZOP_Waterworks_Chlorine-Dosing.xlsx`
- `samples/HAZOP_Battery_Electrolyte-Mixing.xlsx`
- `samples/HAZOP_Integrated_MultiUtility-Complex.xlsx`

각 샘플은 `#1`, `#2`만 데이터가 있고 `#3`, `#4`는 헤더만 있는 빈 Sheet입니다.
`samples/~$...xlsx`처럼 `~$`로 시작하는 파일은 Excel이 파일을 열 때 만드는 임시 잠금 파일이므로 업로드하지 않습니다.

새 샘플은 냉동설비(Ammonia), 용제공급(Isopropyl alcohol), 수처리(Chlorine),
배터리 전해액, 다중 Utility 통합공정을 다룹니다. 특히
`HAZOP_Integrated_MultiUtility-Complex.xlsx`는 10개 Node와 30개가 넘는 평가 조합이 있어
여러 물질과 설비가 함께 있는 긴 Agent 실행을 확인하기 좋습니다.

KOSHA 실검색 성공을 가장 쉽게 확인하려면 물질명에 `Hydrogen`을 입력합니다.
정상 연결 시 Agent 로그에 `KOSHA MSDS 검색 결과를 찾았습니다`와 `chem_id=000557` 같은 출처가 표시됩니다.
외부망 또는 DNS가 막혀 있으면 이제 `ConnectError`처럼 실패 종류가 로그에 표시되고 내장 요약으로 전환됩니다.

## 서버 실행

React frontend를 빌드합니다.

```bash
npm install
npm run build
```

FastAPI 화면과 API를 로컬에서 실행할 때는 아래 명령을 씁니다.

```bash
uvicorn app.main:app --reload --port 8000
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다.

로컬 Python 실행 시 `DATABASE_URL`을 비워두면 SQLite 파일(`data/hazop_poc.db`)을 사용합니다.
Docker Compose 실행 시에는 Postgres를 사용합니다.

## DB 테이블

PoC에서는 DB에 모든 결과 컬럼을 납작하게 저장하지 않고, 추적에 필요한 메타정보를 저장합니다.
실제 생성 결과 JSON과 Excel은 `data/requests/{request_id}` 아래 파일로 저장합니다.

현재 생성되는 테이블은 3개입니다.

| 테이블 | 역할 |
|---|---|
| `hazop_jobs` | AI 초안생성 요청 1건의 기본정보, 업로드 파일 경로, 상태, 결과 Excel 경로 저장 |
| `hazop_agent_events` | 화면에 표시된 Agent 실시간 로그 저장 |
| `hazop_result_meta` | 결과 JSON 경로, 결과 Excel 경로, #3/#4 생성 건수 저장 |

Postgres 컨테이너에 접속해서 확인하려면:

```bash
docker compose exec postgres psql -U hazop -d hazop_poc
```

테이블 목록:

```sql
\dt
```

최근 요청:

```sql
select id, maker, model, status, output_excel_path, created_at
from hazop_jobs
order by created_at desc;
```

Agent 로그:

```sql
select event_type, title, detail, created_at
from hazop_agent_events
order by id;
```

앱 API로도 최근 요청을 볼 수 있습니다.

```bash
curl http://127.0.0.1:8000/api/jobs
```

## 구현 원칙

- AI는 Node, 변수, Guideword를 새로 만들지 않습니다.
- AI는 원인/결과/안전조치/빈도 후보/강도 후보와 근거를 생성합니다.
- 위험도는 시스템이 `빈도 * 강도`로 계산합니다.
- 위험도 9 이상인 항목만 `#4 조치계획서` 생성 대상입니다.
- Agent 로그에는 판단과 근거가 함께 표시됩니다.
- MSDS는 KOSHA 사이트 검색을 우선 시도하고, 실패 시 내장 요약으로 fallback합니다.

## 테스트 방법

### 1. 샘플 Excel 생성 확인

```bash
python scripts/create_sample_excels.py
```

아래 기본 3개와 신규 5개, 총 8개가 생기면 됩니다.

```text
samples/HAZOP_CleanTech_CT-DIW-100.xlsx
samples/HAZOP_ASM_Epsilon3200.xlsx
samples/HAZOP_ThermoVac_TV-ETCH-200.xlsx
samples/HAZOP_ColdChain_NH3-Refrigeration.xlsx
samples/HAZOP_Solvent_IPA-Supply.xlsx
samples/HAZOP_Waterworks_Chlorine-Dosing.xlsx
samples/HAZOP_Battery_Electrolyte-Mixing.xlsx
samples/HAZOP_Integrated_MultiUtility-Complex.xlsx
```

각 파일에서 `#3 위험성평가`, `#4 조치계획서`는 헤더만 있고 데이터 행은 비어 있어야 합니다.

### 2. 웹 화면 테스트

1. `npm run build` 실행
2. `uvicorn app.main:app --reload --port 8000` 실행
3. `http://127.0.0.1:8000` 접속
4. `samples/HAZOP_CleanTech_CT-DIW-100.xlsx` 업로드
5. Maker/Model/Node List 물질 기본값 확인
6. `AI 초안생성` 클릭
7. Agent 로그가 실시간으로 쌓이는지 확인
8. `#3 위험성평가` 테이블이 생성되는지 확인
9. `결과 Excel 다운로드` 클릭

CleanTech 샘플은 낮은 위험도 케이스라 보통 `#4 조치계획서`가 비어 있습니다.
`HAZOP_ASM_Epsilon3200.xlsx`는 Silane/Hydrogen 케이스라 위험도 9 이상 항목과 `#4 조치계획서`가 생성되는지 확인하기 좋습니다.

### 3. API 헬스체크

```bash
curl http://127.0.0.1:8000/api/health
```

정상 응답:

```json
{"status":"ok"}
```

### 4. Python 기본 검증

```bash
python -m compileall app scripts tests
python -c "from app.services.risk import calculate_risk_score; assert calculate_risk_score(3,4)==12; print('ok')"
```
