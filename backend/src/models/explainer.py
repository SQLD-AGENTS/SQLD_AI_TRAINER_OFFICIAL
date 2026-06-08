"""
RAG 기반 AI 해설 생성기 (Phase 4 — Module 1)

오답 문제 → pgvector(Gemini 1536d) 유사 문제 검색 → Ollama Cloud LLM(qwen3.5:cloud) → 한국어 해설

검색(읽기) 경로:
- question_embeddings 테이블에 이미 저장된 임베딩으로 SQL cosine(<=>) 검색 → Gemini 호출 없음
- 신규 문제는 적재(쓰기) 시점에 api.embeddings.upsert_question_embedding() 으로 임베딩되어
  즉시 검색 대상이 됨(FAISS 재빌드 불필요)
- pgvector 미지원(로컬 SQLite) 환경: 유사 문제 검색을 생략(빈 목록)하되 LLM 해설은 정상 동작
모델 미설정 / LLM 호출 실패 시 기존 explanation 필드 fallback 반환.
"""
import os
import pathlib
import re
from typing import Optional

import pandas as pd

# LLM: Ollama Cloud (방식 A — 직접 클라우드 API). 로컬 게이트웨이(방식 B)도 지원.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:cloud")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
DEFAULT_TOP_K = 3

# 응답 토큰 상한. 0 = 무제한(기본). qwen3.5 등 추론 모델은 내부 추론이 길어
# 캡을 두면 답변(content) 전에 예산이 소진돼 빈 응답이 나오므로 기본 무제한. 길이는 프롬프트로 제어.
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "0"))

# 저장된 문서 임베딩끼리의 유사 검색(읽기). 질의 문제의 임베딩(ref)을 기준으로
# 같은 active 문제 중 cosine 거리(<=>)가 가까운 순으로 k개. similarity = 1 - cosine_distance.
_SIMILAR_SQL = """
WITH ref AS (
    SELECT embedding FROM question_embeddings WHERE question_id = :qid
)
SELECT q.question_id, q.question_text, q.explanation, q.chapter_name,
       1 - (e.embedding <=> ref.embedding) AS similarity
FROM question_embeddings e
JOIN questions q ON q.question_id = e.question_id
CROSS JOIN ref
WHERE e.question_id <> :qid AND q.status = 'active'
ORDER BY e.embedding <=> ref.embedding
LIMIT :k
"""


def _strip_markdown(text: str) -> str:
    """LLM이 섞어 넣은 마크다운 기호를 제거해 평문으로 정리."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)          # **굵게** → 굵게
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)      # # 머리말 제거
    text = re.sub(r"(?m)^[ \t]*[-*_]{3,}[ \t]*$", "", text)  # --- 구분선 제거
    text = re.sub(r"(?m)^[ \t]*[*•]\s+", "- ", text)       # * 불릿 → -
    text = text.replace("**", "").replace("`", "")          # 잔여 기호
    text = re.sub(r"[ \t]*\|[ \t]*", " ", text)            # 표 파이프 → 공백
    text = re.sub(r"\n{3,}", "\n\n", text)                  # 빈 줄 축소
    return text.strip()


class RAGExplainer:
    def __init__(self, questions_df: pd.DataFrame):
        self.questions_df = questions_df.copy()
        # pgvector(Postgres) 사용 가능 여부 — 로컬 SQLite/미지원이면 유사검색 생략
        from api.database import HAS_PGVECTOR, _is_sqlite

        self.vector_mode = HAS_PGVECTOR and not _is_sqlite
        if not self.vector_mode:
            print(
                "[RAG 해설기] pgvector 미지원 환경(SQLite 등) → 유사문제 검색 생략, "
                "LLM 해설만 제공"
            )

    def retrieve_similar(self, question_id: str, k: int = DEFAULT_TOP_K) -> list:
        """question_id와 의미적으로 유사한 문제 k개 반환 (자기 자신 제외).

        question_embeddings(pgvector)에 저장된 임베딩으로 SQL cosine 검색 → Gemini 호출 없음.
        질의 문제가 아직 임베딩되지 않았거나(=신규 미적재) pgvector 미지원이면 빈 목록.
        """
        if not self.vector_mode:
            return []

        from sqlalchemy import text as _sql_text

        from api.database import engine

        try:
            with engine.connect() as conn:
                rows = (
                    conn.execute(_sql_text(_SIMILAR_SQL), {"qid": question_id, "k": k})
                    .mappings()
                    .all()
                )
        except Exception as e:  # noqa: BLE001
            print(f"[RAG 해설기] 유사문제 검색 실패 → 빈 목록: {e}")
            return []

        return [
            {
                "question_id": r["question_id"],
                "question_text": str(r["question_text"] or ""),
                "explanation": str(r["explanation"] or ""),
                "chapter_name": str(r["chapter_name"] or ""),
                "similarity": float(r["similarity"]),
            }
            for r in rows
        ]

    def _build_prompt(self, row: pd.Series, similar_rows: list) -> str:
        q_text = str(row.get("question_text", "") or "")
        q_expl = str(row.get("explanation", "") or "")

        context_parts = []
        for i, sim in enumerate(similar_rows, 1):
            context_parts.append(
                f"[유사 문제 {i}] {sim['question_text']}\n해설: {sim['explanation']}"
            )
        context_str = "\n\n".join(context_parts) if context_parts else "없음"

        return (
            f"당신은 SQLD 자격증 시험 전문 강사입니다. 아래 문제의 해설을 한국어로 작성하세요.\n\n"
            f"[문제]\n{q_text}\n\n"
            f"[기존 해설]\n{q_expl}\n\n"
            f"[참고 유사 문제]\n{context_str}\n\n"
            f"작성 규칙(반드시 지킬 것):\n"
            f"- 인사말·서론·맺음말 없이 핵심만. 전체 공백 포함 400자 내외(최대 600자)로 간결하게.\n"
            f"- 마크다운 기호 사용 금지: *, **, #, 표(|), --- 등을 절대 쓰지 말고 일반 문장으로만 작성.\n"
            f"- 다음 세 가지를 짧게 포함: 핵심 개념, 자주 하는 실수(오답 포인트), 한 줄 암기 포인트.\n"
        )

    def generate_explanation(
        self,
        question_id: str,
        similar_rows: Optional[list] = None,
    ) -> dict:
        """
        해설 생성.
        - Ollama(qwen3.5:cloud) 호출 성공 시 RAG 해설 반환 (source=rag)
        - 모델 미설정 / 호출 실패 시 기존 explanation 반환 (source=fallback)
        """
        match = self.questions_df[self.questions_df["question_id"] == question_id]
        if match.empty:
            return {
                "question_id": question_id,
                "explanation": "",
                "similar_ids": [],
                "source": "error",
            }
        row = match.iloc[0]

        if similar_rows is None:
            similar_rows = self.retrieve_similar(question_id)

        if not OLLAMA_MODEL:
            print("[RAG 해설기] OLLAMA_MODEL 미설정 → fallback")
            return {
                "question_id": question_id,
                "explanation": str(row.get("explanation", "") or ""),
                "similar_ids": [s["question_id"] for s in similar_rows],
                "source": "fallback",
            }

        try:
            import httpx
            from ollama import Client

            # 연결은 빨리 실패(5s), 생성 응답은 넉넉히 대기(기본 300s, env로 조절).
            # qwen3.5:397b 등 추론 모델은 응답이 느림(120~200s+).
            _read_to = float(os.environ.get("OLLAMA_READ_TIMEOUT", "300"))
            _timeout = httpx.Timeout(connect=5.0, read=_read_to, write=10.0, pool=5.0)
            prompt = self._build_prompt(row, similar_rows)
            if OLLAMA_API_KEY:
                # 방식 A — 직접 클라우드 API (ollama.com)
                client = Client(
                    host="https://ollama.com",
                    headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"},
                    timeout=_timeout,
                )
            else:
                # 방식 B — 로컬 Ollama 게이트웨이 (호스트에서 ollama signin 필요)
                client = Client(host=OLLAMA_BASE_URL, timeout=_timeout)
            print(
                f"[RAG 해설기] Ollama 호출: model={OLLAMA_MODEL}, "
                f"mode={'cloud' if OLLAMA_API_KEY else 'local'}"
            )
            _options = {"temperature": 0.4}
            if OLLAMA_NUM_PREDICT > 0:             # 0이면 미설정(무제한) — 추론 모델 빈 응답 방지
                _options["num_predict"] = OLLAMA_NUM_PREDICT
            response = client.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                think=False,                       # 추론 트레이스 숨김(내부 추론은 수행될 수 있음)
                options=_options,
            )
            msg = response.message
            explanation = (getattr(msg, "content", "") or "").strip()
            if not explanation:                    # thinking 모델이 content 대신 thinking에 넣은 경우
                explanation = (getattr(msg, "thinking", "") or "").strip()
            if not explanation:
                raise RuntimeError("LLM이 빈 응답을 반환 (content/thinking 모두 비어있음)")
            explanation = _strip_markdown(explanation)   # 마크다운 기호 제거 → 평문
            return {
                "question_id": question_id,
                "explanation": explanation,
                "similar_ids": [s["question_id"] for s in similar_rows],
                "source": "rag",
            }
        except Exception as e:
            print(f"[RAG 해설기] Ollama 오류 ({e}) → fallback")
            return {
                "question_id": question_id,
                "explanation": str(row.get("explanation", "") or ""),
                "similar_ids": [s["question_id"] for s in similar_rows],
                "source": "fallback",
            }


def run_rag_explainer(
    question_ids: list,
    questions_path: pathlib.Path,
    model_dir: Optional[pathlib.Path] = None,  # deprecated: pgvector 전환으로 미사용(시그니처 호환용)
    top_k: int = DEFAULT_TOP_K,
) -> list:
    """pipeline.py 진입점(오프라인 데모). 지정 question_id 목록에 대해 해설 생성 후 결과 반환.

    주의: pgvector 전환 후 유사 검색은 DB(question_embeddings)에 의존한다.
    유사 문제 컨텍스트까지 보려면 DATABASE_URL 이 임베딩 적재된 Postgres 를 가리켜야 한다
    (로컬 SQLite 면 유사검색은 생략되고 LLM 해설만 생성됨).
    """
    questions_df = pd.read_csv(questions_path)
    explainer = RAGExplainer(questions_df)

    results = []
    for qid in question_ids:
        similar = explainer.retrieve_similar(qid, k=top_k)
        result = explainer.generate_explanation(qid, similar)
        results.append(result)
        print(
            f"[RAG 해설기] {qid} → source={result['source']}, "
            f"similar={result['similar_ids']}"
        )
    return results
