import json
import pathlib
from typing import Optional, List
import pandas as pd

import doc_builder  # 해시·임베딩 입력의 단일 원천(SSOT)

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


def _is_correct(c: dict) -> bool:
    """is_correct 가 bool 또는 'True'/'False' 문자열 양쪽으로 들어오는 데이터 대응."""
    v = c.get("is_correct")
    if isinstance(v, str):
        return v.strip().lower() == "true"
    return bool(v)


def _extract_correct_choice(choices: list) -> Optional[int]:
    for c in choices:
        if _is_correct(c):
            n = c.get("choice_number")
            try:
                return int(n)
            except (TypeError, ValueError):
                return None  # 비정수 보기번호 → None (Integer 컬럼 적재 크래시 방지)
    return None


def _extract_choice_kinds(choices: list) -> List[str]:
    return [c.get("choice_kind", "") for c in choices]


def _simple_choices(choices: list) -> list:
    """DB(questions.choices)·build_doc 공용 단순화 형태 [{'number','text'}].

    이 '한' 형태를 choices 컬럼 저장과 content_hash 산출에 모두 써야 round-trip 이 맞다.
    """
    return [
        {"number": c.get("choice_number"), "text": c.get("choice_text", "")}
        for c in choices
    ]


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
            assets = q.get("assets", [])
            raw_choices = q.get("choices", [])
            simple_choices = _simple_choices(raw_choices)
            explanation = q.get("answer", {}).get("explanation", "")

            # 파생 컬럼·해시는 전부 doc_builder(SSOT)에서 — 17종 평탄화 포함
            question_text = doc_builder.build_question_text(assets)
            sql_code = doc_builder.build_sql_code(assets)
            content_hash = doc_builder.content_hash(
                doc_builder.build_doc(assets, simple_choices, explanation)
            )

            rows.append({
                "question_id": question_id,
                "subject_id": subject_id,
                "chapter_id": chapter_id,
                "chapter_name": chapter_name,
                "question_number": qnum,
                "book_section": q.get("book_section", ""),
                "book_question_number": q.get("book_question_number"),
                "exam_subject": q.get("exam_subject"),  # 기출 M 섹션만 값 존재
                "question_type": q.get("question_type", ""),
                "question_text": question_text,
                "sql_code": sql_code,
                "has_sql_asset": bool(sql_code),  # sql_ddl/dml 포함 → DDL-only 도 True
                "choice_count": len(raw_choices),
                "choice_kinds": ",".join(_extract_choice_kinds(raw_choices)),
                "choices": json.dumps(simple_choices, ensure_ascii=False),
                "correct_choice": _extract_correct_choice(raw_choices),
                "explanation": explanation,
                "assets": assets,                 # 원본 무손실 패스스루(JSON 컬럼)
                "content_hash": content_hash,     # md5(build_doc) — 임베딩 동기화 키
            })

    df = pd.DataFrame(rows)
    assert df["question_id"].is_unique, "question_id 중복 발생"
    return df


if __name__ == "__main__":
    df = parse_all()
    print(f"총 문제 수: {len(df)}")
    print(df[["question_id", "subject_id", "chapter_id", "question_type", "has_sql_asset"]].head())
