"""
문제 Dense 임베딩 + FAISS 인덱스 (Phase 3 — Module 1)

사용 모델: paraphrase-multilingual-MiniLM-L12-v2 (384-dim, CPU-friendly, 한국어 지원)
인덱스 유형: IndexFlatIP (cosine = inner-product after L2 norm)
"""

import pathlib
from typing import Tuple

import faiss
import joblib
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def build_question_texts(questions_df: pd.DataFrame) -> list:
    """question_text + explanation 합쳐 정제 텍스트 리스트 반환. 행 순서 유지."""
    texts = []
    for _, row in questions_df.iterrows():
        q_text = str(row.get("question_text", "") or "")
        expl = str(row.get("explanation", "") or "")
        combined = (q_text + " " + expl).strip()
        texts.append(combined)
    return texts


def encode_questions(
    texts: list,
    model_name: str = EMBED_MODEL_NAME,
    batch_size: int = 32,
    show_progress: bool = True,
) -> np.ndarray:
    """sentence-transformers로 인코딩 후 L2 정규화. 반환: float32 ndarray (N, 384)"""
    print(f"[임베딩기] 모델 로드 중: {model_name}")
    model = SentenceTransformer(model_name)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
    )
    embeddings = np.ascontiguousarray(embeddings.astype(np.float32))
    faiss.normalize_L2(embeddings)
    print(f"[임베딩기] 인코딩 완료: {embeddings.shape}")
    return embeddings


def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """L2 정규화된 embeddings로 IndexFlatIP 생성."""
    arr = np.ascontiguousarray(embeddings.astype(np.float32))
    faiss.normalize_L2(arr)
    dim = arr.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(arr)
    print(f"[임베딩기] FAISS IndexFlatIP 구축 완료: {index.ntotal} vectors (dim={dim})")
    return index


def get_dense_content_scores(
    user_id: str,
    logs_df: pd.DataFrame,
    questions_df: pd.DataFrame,
    embeddings: np.ndarray,
    top_wrong: int = 10,
) -> np.ndarray:
    """
    사용자 최근 오답 top_wrong개 임베딩 평균 → 전체 문제 cosine 유사도 반환.
    recommender.get_content_scores 의 dense 대체 버전.
    반환: float32 ndarray (N,)
    """
    question_ids = questions_df["question_id"].tolist()
    q_idx_map = {qid: i for i, qid in enumerate(question_ids)}

    user_logs = logs_df[logs_df["user_id"] == user_id].copy()
    wrong_logs = user_logs[user_logs["is_correct"] == False].sort_values(
        "submitted_at", ascending=False
    )
    recent_wrong_ids = wrong_logs["question_id"].head(top_wrong).tolist()

    if not recent_wrong_ids:
        return np.zeros(len(question_ids), dtype=np.float32)

    indices = [q_idx_map[qid] for qid in recent_wrong_ids if qid in q_idx_map]
    if not indices:
        return np.zeros(len(question_ids), dtype=np.float32)

    query_vec = embeddings[indices].mean(axis=0)
    norm = np.linalg.norm(query_vec)
    if norm > 0:
        query_vec = query_vec / norm

    scores = embeddings @ query_vec
    return scores.astype(np.float32)


def faiss_search(
    query_vec: np.ndarray,
    index: faiss.IndexFlatIP,
    top_k: int = 10,
) -> Tuple[np.ndarray, np.ndarray]:
    """단일 쿼리 벡터에 대한 FAISS 검색. 반환: (distances, indices) 각각 shape (top_k,)"""
    q = np.ascontiguousarray(query_vec.reshape(1, -1).astype(np.float32))
    faiss.normalize_L2(q)
    distances, indices = index.search(q, top_k)
    return distances[0], indices[0]


def save_embedder(
    embeddings: np.ndarray,
    index: faiss.IndexFlatIP,
    question_ids: list,
    model_dir: pathlib.Path,
):
    """
    아티팩트 저장:
      models/sentence_embeddings.npy
      models/faiss_index.joblib   (bytes — 한글 경로 호환)
      models/embed_question_ids.joblib
    """
    model_dir.mkdir(exist_ok=True)
    np.save(str(model_dir / "sentence_embeddings.npy"), embeddings)
    # faiss.write_index 는 한글 경로 불가 → bytes로 직렬화 후 joblib 저장
    index_bytes = faiss.serialize_index(index)
    joblib.dump(index_bytes, model_dir / "faiss_index.joblib")
    joblib.dump(question_ids, model_dir / "embed_question_ids.joblib")
    print(f"[임베딩기] 아티팩트 저장 완료 → {model_dir}")


def load_embedder(model_dir: pathlib.Path) -> dict:
    """반환 keys: embeddings, index, question_ids"""
    embeddings = np.load(str(model_dir / "sentence_embeddings.npy"))
    index_bytes = joblib.load(model_dir / "faiss_index.joblib")
    index = faiss.deserialize_index(index_bytes)
    question_ids = joblib.load(model_dir / "embed_question_ids.joblib")
    return {"embeddings": embeddings, "index": index, "question_ids": question_ids}


def recommend_dense(
    user_id: str,
    logs_df: pd.DataFrame,
    questions_df: pd.DataFrame,
    embeddings: np.ndarray,
    cf_user_factors: np.ndarray,
    cf_item_factors: np.ndarray,
    rec_user_ids: list,
    top_n: int = 10,
    alpha: float = 0.7,
) -> list:
    """
    Dense 임베딩 기반 하이브리드 추천 (TF-IDF 대신 Sentence-Transformers 사용).
    추천 로직은 recommender.recommend 와 동일하게 유지.
    """
    question_ids = questions_df["question_id"].tolist()
    user_logs = logs_df[logs_df["user_id"] == user_id]

    # 약점 챕터 파악
    chapter_acc = (
        user_logs.merge(questions_df[["question_id", "chapter_id"]], on="question_id", how="left")
        .groupby("chapter_id")["is_correct"]
        .mean()
    )
    weak_chapters = chapter_acc[chapter_acc < 0.5].nsmallest(3).index.tolist()

    # 후보 문제 필터링
    if weak_chapters:
        candidates = questions_df[questions_df["chapter_id"].isin(weak_chapters)]["question_id"].tolist()
    else:
        candidates = question_ids.copy()

    # 이미 정답 처리한 문제 제외
    correct_ids = set(user_logs[user_logs["is_correct"] == True]["question_id"])
    candidates = [qid for qid in candidates if qid not in correct_ids]

    if not candidates:
        candidates = [qid for qid in question_ids if qid not in correct_ids]
    if not candidates:
        return []

    # Dense content scores
    content_scores = get_dense_content_scores(user_id, logs_df, questions_df, embeddings)
    q_idx_map = {qid: i for i, qid in enumerate(question_ids)}

    # CF scores
    cf_scores = np.zeros(len(question_ids))
    if user_id in rec_user_ids:
        u_idx = rec_user_ids.index(user_id)
        cf_pred = cf_user_factors[u_idx] @ cf_item_factors.T
        cf_scores = 1.0 - (cf_pred - cf_pred.min()) / (cf_pred.max() - cf_pred.min() + 1e-8)

    # 하이브리드 점수
    results = []
    for qid in candidates:
        idx = q_idx_map.get(qid)
        if idx is None:
            continue
        score = alpha * float(content_scores[idx]) + (1 - alpha) * float(cf_scores[idx])
        results.append((qid, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return [qid for qid, _ in results[:top_n]]


def run_embedder(
    questions_path: pathlib.Path,
    model_dir: pathlib.Path,
) -> Tuple[np.ndarray, faiss.IndexFlatIP, list]:
    """pipeline.py 진입점. 반환: (embeddings, index, question_ids)"""
    print("\n[임베딩기] questions.csv 로드 중...")
    questions_df = pd.read_csv(questions_path)
    question_ids = questions_df["question_id"].tolist()

    texts = build_question_texts(questions_df)
    embeddings = encode_questions(texts)
    index = build_faiss_index(embeddings)
    save_embedder(embeddings, index, question_ids, model_dir)

    return embeddings, index, question_ids
