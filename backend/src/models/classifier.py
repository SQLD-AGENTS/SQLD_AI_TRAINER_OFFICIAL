"""
문제 자동 분류 모델 (Phase 2 — Module 1)

두 가지 멀티클래스 분류 태스크:
  - Task A: subject_id (3 클래스: 1=데이터 모델링, 2=SQL 기본, 3=SQL 튜닝)
  - Task B: difficulty_label (3 클래스: Easy, Medium, Hard)

한국어 텍스트 처리: TF-IDF char_wb n-gram (2,4) — 형태소 분석기 없이 음절 블록 단위 처리
"""
import pathlib
from typing import Tuple

import joblib
import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score, accuracy_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import LinearSVC
from sklearn.feature_extraction.text import TfidfVectorizer


def _build_text_corpus(df: pd.DataFrame) -> list:
    texts = []
    for _, row in df.iterrows():
        text = str(row["question_text"]) if pd.notna(row["question_text"]) else ""
        if row.get("has_sql_asset") and pd.notna(row.get("sql_code")):
            text = text + " " + str(row["sql_code"])
        texts.append(text.strip())
    return texts


def build_text_features(df: pd.DataFrame, vectorizer: TfidfVectorizer = None) -> Tuple[sp.spmatrix, TfidfVectorizer]:
    texts = _build_text_corpus(df)
    if vectorizer is None:
        vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            max_features=3000,
            min_df=2,
            sublinear_tf=True,
        )
        tfidf_matrix = vectorizer.fit_transform(texts)
    else:
        tfidf_matrix = vectorizer.transform(texts)
    return tfidf_matrix, vectorizer


def build_structured_features(df: pd.DataFrame, qt_encoder: LabelEncoder = None) -> Tuple[np.ndarray, LabelEncoder]:
    # question_type를 LabelEncoder로 완전 재인코딩 (-1 문제 해결)
    if qt_encoder is None:
        qt_encoder = LabelEncoder()
        qt_encoded = qt_encoder.fit_transform(df["question_type"].astype(str))
    else:
        qt_encoded = qt_encoder.transform(df["question_type"].astype(str))

    n = len(df)
    n_classes = len(qt_encoder.classes_)
    qt_onehot = np.zeros((n, n_classes), dtype=np.float32)
    qt_onehot[np.arange(n), qt_encoded] = 1.0

    has_sql = df["has_sql_asset"].astype(int).values.reshape(-1, 1)
    complexity = df["choice_kind_complexity"].fillna(0).values.reshape(-1, 1)

    return np.hstack([qt_onehot, has_sql, complexity]), qt_encoder


def _build_feature_matrix(df: pd.DataFrame, vectorizer=None, qt_encoder=None):
    tfidf_mat, vectorizer = build_text_features(df, vectorizer)
    struct_arr, qt_encoder = build_structured_features(df, qt_encoder)
    X = sp.hstack([tfidf_mat, sp.csr_matrix(struct_arr)])
    return X, vectorizer, qt_encoder


def train_classifier(
    df: pd.DataFrame,
    target: str,
    model_type: str = "lr",
) -> Tuple[object, object, object, dict]:
    X, vectorizer, qt_encoder = _build_feature_matrix(df)
    y = df[target].astype(str).values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    if model_type == "svm":
        clf = LinearSVC(C=1.0, max_iter=2000, random_state=42)
    else:
        clf = LogisticRegression(C=1.0, max_iter=1000, random_state=42)

    # 5-fold 교차 검증
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = []
    for train_idx, val_idx in skf.split(X_train.toarray() if sp.issparse(X_train) else X_train, y_train):
        X_cv_train = X_train[train_idx]
        X_cv_val = X_train[val_idx]
        clf_cv = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
        clf_cv.fit(X_cv_train, y_train[train_idx])
        cv_scores.append(accuracy_score(y_train[val_idx], clf_cv.predict(X_cv_val)))

    # 최종 모델 학습 (전체 train set)
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    metrics = {
        "train_size": len(y_train),
        "test_size": len(y_test),
        "accuracy": accuracy_score(y_test, y_pred),
        "f1_weighted": f1_score(y_test, y_pred, average="weighted", zero_division=0),
        "cv_accuracy_mean": float(np.mean(cv_scores)),
        "cv_accuracy_std": float(np.std(cv_scores)),
        "classification_report": classification_report(y_test, y_pred, zero_division=0),
    }
    return clf, vectorizer, qt_encoder, metrics


def save_models(vectorizer, qt_encoder, clf_subject, clf_difficulty, model_dir: pathlib.Path):
    model_dir.mkdir(exist_ok=True)
    joblib.dump(vectorizer, model_dir / "tfidf_vectorizer.joblib")
    joblib.dump(qt_encoder, model_dir / "qt_label_encoder.joblib")
    joblib.dump(clf_subject, model_dir / "classifier_subject.joblib")
    joblib.dump(clf_difficulty, model_dir / "classifier_difficulty.joblib")


def load_models(model_dir: pathlib.Path) -> dict:
    return {
        "vectorizer": joblib.load(model_dir / "tfidf_vectorizer.joblib"),
        "qt_encoder": joblib.load(model_dir / "qt_label_encoder.joblib"),
        "clf_subject": joblib.load(model_dir / "classifier_subject.joblib"),
        "clf_difficulty": joblib.load(model_dir / "classifier_difficulty.joblib"),
    }


def _write_report(report_lines: list, report_dir: pathlib.Path):
    report_dir.mkdir(exist_ok=True)
    path = report_dir / "classifier_report.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    return path


def run_classifier(questions_path: pathlib.Path, model_dir: pathlib.Path, report_dir: pathlib.Path):
    df = pd.read_csv(questions_path, encoding="utf-8-sig")

    print("  [분류기] subject_id 분류 모델 학습...")
    clf_subject, vectorizer, qt_encoder, m_subj = train_classifier(df, "subject_id")
    print(f"       Accuracy: {m_subj['accuracy']:.3f}  |  F1: {m_subj['f1_weighted']:.3f}  |  CV: {m_subj['cv_accuracy_mean']:.3f}±{m_subj['cv_accuracy_std']:.3f}")

    print("  [분류기] difficulty_label 분류 모델 학습...")
    # difficulty_label은 동일 벡터라이저/인코더 재사용
    X, _, _ = _build_feature_matrix(df, vectorizer, qt_encoder)
    y_diff = df["difficulty_label"].astype(str).values
    X_train, X_test, y_train, y_test = train_test_split(X, y_diff, test_size=0.2, stratify=y_diff, random_state=42)
    from sklearn.linear_model import LogisticRegression
    clf_diff = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    clf_diff.fit(X_train, y_train)
    y_pred_diff = clf_diff.predict(X_test)
    m_diff = {
        "train_size": len(y_train),
        "test_size": len(y_test),
        "accuracy": accuracy_score(y_test, y_pred_diff),
        "f1_weighted": f1_score(y_test, y_pred_diff, average="weighted", zero_division=0),
        "classification_report": classification_report(y_test, y_pred_diff, zero_division=0),
    }
    print(f"       Accuracy: {m_diff['accuracy']:.3f}  |  F1: {m_diff['f1_weighted']:.3f}")
    print("       ※ difficulty_label은 규칙 기반 레이블 / 높은 정확도는 자연스러운 결과")

    save_models(vectorizer, qt_encoder, clf_subject, clf_diff, model_dir)

    report_lines = [
        "=== Subject Classification (3 classes: 1=Modeling, 2=SQL Basics, 3=SQL Tuning) ===",
        f"Model: TF-IDF (char_wb, 2-4) + Logistic Regression",
        f"Train size: {m_subj['train_size']}  |  Test size: {m_subj['test_size']}",
        f"Accuracy: {m_subj['accuracy']:.3f}",
        f"Weighted F1: {m_subj['f1_weighted']:.3f}",
        f"CV Accuracy (5-fold): {m_subj['cv_accuracy_mean']:.3f} ± {m_subj['cv_accuracy_std']:.3f}",
        "",
        m_subj["classification_report"],
        "",
        "=== Difficulty Classification (3 classes: Easy, Medium, Hard) ===",
        f"Model: TF-IDF (char_wb, 2-4) + Logistic Regression",
        f"Train size: {m_diff['train_size']}  |  Test size: {m_diff['test_size']}",
        f"Accuracy: {m_diff['accuracy']:.3f}",
        f"Weighted F1: {m_diff['f1_weighted']:.3f}",
        "※ difficulty_label은 features.py의 규칙 기반 레이블 / 동일 피처 학습 시 높은 정확도 예상됨",
        "",
        m_diff["classification_report"],
    ]
    path = _write_report(report_lines, report_dir)
    print(f"  [분류기] 보고서 저장: {path}")

    return {"subject": m_subj, "difficulty": m_diff}
