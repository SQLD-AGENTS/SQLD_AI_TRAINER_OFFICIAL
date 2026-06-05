import pandas as pd

QUESTION_TYPE_ENCODING = {
    "worst_choice": 0,
    "best_choice": 1,
    "fill_blank": 2,
    "different_result": 3,
}

CHOICE_KIND_COMPLEXITY = {
    "keyword": 0,
    "text": 1,
    "sql_fragment": 2,
    "sql_query": 3,
}


def _max_choice_complexity(choice_kinds_str: str) -> int:
    if not choice_kinds_str:
        return 0
    kinds = choice_kinds_str.split(",")
    return max(CHOICE_KIND_COMPLEXITY.get(k, 0) for k in kinds)


def _estimate_difficulty(row: pd.Series) -> int:
    """
    규칙 기반 난이도 추정 (PRD 7.4 기준)
    0=Easy, 1=Medium, 2=Hard
    """
    qtype = row["question_type"]
    subject_id = row["subject_id"]
    has_sql = row["has_sql_asset"]

    if qtype == "different_result":
        return 2  # Hard

    if qtype == "fill_blank":
        base = 1  # Medium
    else:
        base = 0  # Easy (best_choice / worst_choice)

    if has_sql and subject_id == 3:
        return 2  # Hard

    if subject_id == 3:
        base = min(base + 1, 2)

    return base


DIFFICULTY_LABEL = {0: "Easy", 1: "Medium", 2: "Hard"}


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["question_type_encoded"] = df["question_type"].map(QUESTION_TYPE_ENCODING).fillna(-1).astype(int)
    df["choice_kind_complexity"] = df["choice_kinds"].apply(_max_choice_complexity)
    df["difficulty"] = df.apply(_estimate_difficulty, axis=1)
    df["difficulty_label"] = df["difficulty"].map(DIFFICULTY_LABEL)
    return df


if __name__ == "__main__":
    from json_parser import parse_all
    df = parse_all()
    df = add_features(df)
    print(df[["question_id", "question_type_encoded", "has_sql_asset", "choice_kind_complexity", "difficulty_label"]].head(10))
    print("\ndifficulty 분포:")
    print(df["difficulty_label"].value_counts())
