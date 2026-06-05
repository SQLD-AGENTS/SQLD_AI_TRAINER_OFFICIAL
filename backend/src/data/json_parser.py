import json
import pathlib
from typing import Optional, Tuple, List
import pandas as pd

JSON_DIR = pathlib.Path(__file__).parents[2] / "datasets" / "json"

CHAPTER_NAMES = {
    (1, 1): "데이터 모델링의 이해",
    (1, 2): "데이터 모델과 SQL",
    (2, 1): "SQL 기본",
    (2, 2): "SQL 활용",
    (2, 3): "관리구문",
    (3, 1): "SQL 수행 구조",
    (3, 2): "SQL 분석 도구",
    (3, 3): "인덱스 튜닝",
    (3, 4): "조인 튜닝",
    (3, 5): "SQL 옵티마이저",
    (3, 6): "고급 SQL 튜닝",
    (3, 7): "Lock과 트랜잭션 동시성 제어",
}


def _extract_assets(assets: list) -> Tuple[str, str]:
    texts, sqls = [], []
    for a in assets:
        if a["asset_type"] == "text_block":
            texts.append(a["payload"].get("text", ""))
        elif a["asset_type"] == "sql_query":
            sqls.append(a["payload"].get("code", ""))
    return " ".join(texts).strip(), "\n".join(sqls).strip()


def _extract_correct_choice(choices: list) -> Optional[int]:
    for c in choices:
        if c.get("is_correct"):
            return c["choice_number"]
    return None


def _extract_choice_kinds(choices: list) -> List[str]:
    return [c.get("choice_kind", "") for c in choices]


def _extract_choices_json(choices: list) -> str:
    import json
    return json.dumps(
        [{"number": c["choice_number"], "text": c.get("choice_text", "")} for c in choices],
        ensure_ascii=False,
    )


def parse_all() -> pd.DataFrame:
    rows = []
    for filepath in sorted(JSON_DIR.glob("*.json")):
        data = json.loads(filepath.read_text(encoding="utf-8"))
        subject_id = data["subject_id"]
        chapter_id = data["chapter_id"]
        chapter_name = CHAPTER_NAMES.get((subject_id, chapter_id), "")

        for q in data["questions"]:
            qnum = q["question_number"]
            question_id = f"{subject_id}_{chapter_id}_{qnum}"
            text, sql_code = _extract_assets(q.get("assets", []))
            choice_kinds = _extract_choice_kinds(q.get("choices", []))
            correct_choice = _extract_correct_choice(q.get("choices", []))
            explanation = q.get("answer", {}).get("explanation", "")

            rows.append({
                "question_id": question_id,
                "subject_id": subject_id,
                "chapter_id": chapter_id,
                "chapter_name": chapter_name,
                "question_number": qnum,
                "book_section": q.get("book_section", ""),
                "book_question_number": q.get("book_question_number"),
                "question_type": q.get("question_type", ""),
                "question_text": text,
                "sql_code": sql_code,
                "has_sql_asset": bool(sql_code),
                "choice_count": len(q.get("choices", [])),
                "choice_kinds": ",".join(choice_kinds),
                "choices": _extract_choices_json(q.get("choices", [])),
                "correct_choice": correct_choice,
                "explanation": explanation,
            })

    df = pd.DataFrame(rows)
    assert df["question_id"].is_unique, "question_id 중복 발생"
    return df


if __name__ == "__main__":
    df = parse_all()
    print(f"총 문제 수: {len(df)}")
    print(df[["question_id", "subject_id", "chapter_id", "question_type", "has_sql_asset"]].head())
