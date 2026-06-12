"""
앱 시작 시 ML 모델과 데이터를 한 번만 로드해 app.state에 보관.
각 요청마다 재로드하지 않도록 startup 이벤트에서 호출.
"""
import pathlib
import sys

import pandas as pd

# src/models 를 import 경로에 추가
_SRC_MODELS = pathlib.Path(__file__).resolve().parent.parent / "src" / "models"
if str(_SRC_MODELS) not in sys.path:
    sys.path.insert(0, str(_SRC_MODELS))

MODEL_DIR = pathlib.Path(__file__).resolve().parent.parent / "models"
OUTPUTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "outputs"
JSON_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "datasets" / "json"

# RAG 설명 캐시 (question_id → 생성 결과): 동일 문제 중복 API 호출 방지
_explain_cache: dict = {}


class AppState:
    """FastAPI app.state 에 바인딩되는 컨테이너."""

    def __init__(self):
        self.questions_df = None  # pd.DataFrame
        self.logs_df = None  # pd.DataFrame

        # Phase 2 — 분류기 / 오답 예측기
        self.classifier = None  # dict
        self.predictor_model = None
        self.predictor_feature_names = None  # list

        # Phase 3 — 추천기 / 임베더 / DKT
        self.recommender = None  # dict
        self.dkt_model = None
        self.dkt_question_ids = None  # list
        self._device = None

        # Phase 4 — RAG 해설기
        self.explainer = None

    @property
    def device(self):
        if self._device is None:
            import torch
            self._device = torch.device("cpu")
        return self._device

    # ------------------------------------------------------------------
    def load(self) -> None:
        self._load_data()
        # recommender/predictor/DKT/RAG는 첫 요청 시 지연 로딩 (OOM 방지)
        print("[AppState] 데이터 로딩 완료 (recommender/predictor/DKT/RAG는 지연 로딩)")

    def load_recommender_if_needed(self) -> None:
        if self.recommender is None:
            self._load_recommender()

    def load_predictor_if_needed(self) -> None:
        if self.predictor_model is None:
            self._load_predictor()

    def load_dkt_if_needed(self) -> None:
        if self.dkt_model is None:
            self._load_dkt()

    def load_explainer_if_needed(self) -> None:
        if self.explainer is None:
            self._load_explainer()

    # ------------------------------------------------------------------
    def _load_data(self) -> None:
        """문제 마스터를 Postgres(questions 테이블)에서 단일 소스로 로드.

        - create_tables() 가 lifespan 에서 먼저 호출되므로 테이블은 항상 존재(빈 테이블일 수 있음)
        - choices(JSONB)는 psycopg2가 Python 객체로 역직렬화할 수 있어,
          라우터(_parse_choices)가 기대하는 JSON '문자열'로 통일해 준다.
        - user_logs.csv(시뮬레이션 학습 로그)는 오프라인 학습 산출물 → 있으면 로드(런타임 필수 아님).
        """
        import json as _json

        from sqlalchemy import text as _sql_text

        from api.database import engine  # 지연 import (순환 import 방지)

        try:
            # 서빙 풀 = status='active' 만. pending/rejected 생성문항을 추천·연습·RAG·
            # recommender(원본 591 기준 학습)에서 제외해 정합성 유지.
            self.questions_df = pd.read_sql_query(
                _sql_text("SELECT * FROM questions WHERE status = 'active'"), engine
            )
        except Exception as e:  # noqa: BLE001
            print(f"[AppState] questions 테이블 로드 실패: {e}")
            self.questions_df = pd.DataFrame()

        # Postgres(JSONB)→객체 / SQLite(JSON=TEXT)→문자열 차이를 JSON 문자열로 통일
        if "choices" in self.questions_df.columns:
            self.questions_df["choices"] = self.questions_df["choices"].apply(
                lambda v: v
                if (v is None or isinstance(v, str))
                else _json.dumps(v, ensure_ascii=False)
            )

        l_path = OUTPUTS_DIR / "user_logs.csv"
        self.logs_df = pd.read_csv(l_path) if l_path.exists() else None

        n = len(self.questions_df)
        if n == 0:
            print(
                "[AppState] ⚠ questions 테이블이 비어 있습니다. "
                "seeding 이 필요합니다 (lifespan 자동 적재 또는 `cd backend && python load_questions.py`)."
            )
        print(f"[AppState] 데이터 로드: 문제 {n}건 (source=DB)")

    def _load_recommender(self) -> None:
        try:
            from recommender import load_recommender
            self.recommender = load_recommender(MODEL_DIR)
            print("[AppState] 추천기 로드 완료")
        except Exception as e:
            print(f"[AppState] 추천기 로드 실패: {e}")

    def _load_dkt(self) -> None:
        try:
            from knowledge_tracer import load_knowledge_tracer
            self.dkt_model, self.dkt_question_ids = load_knowledge_tracer(
                MODEL_DIR, self.device
            )
            self.dkt_model.eval()
            print("[AppState] DKT 모델 로드 완료")
        except Exception as e:
            print(f"[AppState] DKT 로드 실패: {e}")

    def _load_explainer(self) -> None:
        try:
            from explainer import RAGExplainer
            # pgvector(question_embeddings) 기반 검색 — FAISS 아티팩트 불필요
            self.explainer = RAGExplainer(self.questions_df)
            print("[AppState] RAG 해설기 로드 완료")
        except Exception as e:
            print(f"[AppState] RAG 해설기 로드 실패: {e}")

    def _load_predictor(self) -> None:
        try:
            import joblib
            self.predictor_model = joblib.load(MODEL_DIR / "predictor_primary.joblib")
            self.predictor_feature_names = joblib.load(
                MODEL_DIR / "predictor_feature_names.joblib"
            )
            print("[AppState] 오답 예측기 로드 완료")
        except Exception as e:
            print(f"[AppState] 오답 예측기 로드 실패: {e}")


# 싱글턴 — main.py 에서 app.state.models 로 바인딩
app_state = AppState()
explain_cache = _explain_cache
