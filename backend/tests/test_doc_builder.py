"""doc_builder 회귀 테스트.

핵심 불변식: hash(parse) == hash(reload)
  json_parser(적재) 와 vectorize(재구성)가 같은 build_doc 을 쓰므로, 원본 assets 와
  JSON round-trip(=DB 저장→재로드) assets 의 build_doc 결과가 바이트 동일해야 한다.
  이게 깨지면 매 실행 전 문항이 스테일로 판정되어 무한 재임베딩이 발생한다.

pytest 없이도 실행 가능:  python backend/tests/test_doc_builder.py
pytest 로도:             python -m pytest backend/tests/test_doc_builder.py
"""
import json
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DATA = _ROOT / "backend" / "src" / "data"
sys.path.insert(0, str(_SRC_DATA))

import doc_builder as db  # noqa: E402

JSON_DIR = _ROOT / "datasets" / "json"


def _load_questions():
    out = []
    for f in sorted(JSON_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        out.extend(data["questions"])
    return out


def _simple_choices(q):
    return [
        {"number": c["choice_number"], "text": c.get("choice_text", "")}
        for c in q.get("choices", [])
    ]


# ---------------------------------------------------------------------------
# 1) 린치핀 — 전 문항 round-trip 해시 일치
# ---------------------------------------------------------------------------
def test_roundtrip_hash_equal_all_questions():
    qs = _load_questions()
    assert qs, "데이터셋이 비어 있음"
    mismatches = []
    for q in qs:
        assets = q.get("assets", [])
        choices = _simple_choices(q)
        expl = q.get("answer", {}).get("explanation", "")
        h_parse = db.content_hash(db.build_doc(assets, choices, expl))
        # DB 저장→재로드 모사: JSON round-trip
        rt_assets = json.loads(json.dumps(assets, ensure_ascii=False))
        rt_choices = json.loads(json.dumps(choices, ensure_ascii=False))
        h_reload = db.content_hash(db.build_doc(rt_assets, rt_choices, expl))
        if h_parse != h_reload:
            mismatches.append(q.get("book_section", "?"))
    assert not mismatches, f"round-trip 해시 불일치 {len(mismatches)}건: {mismatches[:10]}"


def test_all_questions_have_nonempty_doc_and_hash():
    qs = _load_questions()
    empty = []
    for q in qs:
        doc = db.build_doc(
            q.get("assets", []),
            _simple_choices(q),
            q.get("answer", {}).get("explanation", ""),
        )
        if not doc.strip() or len(db.content_hash(doc)) != 32:
            empty.append(q.get("book_section", "?"))
    assert not empty, f"빈 doc/해시 {len(empty)}건: {empty[:10]}"


# ---------------------------------------------------------------------------
# 2) M55-13 커버리지 픽스처 (35% → ~100% 회귀 기준)
# ---------------------------------------------------------------------------
def _find(book_section, num):
    for q in _load_questions():
        if q.get("book_section") == book_section and str(q.get("book_question_number")) == str(num):
            return q
    return None


def test_m55_13_coverage():
    q = _find("M55", 13)
    assert q is not None, "M55-13 문항을 찾지 못함"
    doc = db.build_doc(
        q.get("assets", []),
        _simple_choices(q),
        q.get("answer", {}).get("explanation", ""),
    )
    up = doc.upper()
    assert "DENSE_RANK" in up, "DENSE_RANK SQL 누락"
    assert "EMP" in up, "EMP 테이블 데이터 누락"
    for marker in ("[지문]", "[자료]", "[SQL]", "[보기]", "[해설]"):
        assert marker in doc, f"{marker} 섹션 누락"
    assert len(q.get("choices", [])) == 4
    # 보기 4개가 모두 [보기] 섹션에 번호로 등장
    bogi = doc.split("[보기]", 1)[1]
    for c in q["choices"]:
        assert f"{c['choice_number']})" in bogi


# ---------------------------------------------------------------------------
# 3) 직렬화 단위 케이스
# ---------------------------------------------------------------------------
def test_data_table_dict_rows():
    a = [{
        "asset_type": "data_table",
        "payload": {"name": "T", "columns": ["a", "b"],
                    "rows": [{"a": 1, "b": None}, {"a": 2, "b": "x"}]},
    }]
    txt = db.build_question_text(a)
    assert "[T] a | b :: 1, NULL; 2, x" in txt


def test_result_table_no_name_and_list_rows():
    a = [{
        "asset_type": "result_table",
        "payload": {"columns": ["c"], "rows": [["v1"], ["v2"]]},
    }]
    txt = db.build_question_text(a)
    assert "c :: v1; v2" in txt
    assert "[" not in txt.split("::")[0]  # 이름 prefix 없음


def test_erd_bare_string_passthrough():
    a = [{"asset_type": "erd", "payload": "erDiagram\n  A ||--o{ B : x"}]
    assert "erDiagram" in db.build_question_text(a)


def test_sql_types_join_and_sql_code():
    a = [
        {"asset_type": "sql_ddl", "payload": {"code": "create table t(x int);"}},
        {"asset_type": "sql_query", "payload": {"code": "select * from t;"}},
    ]
    code = db.build_sql_code(a)
    assert "create table" in code and "select * from t" in code


def test_unknown_type_leaf_fallback():
    a = [{"asset_type": "brand_new_type", "payload": {"k": ["leaf1", {"k2": "leaf2"}]}}]
    txt = db.build_question_text(a)
    assert "leaf1" in txt and "leaf2" in txt  # 키 제외, 값만


def test_truncation_over_max():
    big = "x" * 5000
    a = [{"asset_type": "data_table",
          "payload": {"name": "B", "columns": ["c"], "rows": [{"c": big}]}}]
    doc = db.build_doc(a, [], "해설")
    assert len(doc) <= db.MAX_DOC
    assert "[해설] 해설" in doc  # 해설은 보존, 절단은 [자료] 후미


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  PASS {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
