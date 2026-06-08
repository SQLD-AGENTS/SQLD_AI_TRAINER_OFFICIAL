import pathlib
import sys

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from classifier import run_classifier
from predictor import run_predictor
from recommender import load_recommender, recommend, run_recommender
from embedder import get_dense_content_scores, recommend_dense, run_embedder
from knowledge_tracer import build_sequences, load_knowledge_tracer, predict_next, run_knowledge_tracer
from explainer import run_rag_explainer

OUTPUTS_DIR = pathlib.Path(__file__).parents[2] / "outputs"
MODELS_DIR  = pathlib.Path(__file__).parents[2] / "models"
REPORTS_DIR = pathlib.Path(__file__).parents[2] / "reports"


def run_recommender_comparison(
    questions_path: pathlib.Path,
    logs_path: pathlib.Path,
    embeddings: np.ndarray,
    model_dir: pathlib.Path,
    report_dir: pathlib.Path,
    n_sample_users: int = 20,
    top_n: int = 10,
) -> dict:
    """
    TF-IDF vs Dense 임베딩 추천 품질 비교.

    지표:
      - Coverage: 전체 문제 중 최소 1회 추천된 문제 비율
      - Weak-chapter Coverage: 추천 top_n 중 약점 챕터 문제 비율
    """
    questions_df = pd.read_csv(questions_path)
    logs_df = pd.read_csv(logs_path)
    rec_artifacts = load_recommender(model_dir)
    question_ids = questions_df["question_id"].tolist()
    total_questions = len(question_ids)

    # 유저 레벨별 균등 추출
    user_level_map = logs_df.drop_duplicates("user_id").set_index("user_id")["user_level"]
    sample_users = []
    for level in ["beginner", "intermediate", "advanced"]:
        users_in_level = user_level_map[user_level_map == level].index.tolist()
        n_pick = min(n_sample_users // 3, len(users_in_level))
        sample_users.extend(users_in_level[:n_pick])
    sample_users = sample_users[:n_sample_users]

    tfidf_recommended = set()
    dense_recommended = set()
    tfidf_weak_hits = []
    dense_weak_hits = []

    for user_id in sample_users:
        user_logs = logs_df[logs_df["user_id"] == user_id]
        chapter_acc = (
            user_logs.merge(questions_df[["question_id", "chapter_id"]], on="question_id", how="left")
            .groupby("chapter_id")["is_correct"]
            .mean()
        )
        weak_chapter_set = set(chapter_acc[chapter_acc < 0.5].nsmallest(3).index.tolist())
        weak_q_set = set(
            questions_df[questions_df["chapter_id"].isin(weak_chapter_set)]["question_id"]
        ) if weak_chapter_set else set()

        # TF-IDF 추천
        tfidf_recs = recommend(
            user_id=user_id,
            logs_df=logs_df,
            questions_df=questions_df,
            tfidf_matrix=rec_artifacts["tfidf_matrix"],
            user_factors=rec_artifacts["user_factors"],
            item_factors=rec_artifacts["item_factors"],
            user_ids=rec_artifacts["user_ids"],
            top_n=top_n,
        )
        tfidf_recommended.update(tfidf_recs)
        if weak_q_set:
            tfidf_weak_hits.append(len(set(tfidf_recs) & weak_q_set) / top_n)

        # Dense 추천
        dense_recs = recommend_dense(
            user_id=user_id,
            logs_df=logs_df,
            questions_df=questions_df,
            embeddings=embeddings,
            cf_user_factors=rec_artifacts["user_factors"],
            cf_item_factors=rec_artifacts["item_factors"],
            rec_user_ids=rec_artifacts["user_ids"],
            top_n=top_n,
        )
        dense_recommended.update(dense_recs)
        if weak_q_set:
            dense_weak_hits.append(len(set(dense_recs) & weak_q_set) / top_n)

    tfidf_coverage = len(tfidf_recommended) / total_questions * 100
    dense_coverage = len(dense_recommended) / total_questions * 100
    tfidf_weak_cov = np.mean(tfidf_weak_hits) * 100 if tfidf_weak_hits else 0.0
    dense_weak_cov = np.mean(dense_weak_hits) * 100 if dense_weak_hits else 0.0

    print(f"\n[추천 비교] TF-IDF Coverage: {tfidf_coverage:.1f}%  |  Dense Coverage: {dense_coverage:.1f}%")
    print(f"[추천 비교] TF-IDF Weak-chapter Cov: {tfidf_weak_cov:.1f}%  |  Dense Weak-chapter Cov: {dense_weak_cov:.1f}%")

    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "phase3_recommender_comparison.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=== Phase 3 추천 품질 비교 보고서 ===\n\n")
        f.write(f"샘플 유저 수  : {len(sample_users)}\n")
        f.write(f"Top-N         : {top_n}\n")
        f.write(f"전체 문제 수  : {total_questions}\n\n")
        f.write(f"{'지표':<25} {'TF-IDF (Phase 2)':>18} {'Dense (Phase 3)':>18}\n")
        f.write("-" * 62 + "\n")
        f.write(f"{'Coverage (%)':25} {tfidf_coverage:>18.1f} {dense_coverage:>18.1f}\n")
        f.write(f"{'Weak-chapter Coverage (%)':25} {tfidf_weak_cov:>18.1f} {dense_weak_cov:>18.1f}\n")
    print(f"[추천 비교] 보고서 저장 완료 → {report_path}")

    return {
        "tfidf_coverage": tfidf_coverage,
        "dense_coverage": dense_coverage,
        "tfidf_weak_chapter_coverage": tfidf_weak_cov,
        "dense_weak_chapter_coverage": dense_weak_cov,
    }


def run_phase4_rag_demo(
    questions_path: pathlib.Path,
    logs_path: pathlib.Path,
    model_dir: pathlib.Path,
    report_dir: pathlib.Path,
    n_wrong_per_user: int = 3,
    top_n_rec: int = 10,
) -> None:
    """
    Phase 4 데모:
      1. 레벨별 샘플 유저 오답 문제 → RAG 해설 생성
      2. DKT 확률 기반 ZPD 추천 결과 비교
    결과를 reports/phase4_rag_demo.txt에 저장.
    """
    import os
    import torch

    api_key = os.environ.get("OLLAMA_API_KEY", "")
    if not api_key:
        print("[Phase 4] 경고: OLLAMA_API_KEY 미설정 — fallback(원본 해설) 모드로 실행")
    else:
        print(f"[Phase 4] OLLAMA_API_KEY 감지됨 (앞 8자: {api_key[:8]}...)")

    questions_df = pd.read_csv(questions_path)
    logs_df = pd.read_csv(logs_path)
    rec_artifacts = load_recommender(model_dir)
    device = torch.device("cpu")

    # DKT 로드 (학습된 모델 재사용)
    try:
        dkt_model, dkt_question_ids = load_knowledge_tracer(model_dir, device)
        dkt_question_to_idx = {qid: i for i, qid in enumerate(dkt_question_ids)}
        dkt_available = True
    except Exception as e:
        print(f"[Phase 4] DKT 로드 실패 ({e}) → ZPD 스킵")
        dkt_available = False

    # 레벨별 샘플 유저 1명씩
    sample_users = []
    for level in ["beginner", "intermediate", "advanced"]:
        uids = logs_df[logs_df["user_level"] == level]["user_id"].unique()
        if len(uids) > 0:
            sample_users.append((level, uids[0]))

    report_lines = ["=== Phase 4 RAG 해설 + ZPD 추천 데모 ===\n"]

    # 오답 문제 수집 (RAG 해설 대상)
    all_wrong_qids = []
    for level, user_id in sample_users:
        user_logs = logs_df[logs_df["user_id"] == user_id]
        wrong = user_logs[~user_logs["is_correct"]].sort_values("submitted_at", ascending=False)
        wrong_qids = wrong["question_id"].head(n_wrong_per_user).tolist()
        all_wrong_qids.extend(wrong_qids)
        report_lines.append(f"\n[{level}] 유저: {user_id}  오답 샘플: {wrong_qids}")

    # RAG 해설 생성
    report_lines.append("\n\n--- RAG 해설 생성 결과 ---\n")
    unique_qids = list(dict.fromkeys(all_wrong_qids))  # 순서 유지 중복 제거
    explanations = run_rag_explainer(unique_qids, questions_path, model_dir)

    for res in explanations:
        row = questions_df[questions_df["question_id"] == res["question_id"]]
        q_text = row.iloc[0]["question_text"] if not row.empty else ""
        report_lines.append(f"\n문제 ID : {res['question_id']}")
        report_lines.append(f"문제    : {q_text[:80]}...")
        report_lines.append(f"source  : {res['source']}")
        report_lines.append(f"유사 문제: {res['similar_ids']}")
        report_lines.append(f"해설 (앞 200자):\n{res['explanation'][:200]}\n")
        report_lines.append("-" * 60)

    # DKT ZPD 추천 비교
    if dkt_available:
        report_lines.append("\n--- DKT ZPD 추천 vs 기존 하이브리드 추천 비교 ---\n")
        sequences = build_sequences(logs_df, dkt_question_ids)
        seq_map = {s["user_id"]: s for s in sequences}

        for level, user_id in sample_users:
            # DKT 확률 계산
            user_seq = seq_map.get(user_id)
            if user_seq:
                dkt_probs_arr = predict_next(dkt_model, user_seq, dkt_question_to_idx, device)
                dkt_probs_map = {
                    dkt_question_ids[i]: float(dkt_probs_arr[i])
                    for i in range(len(dkt_question_ids))
                }
                zpd_count = sum(1 for p in dkt_probs_map.values() if 0.3 <= p <= 0.6)
            else:
                dkt_probs_map = None
                zpd_count = 0

            # 기존 추천
            baseline_recs = recommend(
                user_id=user_id,
                logs_df=logs_df,
                questions_df=questions_df,
                tfidf_matrix=rec_artifacts["tfidf_matrix"],
                user_factors=rec_artifacts["user_factors"],
                item_factors=rec_artifacts["item_factors"],
                user_ids=rec_artifacts["user_ids"],
                top_n=top_n_rec,
            )

            # ZPD 적용 추천
            zpd_recs = recommend(
                user_id=user_id,
                logs_df=logs_df,
                questions_df=questions_df,
                tfidf_matrix=rec_artifacts["tfidf_matrix"],
                user_factors=rec_artifacts["user_factors"],
                item_factors=rec_artifacts["item_factors"],
                user_ids=rec_artifacts["user_ids"],
                top_n=top_n_rec,
                dkt_probs_map=dkt_probs_map,
            )

            zpd_in_baseline = len(set(zpd_recs) & set(baseline_recs))
            report_lines.append(f"\n[{level}] {user_id}  ZPD 범위 문제 수: {zpd_count}")
            report_lines.append(f"  기존 추천  Top-{top_n_rec}: {baseline_recs}")
            report_lines.append(f"  ZPD 추천   Top-{top_n_rec}: {zpd_recs}")
            report_lines.append(f"  변경된 문제 수: {top_n_rec - zpd_in_baseline}")

    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "phase4_rag_demo.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"\n[Phase 4] 데모 보고서 저장 완료 → {report_path}")


def run():
    MODELS_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)

    questions_path = OUTPUTS_DIR / "questions.csv"
    logs_path      = OUTPUTS_DIR / "user_logs.csv"

    # ── Phase 2 ─────────────────────────────────────────────────────────
    print("=" * 55)
    print("1/5  문제 자동 분류 모델 학습...")
    run_classifier(questions_path, MODELS_DIR, REPORTS_DIR)

    print("=" * 55)
    print("2/5  오답 예측 모델 학습...")
    run_predictor(questions_path, logs_path, MODELS_DIR, REPORTS_DIR)

    print("=" * 55)
    print("3/5  개인화 추천 시스템 (TF-IDF baseline) 구축...")
    run_recommender(questions_path, logs_path, MODELS_DIR)

    # ── Phase 3 ─────────────────────────────────────────────────────────
    print("=" * 55)
    print("4/5  [Phase 3] Dense 임베딩 + FAISS 인덱스 구축...")
    embeddings, faiss_index, embed_qids = run_embedder(questions_path, MODELS_DIR)

    print("=" * 55)
    print("5/5  [Phase 3] DKT (LSTM 지식 추적) 학습...")
    dkt_metrics = run_knowledge_tracer(questions_path, logs_path, MODELS_DIR, REPORTS_DIR)

    print("=" * 55)
    print("      [Phase 3] 추천 품질 비교 (TF-IDF vs Dense)...")
    run_recommender_comparison(
        questions_path, logs_path, embeddings, MODELS_DIR, REPORTS_DIR
    )

    # ── Phase 4 ─────────────────────────────────────────────────────────
    print("=" * 55)
    print("      [Phase 4] RAG 해설 생성 + DKT ZPD 추천 데모...")
    run_phase4_rag_demo(questions_path, logs_path, MODELS_DIR, REPORTS_DIR)

    print("=" * 55)
    print("\n[Phase 4 완료] RAG 해설 및 ZPD 추천 데모가 완료되었습니다.")
    print(f"  DKT Best Val AUC-ROC: {dkt_metrics.get('best_val_auc', 0):.3f}")
    print(f"  모델 경로:   {MODELS_DIR}")
    print(f"  보고서 경로: {REPORTS_DIR}")


if __name__ == "__main__":
    run()
