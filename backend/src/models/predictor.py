"""
오답 예측 모델 (Phase 2 — Module 2)

(user, question) 쌍에 대해 is_correct=False 확률 예측 (이진 분류)

피처:
  - 유저 레벨: 전체/난이도별/챕터별/질문유형별 정답률, 평균 풀이 시간
  - 문제 레벨: question_type, has_sql_asset, choice_kind_complexity, subject_id, chapter_id, difficulty

※ 유저 집계 피처는 전체 로그 기준 계산 (시뮬레이션 데이터이므로 허용).
  실제 서비스에서는 point-in-time 집계로 교체 필요.
"""
import pathlib
from typing import Tuple, Any

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    roc_auc_score,
    f1_score,
    precision_score,
    recall_score,
    classification_report,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier


def build_user_features(logs_df: pd.DataFrame, questions_df: pd.DataFrame) -> pd.DataFrame:
    # questions에서 difficulty, chapter_id, question_type 가져오기
    q_meta = questions_df[["question_id", "difficulty", "chapter_id", "question_type"]].copy()
    merged = logs_df.merge(q_meta, on="question_id", how="left")

    # 전체 정답률
    overall = merged.groupby("user_id")["is_correct"].mean().rename("user_overall_accuracy")

    # 난이도별 정답률
    diff_acc = (
        merged.groupby(["user_id", "difficulty"])["is_correct"]
        .mean()
        .unstack(fill_value=np.nan)
    )
    diff_acc.columns = [f"user_diff_{int(c)}_accuracy" for c in diff_acc.columns]

    # 평균 풀이 시간
    avg_time = merged.groupby("user_id")["solve_time_sec"].mean().rename("user_avg_solve_time")

    # 챕터별 정답률 (wide)
    chapter_acc = (
        merged.groupby(["user_id", "chapter_id"])["is_correct"]
        .mean()
        .unstack(fill_value=np.nan)
    )
    chapter_acc.columns = [f"user_ch{int(c)}_accuracy" for c in chapter_acc.columns]

    # 질문 유형별 정답률 (wide)
    qt_acc = (
        merged.groupby(["user_id", "question_type"])["is_correct"]
        .mean()
        .unstack(fill_value=np.nan)
    )
    qt_acc.columns = [f"user_qt_{c}_accuracy" for c in qt_acc.columns]

    user_feat = pd.concat([overall, diff_acc, avg_time, chapter_acc, qt_acc], axis=1)

    # NaN → user_overall_accuracy로 채우기
    for col in user_feat.columns:
        if col != "user_overall_accuracy":
            mask = user_feat[col].isna()
            user_feat.loc[mask, col] = user_feat.loc[mask, "user_overall_accuracy"]

    return user_feat


def build_training_matrix(
    logs_df: pd.DataFrame,
    questions_df: pd.DataFrame,
    user_features_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.Series]:
    q_feat = questions_df[[
        "question_id", "question_type_encoded", "has_sql_asset",
        "choice_kind_complexity", "subject_id", "chapter_id", "difficulty",
    ]].copy()

    # question_type_encoded=-1 재처리
    le_qt = LabelEncoder()
    q_feat["question_type_encoded"] = le_qt.fit_transform(
        questions_df["question_type"].astype(str)
    )
    q_feat["has_sql_asset"] = q_feat["has_sql_asset"].astype(int)

    merged = logs_df.merge(q_feat, on="question_id", how="left")
    merged = merged.merge(user_features_df, on="user_id", how="left")

    drop_cols = ["user_id", "question_id", "user_level", "is_correct", "submitted_at"]
    X = merged.drop(columns=[c for c in drop_cols if c in merged.columns])
    # 타겟: is_correct=False → 1 (오답), is_correct=True → 0
    y = (~logs_df["is_correct"].values).astype(int)

    # 남은 NaN 0으로
    X = X.fillna(0)
    return X, pd.Series(y, name="is_wrong")


def train_predictor(
    X: pd.DataFrame,
    y: pd.Series,
    model_type: str = "rf",
) -> Tuple[Any, dict]:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    if model_type == "xgb":
        model = XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="auc",
            random_state=42,
            verbosity=0,
        )
    else:
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )

    model.fit(X_train, y_train)

    y_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_proba >= 0.5).astype(int)

    metrics = {
        "model_type": model_type,
        "train_size": len(y_train),
        "test_size": len(y_test),
        "auc_roc": roc_auc_score(y_test, y_proba),
        "f1": f1_score(y_test, y_pred, zero_division=0),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "classification_report": classification_report(y_test, y_pred, zero_division=0),
    }
    return model, metrics


def plot_feature_importance(model, feature_names: list, save_path: pathlib.Path):
    importances = model.feature_importances_
    indices = np.argsort(importances)[-20:]  # top 20

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(range(len(indices)), importances[indices], align="center")
    ax.set_yticks(range(len(indices)))
    ax.set_yticklabels([feature_names[i] for i in indices], fontsize=9)
    ax.set_xlabel("Feature Importance")
    ax.set_title("Top 20 Feature Importances (Wrong Answer Predictor)")
    plt.tight_layout()
    save_path.parent.mkdir(exist_ok=True)
    plt.savefig(save_path, dpi=150)
    plt.close()


def _write_report(rf_metrics: dict, xgb_metrics: dict, report_dir: pathlib.Path) -> pathlib.Path:
    report_dir.mkdir(exist_ok=True)
    path = report_dir / "predictor_report.txt"
    lines = [
        "=== Wrong Answer Prediction ===",
        f"Model: RandomForest (n_estimators=200, max_depth=10)",
        f"Train size: {rf_metrics['train_size']}  |  Test size: {rf_metrics['test_size']}",
        f"AUC-ROC: {rf_metrics['auc_roc']:.3f}",
        f"F1 (binary): {rf_metrics['f1']:.3f}",
        f"Precision: {rf_metrics['precision']:.3f}  |  Recall: {rf_metrics['recall']:.3f}",
        "",
        rf_metrics["classification_report"],
        "",
        "=== XGBoost Comparison ===",
        f"Model: XGBoost (n_estimators=200, max_depth=6, lr=0.05)",
        f"AUC-ROC: {xgb_metrics['auc_roc']:.3f}",
        f"F1 (binary): {xgb_metrics['f1']:.3f}",
        f"Precision: {xgb_metrics['precision']:.3f}  |  Recall: {xgb_metrics['recall']:.3f}",
        "",
        xgb_metrics["classification_report"],
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def run_predictor(
    questions_path: pathlib.Path,
    logs_path: pathlib.Path,
    model_dir: pathlib.Path,
    report_dir: pathlib.Path,
):
    questions_df = pd.read_csv(questions_path, encoding="utf-8-sig")
    logs_df = pd.read_csv(logs_path, encoding="utf-8-sig")

    print("  [예측기] 유저 피처 생성 중...")
    user_features = build_user_features(logs_df, questions_df)

    print("  [예측기] 학습 행렬 구성 중...")
    X, y = build_training_matrix(logs_df, questions_df, user_features)
    print(f"       샘플 수: {len(X)}  |  피처 수: {X.shape[1]}  |  오답 비율: {y.mean():.1%}")

    print("  [예측기] RandomForest 학습 중...")
    rf_model, rf_metrics = train_predictor(X, y, model_type="rf")
    print(f"       AUC-ROC: {rf_metrics['auc_roc']:.3f}  |  F1: {rf_metrics['f1']:.3f}")

    print("  [예측기] XGBoost 학습 중...")
    xgb_model, xgb_metrics = train_predictor(X, y, model_type="xgb")
    print(f"       AUC-ROC: {xgb_metrics['auc_roc']:.3f}  |  F1: {xgb_metrics['f1']:.3f}")

    # 더 높은 AUC 모델을 primary로 저장
    primary = rf_model if rf_metrics["auc_roc"] >= xgb_metrics["auc_roc"] else xgb_model
    primary_name = "rf" if rf_metrics["auc_roc"] >= xgb_metrics["auc_roc"] else "xgb"

    model_dir.mkdir(exist_ok=True)
    joblib.dump(rf_model, model_dir / "predictor_rf.joblib")
    joblib.dump(xgb_model, model_dir / "predictor_xgb.joblib")
    joblib.dump(primary, model_dir / "predictor_primary.joblib")
    joblib.dump(list(X.columns), model_dir / "predictor_feature_names.joblib")
    print(f"  [예측기] Primary 모델: {primary_name}")

    img_path = report_dir / "predictor_feature_importance.png"
    plot_feature_importance(primary, list(X.columns), img_path)
    print(f"  [예측기] 피처 중요도 저장: {img_path}")

    report_path = _write_report(rf_metrics, xgb_metrics, report_dir)
    print(f"  [예측기] 보고서 저장: {report_path}")

    return {"rf": rf_metrics, "xgb": xgb_metrics}
