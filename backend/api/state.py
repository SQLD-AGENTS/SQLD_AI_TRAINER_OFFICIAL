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
        import json as _json

        q_path = OUTPUTS_DIR / "questions.csv"
        l_path = OUTPUTS_DIR / "user_logs.csv"
        self.questions_df = pd.read_csv(q_path)
        self.logs_df = pd.read_csv(l_path)

        if "choices" not in self.questions_df.columns and JSON_DIR.exists():
            choices_map: dict = {}
            for filepath in sorted(JSON_DIR.glob("*.json")):
                data = _json.loads(filepath.read_text(encoding="utf-8"))
                sid, cid = data["subject_id"], data["chapter_id"]
                for q in data["questions"]:
                    qid = f"{sid}_{cid}_{q['question_number']}"
                    choices_map[qid] = _json.dumps(
                        [{"number": c["choice_number"], "text": c.get("choice_text", "")}
                         for c in q.get("choices", [])],
                        ensure_ascii=False,
                    )
            self.questions_df["choices"] = self.questions_df["question_id"].map(choices_map)
            print(f"[AppState] 선택지 텍스트 병합: {self.questions_df['choices'].notna().sum()}건")

        print(f"[AppState] 데이터 로드: 문제 {len(self.questions_df)}건, 로그 {len(self.logs_df)}건")

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
            self.explainer = RAGExplainer(MODEL_DIR, self.questions_df)
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
