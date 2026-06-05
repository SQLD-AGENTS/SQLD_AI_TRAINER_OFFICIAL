"""
개인화 추천 시스템 (Phase 2 — Module 3)

하이브리드 2단계 접근:
  Stage 1 — Content-Based: 최근 오답과 유사한 문제 추천 (TF-IDF cosine similarity)
  Stage 2 — Collaborative Filtering: user-item matrix SVD로 협업 필터링
  최종 점수 = alpha * content_score + (1 - alpha) * cf_score  (기본 alpha=0.7)
"""
import pathlib
from typing import Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def build_question_embeddings(questions_df: pd.DataFrame) -> Tuple[np.ndarray, TfidfVectorizer]:
    texts = []
    for _, row in questions_df.iterrows():
        text = str(row["question_text"]) if pd.notna(row["question_text"]) else ""
        explanation = str(row["explanation"]) if pd.notna(row.get("explanation")) else ""
        texts.append((text + " " + explanation).strip())

    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        max_features=2000,
        min_df=1,
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(texts).toarray()
    return tfidf_matrix, vectorizer


def build_user_item_matrix(logs_df: pd.DataFrame, questions_df: pd.DataFrame) -> pd.DataFrame:
    question_ids = questions_df["question_id"].tolist()
    pivot = (
        logs_df.groupby(["user_id", "question_id"])["is_correct"]
        .mean()
        .unstack(fill_value=0.0)
    )
    # 모든 question_id 컬럼이 존재하도록 보장
    for qid in question_ids:
        if qid not in pivot.columns:
            pivot[qid] = 0.0
    pivot = pivot[question_ids]
    return pivot


def build_cf_model(user_item_matrix: pd.DataFrame, n_components: int = 20) -> Tuple[np.ndarray, np.ndarray]:
    svd = TruncatedSVD(n_components=n_components, random_state=42)
    user_factors = svd.fit_transform(user_item_matrix.values)   # (n_users, n_components)
    item_factors = svd.components_.T                             # (n_items, n_components)
    return user_factors, item_factors


def get_user_weak_chapters(
    user_id: str,
    logs_df: pd.DataFrame,
    questions_df: pd.DataFrame,
    threshold: float = 0.5,
    top_k: int = 3,
) -> list:
    q_meta = questions_df[["question_id", "chapter_id"]].copy()
    user_logs = logs_df[logs_df["user_id"] == user_id].merge(q_meta, on="question_id", how="left")
    if user_logs.empty:
        raise ValueError(f"user_id '{user_id}'의 학습 이력이 없습니다.")

    chapter_acc = user_logs.groupby("chapter_id")["is_correct"].mean()
    weak = chapter_acc[chapter_acc < threshold].sort_values().index.tolist()
    return weak[:top_k]


def get_content_scores(
    user_id: str,
    logs_df: pd.DataFrame,
    questions_df: pd.DataFrame,
    tfidf_matrix: np.ndarray,
    top_wrong: int = 10,
) -> np.ndarray:
    user_logs = logs_df[logs_df["user_id"] == user_id].copy()
    wrong_logs = user_logs[~user_logs["is_correct"]]

    if wrong_logs.empty:
        # 오답 없으면 균등 점수
        return np.ones(len(questions_df)) / len(questions_df)

    # 최근 오답 top_wrong개
    if "submitted_at" in wrong_logs.columns:
        wrong_logs = wrong_logs.sort_values("submitted_at", ascending=False)
    recent_wrong_ids = wrong_logs["question_id"].head(top_wrong).tolist()

    question_ids = questions_df["question_id"].tolist()
    wrong_indices = [question_ids.index(qid) for qid in recent_wrong_ids if qid in question_ids]

    if not wrong_indices:
        return np.ones(len(questions_df)) / len(questions_df)

    # 오답 문제들의 평균 TF-IDF 벡터
    mean_vec = tfidf_matrix[wrong_indices].mean(axis=0, keepdims=True)
    scores = cosine_similarity(mean_vec, tfidf_matrix)[0]
    return scores


def get_cf_scores(
    user_id: str,
    user_factors: np.ndarray,
    item_factors: np.ndarray,
    user_ids: list,
) -> np.ndarray:
    if user_id not in user_ids:
        return np.zeros(item_factors.shape[0])
    idx = user_ids.index(user_id)
    scores = user_factors[idx] @ item_factors.T
    # 낮은 예측 점수(= 틀릴 것 같은 문제)를 높게 추천하도록 역전
    return 1.0 - (scores - scores.min()) / (scores.max() - scores.min() + 1e-9)


def recommend(
    user_id: str,
    logs_df: pd.DataFrame,
    questions_df: pd.DataFrame,
    tfidf_matrix: np.ndarray,
    user_factors: np.ndarray,
    item_factors: np.ndarray,
    user_ids: list,
    top_n: int = 10,
    alpha: float = 0.7,
    exclude_correct: bool = True,
    dkt_probs_map: dict = None,
    zpd_low: float = 0.3,
    zpd_high: float = 0.6,
    zpd_weight: float = 0.3,
) -> list:
    """
    하이브리드 추천. dkt_probs_map 제공 시 ZPD 보너스 적용.
    dkt_probs_map: {question_id: P(correct)} — DKT predict_next 결과 매핑.
    ZPD 조건 (zpd_low ≤ P ≤ zpd_high) 문제는 hybrid score를 (1 + zpd_weight) 배 부스트.
    """
    question_ids = questions_df["question_id"].tolist()

    # 약점 챕터 파악
    try:
        weak_chapters = get_user_weak_chapters(user_id, logs_df, questions_df)
    except ValueError:
        raise

    # 후보 문제 필터링: 약점 챕터 문제 우선 (없으면 전체)
    if weak_chapters:
        candidate_mask = questions_df["chapter_id"].isin(weak_chapters)
        candidate_df = questions_df[candidate_mask].copy()
    else:
        candidate_df = questions_df.copy()

    # 이미 정답 처리한 문제 제외
    if exclude_correct:
        user_logs = logs_df[logs_df["user_id"] == user_id]
        correct_ids = set(user_logs[user_logs["is_correct"]]["question_id"].tolist())
        candidate_df = candidate_df[~candidate_df["question_id"].isin(correct_ids)]

    if candidate_df.empty:
        candidate_df = questions_df.copy()

    candidate_indices = [question_ids.index(qid) for qid in candidate_df["question_id"].tolist()]

    # 점수 계산
    content_scores = get_content_scores(user_id, logs_df, questions_df, tfidf_matrix)
    cf_scores = get_cf_scores(user_id, user_factors, item_factors, user_ids)

    final_scores = alpha * content_scores + (1 - alpha) * cf_scores

    # DKT ZPD 보너스 적용
    if dkt_probs_map:
        boosted = []
        for i in candidate_indices:
            qid = question_ids[i]
            p = dkt_probs_map.get(qid)
            if p is not None and zpd_low <= p <= zpd_high:
                score = final_scores[i] * (1 + zpd_weight)
            else:
                score = final_scores[i]
            boosted.append((qid, score))
        boosted.sort(key=lambda x: x[1], reverse=True)
        return [qid for qid, _ in boosted[:top_n]]

    # 후보 내 상위 top_n
    candidate_scores = [(question_ids[i], final_scores[i]) for i in candidate_indices]
    candidate_scores.sort(key=lambda x: x[1], reverse=True)
    return [qid for qid, _ in candidate_scores[:top_n]]


def save_recommender(
    tfidf_matrix: np.ndarray,
    vectorizer: TfidfVectorizer,
    user_factors: np.ndarray,
    item_factors: np.ndarray,
    user_ids: list,
    question_ids: list,
    model_dir: pathlib.Path,
):
    model_dir.mkdir(exist_ok=True)
    joblib.dump(tfidf_matrix, model_dir / "rec_tfidf_matrix.joblib")
    joblib.dump(vectorizer, model_dir / "rec_tfidf_vectorizer.joblib")
    joblib.dump(user_factors, model_dir / "rec_user_factors.joblib")
    joblib.dump(item_factors, model_dir / "rec_item_factors.joblib")
    joblib.dump(user_ids, model_dir / "rec_user_ids.joblib")
    joblib.dump(question_ids, model_dir / "rec_question_ids.joblib")


def load_recommender(model_dir: pathlib.Path) -> dict:
    return {
        "tfidf_matrix": joblib.load(model_dir / "rec_tfidf_matrix.joblib"),
        "vectorizer": joblib.load(model_dir / "rec_tfidf_vectorizer.joblib"),
        "user_factors": joblib.load(model_dir / "rec_user_factors.joblib"),
        "item_factors": joblib.load(model_dir / "rec_item_factors.joblib"),
        "user_ids": joblib.load(model_dir / "rec_user_ids.joblib"),
        "question_ids": joblib.load(model_dir / "rec_question_ids.joblib"),
    }


def run_recommender(
    questions_path: pathlib.Path,
    logs_path: pathlib.Path,
    model_dir: pathlib.Path,
):
    questions_df = pd.read_csv(questions_path, encoding="utf-8-sig")
    logs_df = pd.read_csv(logs_path, encoding="utf-8-sig")

    print("  [추천기] 문제 임베딩 구축 중...")
    tfidf_matrix, vectorizer = build_question_embeddings(questions_df)
    print(f"       TF-IDF matrix: {tfidf_matrix.shape}")

    print("  [추천기] User-Item 행렬 구성 중...")
    ui_matrix = build_user_item_matrix(logs_df, questions_df)
    print(f"       User-Item matrix: {ui_matrix.shape}")

    print("  [추천기] SVD (Collaborative Filtering) 학습 중...")
    user_factors, item_factors = build_cf_model(ui_matrix, n_components=20)
    print(f"       User factors: {user_factors.shape}  |  Item factors: {item_factors.shape}")

    user_ids = ui_matrix.index.tolist()
    question_ids = questions_df["question_id"].tolist()

    save_recommender(tfidf_matrix, vectorizer, user_factors, item_factors, user_ids, question_ids, model_dir)
    print(f"  [추천기] 모델 저장 완료: {model_dir}")

    # 샘플 추천 출력 (3명: beginner, intermediate, advanced 각 1명)
    print("\n  --- 샘플 추천 결과 ---")
    for level in ["beginner", "intermediate", "advanced"]:
        sample_uid = logs_df[logs_df["user_level"] == level]["user_id"].iloc[0]
        recs = recommend(
            sample_uid, logs_df, questions_df,
            tfidf_matrix, user_factors, item_factors, user_ids,
            top_n=5,
        )
        weak = get_user_weak_chapters(sample_uid, logs_df, questions_df)
        print(f"  [{level}] {sample_uid}  약점 챕터: {weak}")
        for i, qid in enumerate(recs, 1):
            row = questions_df[questions_df["question_id"] == qid].iloc[0]
            print(f"    {i}. {qid} ({row['chapter_name']} / {row['difficulty_label']})")
    print()
