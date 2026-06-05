"""
RAG 기반 AI 해설 생성기 (Phase 4 — Module 1)

오답 문제 → FAISS 유사 문제 검색 → Groq API(gemma2-9b-it) → 한국어 해설
API 키 없을 시 기존 explanation 필드 fallback 반환.
"""
import os
import pathlib
from typing import Optional

import numpy as np
import pandas as pd

from embedder import faiss_search, load_embedder

GROQ_MODEL = "llama-3.1-8b-instant"
DEFAULT_TOP_K = 3


class RAGExplainer:
    def __init__(self, model_dir: pathlib.Path, questions_df: pd.DataFrame):
        self.questions_df = questions_df.copy()
        artifacts = load_embedder(model_dir)
        self.embeddings: np.ndarray = artifacts["embeddings"]
        self.index = artifacts["index"]
        self.question_ids: list = artifacts["question_ids"]
        self.q_idx_map: dict = {qid: i for i, qid in enumerate(self.question_ids)}

    def retrieve_similar(self, question_id: str, k: int = DEFAULT_TOP_K) -> list:
        """question_id와 의미적으로 유사한 문제 k개 반환 (자기 자신 제외)."""
        if question_id not in self.q_idx_map:
            return []
        idx = self.q_idx_map[question_id]
        query_vec = self.embeddings[idx]
        distances, indices = faiss_search(query_vec, self.index, top_k=k + 1)

        results = []
        for dist, i in zip(distances, indices):
            if i < 0 or self.question_ids[i] == question_id:
                continue
            qid = self.question_ids[i]
            match = self.questions_df[self.questions_df["question_id"] == qid]
            if not match.empty:
                r = match.iloc[0]
                results.append({
                    "question_id": qid,
                    "question_text": str(r.get("question_text", "") or ""),
                    "explanation": str(r.get("explanation", "") or ""),
                    "chapter_name": str(r.get("chapter_name", "") or ""),
                    "similarity": float(dist),
                })
            if len(results) >= k:
                break
        return results

    def _build_prompt(self, row: pd.Series, similar_rows: list) -> str:
        q_text = str(row.get("question_text", "") or "")
        q_expl = str(row.get("explanation", "") or "")
        chapter = str(row.get("chapter_name", "") or "")
        difficulty = str(row.get("difficulty_label", "") or "")

        context_parts = []
        for i, sim in enumerate(similar_rows, 1):
            context_parts.append(
                f"[유사 문제 {i}] {sim['question_text']}\n해설: {sim['explanation']}"
            )
        context_str = "\n\n".join(context_parts) if context_parts else "없음"

        return (
            f"당신은 SQLD(SQL 개발자) 자격증 시험 전문 강사입니다.\n"
            f"아래 문제에 대해 학습자가 이해할 수 있도록 한국어로 상세하게 해설을 작성해주세요.\n\n"
            f"# 문제 정보\n"
            f"- 챕터: {chapter}\n"
            f"- 난이도: {difficulty}\n"
            f"- 문제: {q_text}\n"
            f"- 기존 해설: {q_expl}\n\n"
            f"# 참고할 유사 문제들\n{context_str}\n\n"
            f"# 작성 지침\n"
            f"1. **핵심 개념 설명**: 이 문제에서 요구하는 SQL/데이터 모델링 개념을 명확히 설명하세요\n"
            f"2. **오답 포인트**: 학습자가 자주 실수하는 부분을 강조하세요\n"
            f"3. **유사 문제와의 연결**: 위 유사 문제들과 어떤 개념이 연결되는지 설명하세요\n"
            f"4. **기억 포인트**: 시험에서 반드시 기억해야 할 핵심 사항을 정리하세요\n\n"
            f"해설을 작성해주세요:"
        )

    def generate_explanation(
        self,
        question_id: str,
        similar_rows: Optional[list] = None,
    ) -> dict:
        """
        해설 생성.
        - GEMINI_API_KEY 있으면 Gemini API 호출 (RAG)
        - 없으면 기존 explanation 반환 (fallback)
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

        api_key = os.environ.get("GROQ_API_KEY", "")
        print(f"[RAG 해설기] GROQ_API_KEY {'감지됨' if api_key else '없음 → fallback'}")
        if not api_key:
            return {
                "question_id": question_id,
                "explanation": str(row.get("explanation", "") or ""),
                "similar_ids": [s["question_id"] for s in similar_rows],
                "source": "fallback",
            }

        try:
            from groq import Groq
            prompt = self._build_prompt(row, similar_rows)
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            explanation = response.choices[0].message.content
            return {
                "question_id": question_id,
                "explanation": explanation,
                "similar_ids": [s["question_id"] for s in similar_rows],
                "source": "rag",
            }
        except Exception as e:
            print(f"[RAG 해설기] API 오류 ({e}) → fallback")
            return {
                "question_id": question_id,
                "explanation": str(row.get("explanation", "") or ""),
                "similar_ids": [s["question_id"] for s in similar_rows],
                "source": "fallback",
            }


def run_rag_explainer(
    question_ids: list,
    questions_path: pathlib.Path,
    model_dir: pathlib.Path,
    top_k: int = DEFAULT_TOP_K,
) -> list:
    """pipeline.py 진입점. 지정 question_id 목록에 대해 해설 생성 후 결과 반환."""
    questions_df = pd.read_csv(questions_path)
    explainer = RAGExplainer(model_dir, questions_df)

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
