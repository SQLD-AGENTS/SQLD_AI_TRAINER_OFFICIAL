# SQLD AI 적응형 학습 플랫폼

> 이 프로젝트는 [chodonghee-hub/sqld-ai-trainer](https://github.com/chodonghee-hub/sqld-ai-trainer) 레포지토리를 이어서 작업했습니다.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green?logo=fastapi)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-red?logo=pytorch)
![Railway](https://img.shields.io/badge/Railway-Deployed-black?logo=railway)
![Vercel](https://img.shields.io/badge/Vercel-Frontend-black?logo=vercel)
![Google OAuth](https://img.shields.io/badge/Google_OAuth-2.0-4285F4?logo=google)
![Cloudflare R2](https://img.shields.io/badge/Cloudflare_R2-Storage-F38020?logo=cloudflare)


_SQLD(SQL 개발자 자격증) 기출 문제를 기반으로 **ML · DKT · RAG/LLM** 기술을 통합한 AI 기반 적응형 학습 플랫폼._

🌐 [**배포 환경 바로가기**](https://sqld-ai-trainer-official.vercel.app)

---

## 목차

1. [프로젝트 개요](#프로젝트-개요)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [데이터 전처리 및 파이프라인](#데이터-전처리-및-파이프라인)
4. [DB 스키마 & 임베딩 적재 파이프라인](#db-스키마--임베딩-적재-파이프라인)
5. [AI 모델 상세](#ai-모델-상세)
6. [백엔드](#백엔드)
7. [프론트엔드](#프론트엔드)
8. [코드 관리 전략](#코드-관리-전략)
9. [로컬 실행](#로컬-실행)
10. [배포](#배포)
11. [API 명세](#api-명세)
12. [데이터셋](#데이터셋)

---

## 프로젝트 개요

### 문제 정의

기존 자격증 학습 서비스는 모든 사용자에게 동일한 문제를 제공하고 단순 정답만 알려준다. 이미 아는 문제를 반복 풀이하거나, 취약한 개념을 파악하지 못한 채 시험에 임하는 비효율이 발생한다.

### 해결 방식

| 기존 문제 | 본 플랫폼의 접근 |
|-----------|----------------|
| 모든 사용자에게 동일 문제 제공 | DKT + 하이브리드 추천으로 개인화 |
| 취약 영역 분석 부재 | 챕터별 정답률 + 오답 패턴 자동 분석 |
| 이미 아는 문제 반복 | ZPD(Zone of Proximal Development) 기반 난이도 매칭 |
| 단순 정답 제공 | Ollama Cloud LLM + RAG로 오답 원인 맞춤 해설 생성 |
| 학습 순서 무관 | Knowledge Tracing으로 다음 학습 문제 예측 |

### 주요 기능

| 기능 | 설명 |
|------|------|
| 문제 풀이 | 591개 SQLD 기출 문제, 챕터·난이도 필터 |
| 오답 확률 예측 | XGBoost 기반 문제별 오답 확률 실시간 표시 |
| 개인화 추천 | DKT + 하이브리드 필터링으로 다음 학습 문제 추천 |
| AI 해설 | Ollama Cloud LLM + pgvector RAG 파이프라인으로 맞춤 해설 생성 |
| 학습 대시보드 | 챕터별 정답률 차트, 취약 영역 분석 |
| 게스트 모드 | 회원가입 없이 문제 풀기 및 AI 해설 이용 가능 |
| Google OAuth | Google 계정으로 간편 회원가입·로그인 |
| 프로필 관리 | 닉네임·아바타 변경, 비밀번호 수정, 계정 삭제 (아바타는 Cloudflare R2 저장) |

<br>

> 메인 페이지
<div align='center'>
  <img width="700" height="380" alt="image" src="https://github.com/user-attachments/assets/64ee8657-7aff-41ff-bc16-309293511aeb" />  
</div>

<br>

> 문제 목록
<div align='center'>
  <img width="700" height="380" alt="image" src="https://github.com/user-attachments/assets/04d8f03d-3d03-44fb-89b3-baec582a6995" />
</div>

---

## 시스템 아키텍처

```
[Vercel]                           [Railway — Docker Container]
React 19 + TypeScript              FastAPI + uvicorn
(Vite 정적 빌드)         ←──────►   ├─ AppState (Singleton)
                          HTTPS    │   ├─ XGBoost Predictor      ← Lazy Load
                          REST     │   ├─ SVD + TF-IDF Recommender ← Lazy Load
                                   │   ├─ DKT/LSTM (PyTorch)      ← Lazy Load
                                   │   └─ RAGExplainer            ← Lazy Load
                                   │       ├─ pgvector cosine 검색 (Gemini 1536-dim)
                                   │       └─ Ollama Cloud ──► qwen3.5:cloud
                                   ├─ Postgres + pgvector (users·logs·questions·embeddings)
                                   └─ Cloudflare R2 (프로필 아바타)
```

### 모델 로딩 전략

서버 시작 시 ML 모델을 모두 로드하면 Railway 헬스체크 타임아웃이 발생한다. 이를 두 가지 전략으로 해결한다.

**전략 1 — 데이터 로딩은 시작 시 1회**
`lifespan` 내 `_bootstrap()`이 questions 테이블 자동 시딩 + 문제 데이터 로드를 순서대로 실행한다.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    app.state.models = app_state
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _bootstrap)  # seeding → 데이터 로드
    yield

def _bootstrap():
    _seed_questions_if_empty()  # questions 테이블 비어 있으면 JSON에서 1회 적재
    app_state.load()             # Postgres questions 테이블 → questions_df 로드
```

**전략 2 — ML 모델은 Lazy Loading**
Recommender, Predictor, DKT, RAG 해설기는 시작 시 로드하지 않고 **첫 API 요청 시점에 지연 로드**한다. OOM 방지 및 헬스체크 즉시 응답을 위해서다.

```python
# /recommend 첫 호출 시
app_state.load_recommender_if_needed()

# /predict 첫 호출 시
app_state.load_predictor_if_needed()
```

---

## 데이터 전처리 및 파이프라인

ML 모델 학습에 사용할 정형 데이터를 생성하는 오프라인 파이프라인이다. `backend/src/data/pipeline.py`를 진입점으로 세 단계가 순서대로 실행된다.

```
datasets/json/*.json (12개 챕터)
        │
        ▼  [1단계] json_parser.py
  원시 DataFrame
  (question_id, question_text, sql_code, choices, explanation ...)
        │
        ▼  [2단계] features.py
  Feature DataFrame
  (+ question_type_encoded, choice_kind_complexity, difficulty, difficulty_label)
        │
        ├──► outputs/questions.csv   ← API·ML 공용 문제 마스터 데이터
        │
        ▼  [3단계] simulator.py
  시뮬레이션 학습 이력
  (user_id, question_id, is_correct, solve_time_sec, submitted_at ...)
        │
        └──► outputs/user_logs.csv  ← ML 모델 학습용 이력 데이터
```

파이프라인 완료 후 `_verify()` 함수로 자동 품질 검증을 수행한다.
- `question_id` 중복 여부 확인
- 각 난이도(`Easy` / `Medium` / `Hard`) 비율이 5% 이상인지 확인

---

### 1단계 — JSON 파싱 (`json_parser.py`)

12개 챕터 JSON 파일을 순회해 정형화된 DataFrame으로 변환한다.

**question_id 생성 규칙**

```
question_id = f"{subject_id}_{chapter_id}_{question_number}"
# 예: "2_1_5"  → Part II, Chapter 1, 5번 문제
```

중복 여부는 파싱 직후 `assert df["question_id"].is_unique`로 즉시 검증한다.

**asset 추출 — `doc_builder` (SSOT)**

`assets` 배열엔 본문(`text_block`), SQL(`sql_query`/`sql_ddl`/`sql_dml`), 표(`data_table`/`result_table`), ERD 등 **17종**이 섞여 있다. `doc_builder.py`가 이를 단일 원천(Single Source of Truth)으로 직렬화한다.

```python
question_text = doc_builder.build_question_text(assets)  # [지문]+[자료] (표·ERD 평탄화 포함)
sql_code      = doc_builder.build_sql_code(assets)       # sql_query + sql_ddl + sql_dml
has_sql_asset = bool(sql_code)
```

**임베딩·해시의 단일 입력**: `build_doc(assets, choices, explanation)`는 5섹션(`[지문]·[자료]·[SQL]·[보기]·[해설]`) 문서를 만들고, 이 문서가 (1) `content_hash`(md5) 와 (2) Gemini 임베딩의 **동일한 입력**으로 쓰인다. 적재 시 해시 산출(`json_parser`)과 임베딩 시 재구성(`vectorize_questions`)이 같은 함수를 호출하므로, 파싱↔임베딩 표현이 절대 어긋나지 않는다(멱등의 린치핀).

```
assets ─► build_doc() ─┬─► content_hash (md5)         → questions.content_hash
                       └─► Gemini embedding (1536d)   → question_embeddings (pgvector HNSW)
                                                              │
            /explain 요청 시 cosine(<=>)으로 유사 문제 검색 ◄──┘  → RAG 컨텍스트로 LLM에 주입
```

`content_hash`는 **스테일 검출 키**다 — 문항 내용이 바뀌면 `questions.content_hash ≠ question_embeddings.content_hash`가 되어 자동으로 재임베딩 대상이 된다. (`verify_pipeline.py`가 이 체인 정합을 게이트로 검증)

**선택지 정보 추출**

| 추출 항목 | 컬럼 | 설명 |
|-----------|------|------|
| 각 선택지의 `choice_kind` | `choice_kinds` | 쉼표 구분 문자열 (예: `"text,sql_query,keyword"`) |
| 정답 번호 | `correct_choice` | `is_correct: true`인 `choice_number` |
| 선택지 전체 | `choices` | JSON 문자열 (`[{"number": 1, "text": "..."}]`) |

**파싱 결과 컬럼 목록**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `question_id` | str | 고유 식별자 (`subject_chapter_number`) |
| `subject_id` | int | 파트 번호 (1~3) |
| `chapter_id` | int | 챕터 번호 |
| `chapter_name` | str | 챕터명 (`CHAPTER_NAMES` 매핑) |
| `question_type` | str | 16종 (worst_choice, best_choice, predict_result, fill_blank, identify_sql 등) |
| `question_text` | str | 문제 본문 (text_block 합산) |
| `sql_code` | str | SQL 코드 블록 (없으면 빈 문자열) |
| `has_sql_asset` | bool | SQL 포함 여부 |
| `choice_kinds` | str | 선택지 유형 쉼표 목록 |
| `correct_choice` | int | 정답 번호 |
| `explanation` | str | 해설 텍스트 |
| `assets` | list(JSON) | 원본 asset 배열 무손실 보존 — `doc_builder` 파생의 원천 |
| `exam_subject` | int | 기출 시험지 과목 (모의고사 M55~M60 만 값) |
| `content_hash` | str | `md5(build_doc)` — 임베딩 동기화 키 (재임베딩 동기) |

---

### 2단계 — Feature 엔지니어링 (`features.py`)

원시 DataFrame에 ML 모델 입력용 수치 Feature 4개를 추가한다.

**① question_type_encoded** — 문제 유형 정수 인코딩

| question_type | 인코딩 값 |
|---------------|-----------|
| worst_choice | 0 |
| best_choice | 1 |
| fill_blank | 2 |
| different_result | 3 |

> ⚠ `features.py`는 위 **4종만 명시 인코딩**하고, 모의고사(55~60회)에서 추가된 나머지 12종(predict_result, derive_count, identify_sql 등)은 현재 `-1`로 매핑된다. 16종 전체 인코딩은 features.py 보완 예정 항목.

**② choice_kind_complexity** — 선택지 복잡도 점수 (0~3)

선택지 유형마다 인지 부하를 점수화하고, 한 문제에 여러 유형이 섞인 경우 **가장 높은 점수**를 채택한다.

| choice_kind | 점수 | 이유 |
|-------------|------|------|
| keyword | 0 | 단순 키워드 |
| text | 1 | 자연어 보기 |
| sql_fragment | 2 | SQL 일부 |
| sql_query | 3 | 완전한 SQL문 |

**③ difficulty / difficulty_label** — 규칙 기반 난이도 추정

원본 JSON에 `difficulty` 필드가 없으므로 `question_type`과 `subject_id`, `has_sql_asset`을 조합해 자동 추정한다.

```
different_result            → Hard  (결과 비교는 실행 오류를 잡아야 함)
fill_blank                  → Medium 기본
best_choice / worst_choice  → Easy 기본

위 기본값에서 아래 규칙으로 상향 조정:
  has_sql_asset AND subject_id == 3  → Hard  (SQL 튜닝 파트 SQL 문제)
  subject_id == 3 (SQL 튜닝 파트)    → 한 단계 상향 (Easy→Medium, Medium→Hard)
```

| difficulty 값 | difficulty_label | 적용 조건 요약 |
|---------------|-----------------|----------------|
| 0 | Easy | best/worst_choice, 비튜닝 파트 |
| 1 | Medium | fill_blank 기본 / 튜닝 파트 Easy 문제 |
| 2 | Hard | different_result / 튜닝 파트 SQL 포함 문제 |

---

### 3단계 — 시뮬레이션 학습 이력 (`simulator.py`)

실제 사용자 이력이 없으므로 **가상 100명**의 풀이 이력을 수식 기반으로 생성한다. 재현성을 위해 `numpy.random.default_rng(seed=42)`를 사용한다.

**사용자 분포**

| 레벨 | 비율 | 기본 정답률 |
|------|------|-------------|
| beginner | 40% | 40% |
| intermediate | 40% | 65% |
| advanced | 20% | 85% |

**정답 확률 계산식**

각 풀이 시도에서 정답 확률 `acc`를 아래 식으로 계산한 뒤 베르누이 시행으로 `is_correct`를 결정한다.

```
acc = clamp(base_acc + difficulty_penalty + knowledge_gain × (attempt - 1), 0.05, 0.95)

difficulty_penalty: Easy=0.0, Medium=-0.05, Hard=-0.15
knowledge_gain:     동일 문제 재시도마다 +0.02 (반복 학습 효과)
```

예시: `intermediate` 사용자가 `Hard` 문제를 3번째 시도할 때
```
acc = clamp(0.65 + (-0.15) + 0.02 × 2, 0.05, 0.95) = 0.54
```

**풀이 시간 시뮬레이션**

난이도별로 정규분포에서 샘플링한다.

| difficulty | 평균(초) | 표준편차(초) |
|------------|---------|-------------|
| Easy | 30 | 10 |
| Medium | 60 | 15 |
| Hard | 90 | 20 |

최소값 5초로 클램핑 (`max(5, sampled_time)`).

**풀이 라운드 구성**

각 사용자는 전체 591문제를 1~3라운드 무작위로 반복 풀이한다. 라운드 간 간격은 2주(`14일`)로 설정해 시간적 분포를 만든다.

**생성 결과 컬럼**

| 컬럼 | 설명 |
|------|------|
| `user_id` | 가상 사용자 ID (`user_001` ~ `user_100`) |
| `question_id` | 풀이한 문제 ID |
| `user_level` | beginner / intermediate / advanced |
| `is_correct` | 정답 여부 (bool) |
| `solve_time_sec` | 풀이 소요 시간(초) |
| `submitted_at` | 제출 일시 (2025-01-01 기준 시뮬레이션) |
| `attempt_count` | 해당 사용자의 해당 문제 누적 시도 횟수 |

---

## DB 스키마 & 임베딩 적재 파이프라인

위 ML 데이터 파이프라인(CSV·모델 학습용)과 별개로, **서빙 DB(Postgres + pgvector)** 에 문제·임베딩·유사도를 적재하는 런타임 파이프라인이다. `/explain`(RAG)·추천이 이 데이터를 소비한다.

### DB 스키마 (v4)

| 테이블 | 역할 | 핵심 컬럼 |
|--------|------|----------|
| `questions` | 문제 마스터 | `assets`(JSON 무손실), `content_hash`, `status`, `source`, `generated_from`, `exam_subject` |
| `question_embeddings` | Gemini 1536d 임베딩 (1:1) | `embedding`(pgvector), `model_name`, `content_hash` |
| `question_similar` | top-k 유사 문제 사전 | `(question_id, similar_question_id)` PK, `similarity`, `computed_at` |
| `question_dedup_log` | 중복 제거 감사 | `removed_question_id`, `kept_question_id`, `similarity`, `method` |
| `users` · `answer_logs` | 인증 · 풀이 이력 | — |

- **status 서빙 게이트** — `active`(서빙) / `pending`(생성 문항 검수 대기) / `rejected` / `retired`. 추천·연습·RAG는 `active`만 조회한다(`AppState`도 active만 로드).
- **content_hash 체인** — `questions.content_hash → question_embeddings.content_hash → question_similar.computed_at`. 문항 내용이 바뀌면 해시 불일치로 **재임베딩 → 재유사도계산**이 연쇄 트리거된다.
- **마이그레이션** — Alembic. v4 스키마는 단일 통합 마이그레이션으로 관리(스쿼시). 로컬 SQLite는 마이그레이션 없이 `metadata.create_all`로 직접 생성.

### 적재 파이프라인 (4 스크립트, 순차 실행)

```
load_questions.py        JSON 파싱 → doc_builder content_hash 산출 → questions 적재
                         (청크 upsert + 데이터셋에서 빠진 original 문항 자동 prune)
        ↓
vectorize_questions.py   스테일(신규·내용변경·모델교체) 문항만 Gemini 임베딩
                         → question_embeddings 적재 + HNSW(cosine) 인덱스
        ↓
refresh_similarities.py  active 풀에서 문항별 top-3 cosine(<=>) → question_similar
                         (upsert-then-prune 단일 트랜잭션 — 중간 '이웃 0개' 상태 없음)
        ↓
verify_pipeline.py       V1~V8 불변식 게이트 — content_hash 체인·임베딩 커버리지·
                         모델 일관성·양측 스테일 검사. 위반 시 exit 1 (CI 겸용)
```

- **멱등** — `content_hash` 기반 스테일 검출로 변경분만 재처리(전체 재임베딩 회피)
- **SSOT** — `doc_builder.build_doc()`가 해시·임베딩 입력의 단일 원천 ([1단계](#1단계--json-파싱-json_parserpy) 참조)
- **모델 SSOT** — `EMBED_MODEL` / `EMBED_TASK_TYPE` / `EMBED_MODEL_NAME`(=`gemini-embedding-001:ss`) 3상수를 전 스크립트가 참조

---

## AI 모델 상세

### Phase 2 — 머신러닝 모델

#### 문제 분류기 (`classifier.py`)

문제 텍스트를 분석해 `subject_id`(파트)와 `difficulty_label`(난이도)을 분류한다.

**텍스트 표현**
- TF-IDF Vectorizer: `analyzer="char_wb"`, `ngram_range=(2, 4)`, `max_features=3000`
- 한국어 형태소 분석기 없이 음절 블록(character n-gram) 단위로 처리

**Feature 구성**
```
TF-IDF 행렬 (sparse)
+ question_type OneHot (4차원)
+ has_sql_asset (0/1)
+ choice_kind_complexity (0~3)
```

**모델**: Logistic Regression (C=1.0) / LinearSVC — StratifiedKFold 5-fold 교차 검증

--

#### 오답 확률 예측기 (`predictor.py`)

(user, question) 쌍에 대해 오답 확률(0~1)을 예측하는 이진 분류 모델.

<div align='center'>
  <img width="580" height="380" alt="image" src="https://github.com/user-attachments/assets/70bb6d90-7120-4168-9c1b-3ef703ac58b3" />
</div>

**Feature 엔지니어링**

유저 레벨 Feature는 `user_logs.csv` 전체 기준으로 집계된 통계값이다. NaN(풀이 이력 없는 챕터/유형)은 해당 사용자의 `user_overall_accuracy`로 대체한다.

| Feature 그룹 | Feature 명 | 설명 |
|-------------|-----------|------|
| 유저 — 전체 | `user_overall_accuracy` | 전체 문제 정답률 |
| 유저 — 난이도별 | `user_diff_0/1/2_accuracy` | Easy·Medium·Hard 각 정답률 |
| 유저 — 챕터별 | `user_ch{N}_accuracy` | 각 챕터별 정답률 (wide format) |
| 유저 — 유형별 | `user_qt_{type}_accuracy` | 문제 유형(worst/best/fill/diff)별 정답률 |
| 유저 — 시간 | `user_avg_solve_time` | 평균 풀이 시간(초) |
| 문제 | `question_type_encoded` | 문제 유형 정수 인코딩 (0~3) |
| 문제 | `has_sql_asset` | SQL 포함 여부 (0/1) |
| 문제 | `choice_kind_complexity` | 선택지 최대 복잡도 (0~3) |
| 문제 | `subject_id`, `chapter_id` | 파트·챕터 번호 |
| 문제 | `difficulty` | 규칙 기반 난이도 (0~2) |

**XGBoost 학습 원리**

XGBoost(eXtreme Gradient Boosting)는 여러 개의 약한 결정 트리를 순서대로 쌓아, 이전 트리의 **잔차(residual)**를 다음 트리가 보정하는 Gradient Boosting 방식이다.

```
초기 예측 F₀(x)
    ↓
1번 트리 h₁: F₀의 오차를 줄이는 방향으로 학습
    ↓
2번 트리 h₂: (F₀ + η·h₁)의 오차를 줄이는 방향으로 학습
    ↓  (반복 200회)
최종 예측 = F₀ + η·h₁ + η·h₂ + ... + η·h₂₀₀

η (learning_rate) = 0.05  ← 각 트리의 기여도를 줄여 과적합 방지
```

RandomForest가 트리를 **병렬·독립적**으로 쌓는 것과 달리, XGBoost는 **순차적**으로 이전 오류에 집중하므로 일반적으로 더 높은 정확도를 보인다.

**하이퍼파라미터 설명**

| 파라미터 | 값 | 역할 |
|----------|-----|------|
| `n_estimators` | 200 | 결정 트리 개수 |
| `max_depth` | 6 | 트리 최대 깊이 (과적합 제어) |
| `learning_rate` | 0.05 | 각 트리의 기여 가중치 (작을수록 안정적) |
| `subsample` | 0.8 | 트리마다 사용할 샘플 비율 (무작위성 추가) |
| `colsample_bytree` | 0.8 | 트리마다 사용할 Feature 비율 |
| `eval_metric` | auc | 학습 중 검증 지표 |

**모델 비교 및 자동 선택**

두 모델을 동일한 80/20 분할로 학습한 뒤 **테스트셋 AUC-ROC**가 높은 쪽을 `predictor_primary.joblib`으로 저장한다.

| 모델 | n_estimators | max_depth | 특징 |
|------|-------------|-----------|------|
| RandomForest | 200 | 10 | 병렬 학습, `class_weight="balanced"` |
| XGBoost | 200 | 6 | 순차 Boosting, subsample·colsample로 정규화 |

**타겟 변수**: `is_correct=False → 1` (오답=양성), `is_correct=True → 0`

**API 응답 (`POST /predict`)**
```json
{
  "error_probability": 0.72,
  "risk_level": "high",
  "message": "이 문제는 틀릴 가능성이 높습니다.",
  "source": "model"
}
```
`risk_level` 기준: `< 0.4` → low, `0.4~0.65` → medium, `> 0.65` → high

---

#### 하이브리드 추천 시스템 (`recommender.py`)

Content-Based + Collaborative Filtering 혼합 추천.

**Stage 1 — Content-Based Filtering**
- 최근 오답 문제 텍스트 TF-IDF 벡터와 전체 문제 코사인 유사도 계산
- 유사한 개념의 문제를 우선 추천

**Stage 2 — Collaborative Filtering**
- User-Item 정답 행렬 → TruncatedSVD (n_components=20) → 유사 사용자 기반 추천

**최종 점수**
```
score = 0.7 × content_score + 0.3 × cf_score
```

**ZPD(Zone of Proximal Development) 필터**

DKT가 예측한 `P(correct)`가 `[zpd_low, zpd_high]` 범위(기본 0.3~0.6)에 있는 문제에 가중치를 부여해 적정 난이도 문제를 우선 추천한다.

```
"너무 쉽지도 너무 어렵지도 않은" 문제 → 학습 효과 최대화
```

**추천 제외 조건**: 이미 맞힌 문제, 약점 챕터 외 문제 (취약 챕터 상위 3개 우선)

---

### Phase 3 — 딥러닝

#### DKT — Deep Knowledge Tracing (`knowledge_tracer.py`)

사용자 풀이 이력 시퀀스를 LSTM으로 모델링해 다음 문제별 정답 확률 벡터를 예측한다.

**아키텍처**

```
입력 시퀀스: [(question_idx × 2) + response + 1]  ← 1-indexed, 0=padding
      ↓
Embedding(num_questions × 2 + 1, embed_dim=128)
      ↓
LSTM(input=128, hidden=128, dropout=0.2)
      ↓
Linear(128 → 297)
      ↓
Sigmoid → P(correct) for each question (297개)
```

> ⚠ 현재 DKT는 **원본 297문항 기준으로 학습**된 상태(`dkt_question_ids`=297)다. 모의고사 294문항은 입력 시퀀스·출력 벡터에 포함되지 않아 해당 문항엔 ZPD 보정이 적용되지 않는다. 추천기(591 재학습 완료)와 동일하게 DKT도 591 재학습이 필요한 항목.

**학습 설정**

| 항목 | 값 |
|------|-----|
| Epochs | 30 (Early Stopping patience=5) |
| Batch Size | 32 |
| Learning Rate | 1e-3 |
| 손실 함수 | BCELoss |
| 분할 | 80/20 (user-level stratified) |
| 평가 | AUC-ROC |

**저장 아티팩트**: `dkt_model.pth` (state_dict), `dkt_question_ids.joblib`

---

#### Dense 임베딩 + FAISS (`embedder.py`)

> ⚠ 이 절의 FAISS(MiniLM 384-dim)는 **초기 구현**이다. 현재 런타임 RAG 유사검색은
> pgvector(Gemini 1536-dim, `question_embeddings` 테이블)로 이전되었고, `embedder.py`는 오프라인 레거시다.

**임베딩 모델**: `paraphrase-multilingual-MiniLM-L12-v2` (384-dim)
- 50개 언어 지원 다국어 모델, 한국어 문장 의미 표현에 적합
- MiniLM 구조로 BERT 대비 6배 빠른 추론, CPU 환경에서 실용적
- sentence-transformers 라이브러리로 로드

**임베딩 대상**: `question_text + " " + explanation` 합쳐서 인코딩
- 문제 본문 단독보다 해설까지 합친 텍스트가 더 풍부한 의미 표현 제공
- 배치 크기 32로 순차 인코딩, 결과는 `float32` ndarray (N×384)

**FAISS란**

FAISS(Facebook AI Similarity Search)는 Meta AI가 개발한 **고속 벡터 유사도 검색 라이브러리**다. 수십억 개의 벡터에서 주어진 쿼리 벡터와 가장 가까운 k개를 빠르게 찾는다.

일반 반복문으로 N개 벡터와 순차 비교하면 O(N)이지만, FAISS는 인덱스 구조를 사전 구축해 탐색 복잡도를 줄인다.

**IndexFlatIP와 코사인 유사도**

```
벡터 L2 정규화 (||v|| = 1 로 만들기)
        ↓
IndexFlatIP에 추가 (Inner Product 기반 완전 탐색)

쿼리 시:
  코사인 유사도 = (v₁ · v₂) / (||v₁|| × ||v₂||)
              = v₁ · v₂   ← 이미 정규화됐으므로 내적 = 코사인
```

`IndexFlatIP`는 근사 없이 모든 벡터와 완전 탐색한다. 데이터셋이 297개로 작아 속도 문제가 없으므로 IVF(역색인) 등 근사 인덱스보다 정확도 우선으로 선택했다.

**인덱스 구축 흐름**

```
question_text + explanation (297개)
        ↓
SentenceTransformer.encode()  → ndarray (297, 384)
        ↓
faiss.normalize_L2()           → 각 벡터를 단위 벡터로 정규화
        ↓
faiss.IndexFlatIP(dim=384)
index.add(embeddings)          → 297개 벡터 등록
```

**추천에서의 활용**

사용자의 최근 오답 문제 임베딩 벡터들을 **평균**내어 쿼리 벡터를 만들고, 전체 문제 임베딩과 내적 연산으로 유사도 점수를 산출한다. 이 점수가 하이브리드 추천의 Content-Based 점수(`alpha=0.7` 가중)로 사용된다.

```python
query_vec = embeddings[recent_wrong_indices].mean(axis=0)  # 오답 중심 벡터
query_vec /= np.linalg.norm(query_vec)                     # 정규화
scores = embeddings @ query_vec                            # 전체 문제 유사도 (297,)
```

**한글 경로 호환**: `faiss.write_index()`가 한글 경로를 지원하지 않아, 인덱스를 bytes로 직렬화한 뒤 joblib으로 저장한다.

```python
# 저장
buf = faiss.serialize_index(index)
joblib.dump(buf, "faiss_index.joblib")

# 로드
buf = joblib.load("faiss_index.joblib")
index = faiss.deserialize_index(buf)
```

**저장 아티팩트**: `sentence_embeddings.npy` (N×384), `faiss_index.joblib`, `embed_question_ids.joblib`

---

### Phase 4 — RAG / LLM 해설 (`explainer.py`)

> ⚠ 현재 런타임은 **pgvector(Gemini 1536-dim) 검색 + Ollama Cloud(qwen3.5:cloud)** 로 동작한다.
> 아래 일부 설명·다이어그램은 초기 구현(FAISS·Groq) 기준이며, 검색 단계가 pgvector로, LLM이 Ollama로 이전되었다.

#### RAG(Retrieval-Augmented Generation)란

LLM(대형 언어 모델)은 학습 데이터에 없는 도메인 지식에 대해 잘못된 정보를 생성하는 **Hallucination** 문제가 있다. RAG는 이를 해결하기 위해 LLM이 답변을 생성하기 전에 **외부 지식 베이스에서 관련 문서를 검색(Retrieve)해 프롬프트에 함께 제공(Augment)** 하는 방식이다.

```
기존 LLM:  질문 → LLM → 답변 (학습 데이터에만 의존, Hallucination 위험)

RAG:       질문 → [검색] 관련 문서 k개 → 질문 + 문서 → LLM → 근거 있는 답변
```

본 프로젝트에서는 LLM이 SQLD 기출 문제의 해설 데이터를 모른다는 전제 하에, **FAISS로 유사 문제를 검색해 컨텍스트로 제공**함으로써 SQLD 도메인에 특화된 정확한 해설을 생성한다.

#### 구현 파이프라인

**1단계 — 오프라인 인덱싱 (서버 시작 시 1회)**

```
297개 문제 전체
      ↓
question_text + explanation → sentence-transformers 인코딩 (384-dim)
      ↓
L2 정규화 (코사인 유사도를 내적으로 변환)
      ↓
FAISS IndexFlatIP 구축 → faiss_index.joblib 저장
```

**2단계 — 온라인 추론 (사용자 요청마다)**

```
오답 question_id
      ↓
해당 문제 임베딩 벡터 추출
      ↓
FAISS 검색: cosine similarity 상위 k=3개 유사 문제 반환
      ↓
프롬프트 구성
  ├─ [문제 정보] 챕터, 난이도, 문제 텍스트, 기존 해설
  ├─ [참고 컨텍스트] 유사 문제 3개 + 각 해설  ← RAG의 핵심
  └─ [작성 지침] 핵심 개념, 오답 포인트, 유사 문제 연결, 기억 포인트
      ↓
Ollama Cloud (qwen3.5:cloud)
      ↓
한국어 맞춤 해설 반환
```

#### RAG가 단순 LLM 호출과 다른 점

| 항목 | 단순 LLM | RAG (본 프로젝트) |
|------|----------|-----------------|
| 컨텍스트 | 없음 (LLM 파라미터에 의존) | SQLD 기출 해설 3개 제공 |
| Hallucination | 발생 가능 | 실제 해설 기반으로 억제 |
| 도메인 특화 | 낮음 | 높음 (SQLD 개념 정확도 향상) |
| 비용 | 프롬프트 짧음 | 컨텍스트만큼 토큰 증가 |

**Fallback 전략**
- `OLLAMA_API_KEY` 미설정 또는 API 오류 → `original_explanation` 반환, `source: "fallback"`

**캐싱**: `explain_cache[question_id]` — 동일 문제 중복 API 호출 방지

---

## 백엔드

### 구조

```
backend/
├── api/
│   ├── main.py              # FastAPI 앱, lifespan, CORS 설정
│   ├── database.py          # SQLAlchemy 엔진, 세션 관리, ORM 모델
│   ├── state.py             # AppState 싱글턴 (모든 모델 보유)
│   ├── auth.py              # JWT 유틸리티, 비밀번호 해싱, OAuth 검증
│   ├── embeddings.py        # Gemini 임베딩 API 래퍼
│   ├── routers/
│   │   ├── auth.py          # 회원가입·로그인·게스트·Google OAuth JWT 발급
│   │   ├── questions.py     # 문제 목록·상세 조회
│   │   ├── logs.py          # 풀이 결과 저장 및 정답 판정
│   │   ├── predict.py       # XGBoost 오답 확률 예측
│   │   ├── explain.py       # RAG AI 해설 생성
│   │   ├── recommend.py     # DKT + 하이브리드 추천
│   │   └── progress.py      # 챕터별 학습 진도 조회
│   └── schemas/             # Pydantic 요청/응답 스키마
├── src/
│   ├── models/
│   │   ├── classifier.py    # TF-IDF + Logistic Regression 분류기
│   │   ├── predictor.py     # XGBoost / RandomForest 오답 예측기
│   │   ├── recommender.py   # SVD + TF-IDF 하이브리드 추천기
│   │   ├── knowledge_tracer.py  # PyTorch LSTM DKT
│   │   ├── embedder.py      # sentence-transformers + FAISS (레거시, 오프라인)
│   │   └── explainer.py     # RAG 파이프라인 (pgvector + Ollama)
│   └── data/
│       ├── json_parser.py   # 챕터 JSON 파싱
│       ├── features.py      # Feature 엔지니어링, 난이도 추정
│       ├── simulator.py     # 시뮬레이션 학습 이력 생성
│       └── pipeline.py      # 전체 데이터 파이프라인 오케스트레이션
├── alembic/                 # DB 마이그레이션 (Alembic)
│   ├── env.py
│   └── versions/
├── uploads/                 # 사용자 아바타 업로드 임시 경로
├── models/                  # 학습된 모델 아티팩트 (git 추적)
│   ├── predictor_primary.joblib      # 오답 예측기 (XGBoost or RF, AUC 기준 선택)
│   ├── predictor_feature_names.joblib
│   ├── rec_tfidf_matrix.joblib       # 추천기 TF-IDF
│   ├── rec_user_factors.joblib       # 추천기 SVD 사용자 행렬
│   ├── rec_item_factors.joblib       # 추천기 SVD 아이템 행렬
│   ├── rec_*.joblib                  # 추천기 기타 아티팩트
│   ├── dkt_model.pth                 # DKT LSTM 가중치
│   ├── dkt_question_ids.joblib
│   ├── classifier_subject.joblib     # 분류기 (오프라인 전용)
│   ├── classifier_difficulty.joblib
│   ├── tfidf_vectorizer.joblib
│   ├── faiss_index.joblib            # FAISS 인덱스 (레거시, 오프라인 전용)
│   └── sentence_embeddings.npy       # MiniLM 384-dim (레거시, 오프라인 전용)
├── outputs/                 # 데이터 파이프라인 산출물
│   ├── questions.csv        # 문제 마스터 (시딩 소스)
│   └── user_logs.csv        # 시뮬레이션 학습 이력 (ML 학습용)
└── requirements_api.txt
```

### AppState — 모델 싱글턴

모든 ML 모델을 `AppState` 단일 객체로 관리해 라우터에서 참조한다.

```python
class AppState:
    # 시작 시 로드 (questions 테이블 → DB 단일 소스)
    questions_df: pd.DataFrame
    logs_df: pd.DataFrame          # user_logs.csv (오프라인 ML 산출물, 있으면 로드)

    # Lazy Loading — 첫 API 요청 시 로드
    predictor_model: object        # XGBoost or RandomForest (AUC 기준 자동 선택)
    predictor_feature_names: list
    recommender: dict              # tfidf_matrix, user_factors, item_factors
    dkt_model: DKTModel            # PyTorch LSTM
    dkt_question_ids: list
    explainer: RAGExplainer        # pgvector + Ollama (FAISS 아티팩트 불필요)

    device: torch.device           # CPU (Railway 환경)
```

> **분류기(`classifier`)**: `classifier_subject.joblib`, `classifier_difficulty.joblib` 아티팩트는 `backend/models/`에 존재하나 현재 런타임 API에서는 로드하지 않는다. 오프라인 학습·평가 용도로만 사용한다.

### 인증

- JWT Bearer 토큰 (python-jose)
- 게스트: `POST /auth/guest` → 24시간 유효 토큰, 풀이 이력 미저장
- 회원(이메일): `POST /auth/register` / `POST /auth/login` → 풀이 이력 저장 + 개인화 기능 이용
- 회원(Google): `POST /auth/google` → Google ID 토큰 검증 후 JWT 발급, 신규 계정 자동 생성
- CORS: 로컬(`localhost:5173`) + Vercel 프리뷰 URL(`https://sqld-ai-trainer*.vercel.app`) regex 자동 허용 + `CORS_ORIGINS` 환경변수로 추가 오리진 지정 가능

---

## 프론트엔드

### 구조

```
frontend/
├── src/
│   ├── services/
│   │   └── api.ts               # axios 인스턴스, API 함수 모음
│   ├── contexts/
│   │   └── AuthContext.tsx       # 인증 상태 전역 관리 (token, user, isGuest)
│   ├── pages/
│   │   ├── LandingPage.tsx
│   │   ├── LoginPage.tsx        # 이메일/비밀번호 + Google OAuth 로그인
│   │   ├── RegisterPage.tsx     # 이메일 회원가입 + Google OAuth 가입
│   │   ├── FindAccountPage.tsx  # 비밀번호 재설정
│   │   ├── QuestionListPage.tsx  # 챕터·난이도 필터, 페이지네이션
│   │   ├── QuestionDetailPage.tsx # 풀이·채점·AI 해설·오답 확률
│   │   ├── DashboardPage.tsx     # 챕터별 차트, 취약 영역
│   │   ├── RecommendPage.tsx     # DKT 추천 문제 목록
│   │   └── ProfilePage.tsx       # 프로필 정보·비밀번호 변경·계정 삭제
│   └── components/
│       ├── auth/AuthGuard.tsx    # 미인증 시 /login 리다이렉트
│       ├── layout/              # TopBar, PageLayout
│       ├── question/            # QuestionCard, ChoiceList, SqlBlock,
│       │                        # AiExplanation, RiskIndicator, FilterPanel
│       ├── dashboard/           # SummaryCard, AccuracyChart, WeakChapterList
│       ├── profile/             # ProfileBasicInfo, ProfileStats,
│       │                        # ProfilePasswordChange, ProfileDangerZone,
│       │                        # DeleteAccountModal, ProfileComingSoon
│       ├── recommend/           # RecommendCard
│       └── ui/                  # DifficultyBadge, AiBadge, Spinner, Alert, Avatar
├── vercel.json                  # SPA 라우팅 + /api/* → Railway 프록시 + COOP 헤더
└── package.json
```

### 라우팅

| 경로 | 페이지 | 인증 |
|------|--------|------|
| `/` | 랜딩 페이지 | 불필요 |
| `/login` | 로그인 | 불필요 |
| `/register` | 회원가입 | 불필요 |
| `/find-account` | 비밀번호 재설정 | 불필요 |
| `/questions` | 문제 목록 | 불필요 |
| `/questions/:id` | 문제 풀이 | 불필요 |
| `/dashboard` | 학습 대시보드 | 필요 (AuthGuard) |
| `/recommend` | 추천 문제 | 필요 (AuthGuard) |
| `/profile` | 프로필 관리 | 필요 (AuthGuard) |

### API 클라이언트 (`services/api.ts`)

axios 인스턴스에 요청 인터셉터를 설정해 `Authorization: Bearer <token>`을 자동 첨부한다.

```typescript
// 주요 API 함수
authApi.login(email, password)
authApi.register(username, email, password)
authApi.guest()

questionsApi.list({ chapter_name?, difficulty?, limit?, offset? })
questionsApi.detail(id)

logsApi.submit(question_id, selected_answer)
predictApi.errorProb(user_id, question_id)
explainApi.explain(question_id)
progressApi.get(user_id)
recommendApi.get(user_id, top_n, use_zpd)
```

---

## 코드 관리 전략

### 브랜치 전략

```
main   ─────────────────────────────────────► 프로덕션 브랜치
          ↑ PR 병합                            Railway / Vercel 자동 배포
dev    ──────────────────────────────────────► 개발 통합 브랜치
        ↑ PR 병합
feat/  ─ feat/#5 (로컬 연동 테스트)
       ─ feat/#6 (Docker + Railway 배포 설정)
fix/   ─ 버그 수정 커밋 (Railway 배포 이슈 대응)
```

- `feat/#N` / `fix/#N` 브랜치에서 작업 → `dev`로 PR 병합
- `dev`가 안정화되면 `main`으로 병합 → Railway·Vercel 자동 재배포

### 모노레포 구성

하나의 GitHub 레포지토리에 백엔드·프론트엔드를 함께 관리한다.

```
SQLD_AI_TRAINER/    ← 레포 루트
├── backend/        ← Python FastAPI (Railway 배포)
├── frontend/       ← React + TypeScript (Vercel 배포)
├── datasets/       ← 원본 JSON 데이터
├── backend/models/ ← 학습된 모델 아티팩트 (git 추적)
├── Dockerfile      ← Railway용 (backend만 포함)
└── railway.toml
```

**배포 분리**: Railway는 루트 `Dockerfile`을 빌드 (백엔드만), Vercel은 `frontend/` 디렉토리만 빌드.

### 모델 아티팩트 관리

학습된 모델(`backend/models/*.joblib`, `dkt_model.pth`)을 git으로 추적한다.

**이유**: ML 모델 재현성 확보, Railway 배포 시 별도 학습 불필요, GitHub Actions 없이 단순한 배포 파이프라인 유지.

**`.gitignore` 전략**

```
.env               ← 비밀 키 (추적 제외)
backend/*.db       ← SQLite DB (추적 제외)
.venv/             ← Python 가상환경 (추적 제외)
outputs/           ← 데이터 CSV (추적 제외 — 파이프라인으로 재생성)
backend/models/    ← 학습 아티팩트는 예외적으로 git 추적 (배포 시 재학습 불필요)
backend/models/    ← 원칙적 제외, .gitignore에서 명시적 허용 처리
```

### 환경 변수 관리

| 변수 | 위치 | 설명 |
|------|------|------|
| `DATABASE_URL` | Railway Variables | Postgres(pgvector) 연결 URL |
| `JWT_SECRET_KEY` | Railway Variables | JWT 서명 키 (32자 이상) |
| `OLLAMA_API_KEY` | Railway Variables | Ollama Cloud LLM API 키 |
| `OLLAMA_MODEL` | Railway Variables | 사용할 Ollama 모델명 (예: `qwen3.5:cloud`) |
| `OLLAMA_NUM_PREDICT` | Railway Variables | LLM 응답 최대 토큰 수 |
| `GEMINI_API_KEY` | Railway Variables | Gemini 임베딩(gemini-embedding-001) 키 |
| `CORS_ORIGINS` | Railway Variables | Vercel 도메인 (콤마 구분) |
| `R2_ACCOUNT_ID` | Railway Variables | Cloudflare R2 계정 ID (아바타 저장) |
| `R2_ACCESS_KEY_ID` | Railway Variables | R2 액세스 키 ID |
| `R2_SECRET_ACCESS_KEY` | Railway Variables | R2 시크릿 액세스 키 |
| `R2_BUCKET_NAME` | Railway Variables | R2 버킷 이름 |
| `R2_PUBLIC_URL` | Railway Variables | R2 퍼블릭 URL (아바타 이미지 서빙) |
| `VITE_API_URL` | Vercel Variables | Railway 백엔드 URL |

로컬 개발 시 **프로젝트 루트 `.env`** 파일에 설정 (`.env.example` 참고). 앱이 루트 `.env`를 로드한다 (`api/database.py`, `api/main.py`).

---

## 로컬 실행

### 환경 변수 설정

```bash
cp .env.example .env
# 프로젝트 루트 .env 파일에서 DATABASE_URL, JWT_SECRET_KEY, OLLAMA_API_KEY, GEMINI_API_KEY 설정
```

### Backend

```bash
cd backend
pip install -r requirements_api.txt
uvicorn api.main:app --reload --port 8000
```

API 문서: http://localhost:8000/docs

### Frontend

```bash
cd frontend
cp .env.example .env   # VITE_API_URL=http://localhost:8000
npm install
npm run dev
```

앱: http://localhost:5173

### Docker

```bash
docker build -t sqld-api .
docker run -p 8000:8000 --env-file .env sqld-api
```

---

## 배포

### Backend — Railway

Railway가 루트 `Dockerfile`을 빌드해 컨테이너를 배포한다.

```toml
# railway.toml
[build]
dockerfilePath = "Dockerfile"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 600   # ML 모델 로딩 시간 확보
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

**Railway 환경 변수 설정 (필수)**

| 변수 | 값 |
|------|-----|
| `DATABASE_URL` | Railway Postgres(pgvector) 플러그인 연결 URL |
| `JWT_SECRET_KEY` | 랜덤 32자 이상 문자열 |
| `OLLAMA_API_KEY` | Ollama Cloud(ollama.com)에서 발급 |
| `OLLAMA_MODEL` | 사용할 모델명 (예: `qwen3.5:cloud`) |
| `GEMINI_API_KEY` | Google AI Studio에서 발급 (문제 임베딩 적재용) |
| `CORS_ORIGINS` | `https://<vercel-domain>.vercel.app` |
| `R2_ACCOUNT_ID` | Cloudflare 대시보드 → R2 계정 ID |
| `R2_ACCESS_KEY_ID` | R2 API 토큰에서 발급 |
| `R2_SECRET_ACCESS_KEY` | R2 API 토큰 시크릿 |
| `R2_BUCKET_NAME` | 아바타 저장용 버킷 이름 |
| `R2_PUBLIC_URL` | 퍼블릭 읽기 URL (예: `https://pub-xxx.r2.dev`) |

### Frontend — Vercel

| 항목 | 값 |
|------|-----|
| Root Directory | `frontend` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| `VITE_API_URL` | `https://sqldaitrainer-production.up.railway.app` |

`frontend/vercel.json`이 SPA 라우팅, API 프록시, OAuth COOP 헤더를 처리한다.

```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://sqldaitrainer-production.up.railway.app/:path*" },
    { "source": "/(.*)", "destination": "/index.html" }
  ],
  "headers": [
    { "source": "/(.*)", "headers": [{ "key": "Cross-Origin-Opener-Policy", "value": "same-origin-allow-popups" }] }
  ]
}
```

- `/api/*` 경로는 Railway 백엔드로 프록시되어 프론트엔드 개발 중 CORS 없이 호출 가능
- `Cross-Origin-Opener-Policy` 헤더는 Google OAuth 팝업 창이 정상 작동하도록 설정

---

## API 명세

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/health` | 서버·모델 상태 확인 | 불필요 |
| POST | `/auth/register` | 회원가입 | 불필요 |
| POST | `/auth/login` | 로그인 | 불필요 |
| POST | `/auth/guest` | 게스트 토큰 발급 | 불필요 |
| GET | `/questions` | 문제 목록 (limit/offset/chapter/difficulty) | 불필요 |
| GET | `/questions/{id}` | 문제 상세 | 불필요 |
| POST | `/logs` | 풀이 결과 저장 + 정답 판정 | 필요 |
| POST | `/predict` | XGBoost 오답 확률 예측 | 필요 |
| POST | `/explain` | pgvector + Ollama RAG 해설 생성 | 불필요 |
| POST | `/recommend/{user_id}` | DKT + 하이브리드 문제 추천 | 필요 |
| GET | `/progress/{user_id}` | 챕터별 학습 진도 | 필요 |

---

## 데이터셋

`datasets/json/` 경로에 12개 챕터의 SQLD 기출 문제 JSON 파일.

| subject_id | 파트 | 챕터 |
|---|---|---|
| 1 | Part I | 데이터 모델링의 이해, 데이터 모델과 SQL |
| 2 | Part II | SQL 기본, SQL 활용, 관리구문 |
| 3 | Part III | SQL 수행 구조, 인덱스 튜닝, 조인 튜닝, 옵티마이저, 고급 SQL 튜닝, Lock과 트랜잭션 |

총 **591문제** (원본 297 + SQLD 모의고사 55~60회 294문항) — `question_type` 16종.

**JSON 스키마**
```json
{
  "subject_id": 2,
  "chapter_id": 1,
  "questions": [
    {
      "question_number": 1,
      "book_section": "II",
      "book_question_number": 1,
      "question_type": "worst_choice",
      "assets": [
        {
          "asset_type": "text_block",
          "payload": { "text": "문제 본문" }
        },
        {
          "asset_type": "sql_query",
          "payload": { "dialect": "ansi", "code": "SELECT ..." }
        }
      ],
      "choices": [
        { "choice_number": 1, "choice_kind": "keyword",  "choice_text": "INSERT",       "is_correct": false },
        { "choice_number": 2, "choice_kind": "text",     "choice_text": "보기 텍스트",   "is_correct": false },
        { "choice_number": 3, "choice_kind": "sql_query","choice_text": "SELECT * ...", "is_correct": true  }
      ],
      "answer": { "explanation": "해설 텍스트" }
    }
  ]
}
```

> `sql_query` payload 형식은 파일마다 두 가지 중 하나로 표기된다.
> - `{ "dialect": "ansi" | "plsql" | "sql_server", "code": "SELECT ..." }` — **대부분의 챕터** (`doc_builder`가 `code` 키를 파싱)
> - `{ "sql": "SELECT ..." }` — 극소수 레거시 표기
>
> `choice_kind` 가능한 값: `"keyword"` · `"text"` · `"sql_query"` · `"sql_fragment"`

---

## 기술 스택 요약

| 영역 | 기술 |
|------|------|
| API 서버 | FastAPI 0.111, uvicorn, SQLAlchemy 2.0 |
| 인증 | JWT (python-jose) + Google OAuth 2.0 (이메일·소셜 로그인 동시 지원) |
| ML 분류 | scikit-learn (TF-IDF + Logistic Regression) |
| 오답 예측 | XGBoost 2.0, RandomForest |
| 추천 | TruncatedSVD (CF) + TF-IDF 코사인 유사도 (CBF) |
| Knowledge Tracing | PyTorch 2.0 LSTM (DKT) |
| 벡터 검색 | pgvector (HNSW cosine), Gemini gemini-embedding-001 (1536-dim) |
| LLM/RAG | Ollama Cloud (qwen3.5:cloud) |
| DB | Postgres + pgvector (로컬은 SQLite 폴백, SQLAlchemy ORM) |
| Frontend | React 19, TypeScript, Vite, axios, Recharts, TanStack Query |
| 파일 저장 | Cloudflare R2 — 프로필 아바타 이미지 저장 및 퍼블릭 서빙 (S3 호환 API) |
| 배포 | Docker (Railway — 백엔드), Vercel (프론트엔드) |
