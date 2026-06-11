"""
임베딩 입력·content_hash 의 단일 원천(SSOT).

build_doc(assets, choices, explanation) 가 5섹션 문서를 만들고 content_hash() 가 그 md5 를
낸다. json_parser(적재 시 해시 생성)와 vectorize_questions(임베딩 시 재구성)가 '같은 함수'를
호출하므로 해시-임베딩 입력이 절대 어긋나지 않는다(멱등의 린치핀).

입력은 DB 에 저장되는 형태와 동일해야 한다(round-trip 일치가 핵심 불변식):
    assets      : 원본 asset 배열(raw passthrough; questions.assets 컬럼)
    choices     : 단순화 [{"number","text"}] 목록(questions.choices 컬럼)
    explanation : 해설 텍스트(questions.explanation 컬럼)

직렬화 규칙(17종):
    text_block                         → [지문]
    sql_query / sql_ddl / sql_dml      → [SQL]
    data_table / result_table          → [자료] 표 포맷 '[name] c1 | c2 :: v,v; v,v'
    erd                                → [자료] bare mermaid 그대로
    그 외(list_items/entity_schema/...)→ [자료] leaf 깊이우선(dict 키 제외, 값만)
    미지 타입                          → leaf 직렬화 + 경고(생성 문항 신규 타입 대비)

3,000자 초과 시 [자료] 후미 절단(해시는 절단 후 텍스트 기준).
"""
import hashlib
import logging

logger = logging.getLogger(__name__)

MAX_DOC = 3000

TEXT_TYPES = {"text_block"}
SQL_TYPES = {"sql_query", "sql_ddl", "sql_dml"}
TABLE_TYPES = {"data_table", "result_table"}

# leaf 직렬화로 처리하는 '알려진' 타입 — 미지 타입 경고 억제용
_KNOWN_TYPES = TEXT_TYPES | SQL_TYPES | TABLE_TYPES | {
    "erd",
    "list_items",
    "entity_schema",
    "execution_plan",
    "schema_variant_pair",
    "sql_trace",
    "functional_dependency",
    "code_compare",
    "transaction_steps",
    "concurrent_timeline",
    "awr_report",
}


def _cell(v) -> str:
    """표 셀·leaf 값의 결정적 문자열화. None → 'NULL'(SQL 의미)."""
    if v is None:
        return "NULL"
    return str(v)


def _asset_payload(a):
    return a.get("payload") if isinstance(a, dict) else None


def _leaf_serialize(node) -> str:
    """dict 키 제외, 모든 leaf 값을 깊이우선으로 모아 공백 결합(삽입순서 보존)."""
    out = []

    def walk(n):
        if isinstance(n, dict):
            for v in n.values():
                walk(v)
        elif isinstance(n, (list, tuple)):
            for v in n:
                walk(v)
        else:
            out.append(_cell(n))

    walk(node)
    return " ".join(s for s in out if s != "")


def _table_text(payload, with_name: bool) -> str:
    """data_table/result_table → '[name] c1 | c2 :: r1,r1; r2,r2' (전체 행).

    rows 는 list[dict](data_table/result_table) 또는 list[list] 모두 허용.
    """
    if not isinstance(payload, dict):
        return _leaf_serialize(payload)
    cols = payload.get("columns") or []
    rows = payload.get("rows") or []
    head = " | ".join(_cell(c) for c in cols)
    row_strs = []
    for row in rows:
        if isinstance(row, dict):
            vals = (
                [_cell(row.get(c)) for c in cols]
                if cols
                else [_cell(v) for v in row.values()]
            )
        elif isinstance(row, (list, tuple)):
            vals = [_cell(v) for v in row]
        else:
            vals = [_cell(row)]
        row_strs.append(", ".join(vals))
    body = "; ".join(row_strs)
    name = payload.get("name") if with_name else None
    prefix = f"[{name}] " if name else ""
    return f"{prefix}{head} :: {body}".strip()


def _flatten_asset(a) -> str:
    """[자료] 한 asset → 텍스트. 표/erd 전용 포맷, 그 외 leaf."""
    t = a.get("asset_type") if isinstance(a, dict) else None
    p = _asset_payload(a)
    if t == "data_table":
        return _table_text(p, with_name=True)
    if t == "result_table":
        return _table_text(p, with_name=False)
    if t == "erd":
        return p if isinstance(p, str) else _leaf_serialize(p)
    if t not in _KNOWN_TYPES:
        logger.warning("doc_builder: 미지 asset_type %r → leaf 직렬화 폴백", t)
    return _leaf_serialize(p)


def _join_text_blocks(assets) -> str:
    out = []
    for a in assets or []:
        if isinstance(a, dict) and a.get("asset_type") in TEXT_TYPES:
            p = _asset_payload(a)
            if isinstance(p, dict):
                out.append(str(p.get("text", "")))
            elif isinstance(p, str):
                out.append(p)
    return " ".join(s for s in out if s).strip()


def _join_sql(assets) -> str:
    out = []
    for a in assets or []:
        if isinstance(a, dict) and a.get("asset_type") in SQL_TYPES:
            p = _asset_payload(a)
            code = p.get("code", "") if isinstance(p, dict) else str(p or "")
            if code:
                out.append(code)
    return "\n".join(out).strip()


def _join_jaryo(assets) -> str:
    out = []
    for a in assets or []:
        if not isinstance(a, dict):
            continue
        t = a.get("asset_type")
        if t in TEXT_TYPES or t in SQL_TYPES:
            continue  # [지문]/[SQL] 로 분리
        s = _flatten_asset(a)
        if s:
            out.append(s)
    return " ".join(out).strip()


def _format_choices(choices) -> str:
    """단순화 choices [{'number','text'}] → '1) text / 2) text'. payload·정답마킹 제외."""
    out = []
    for c in choices or []:
        if not isinstance(c, dict):
            continue
        num = c.get("number", c.get("choice_number", ""))
        txt = c.get("text", c.get("choice_text", ""))
        out.append(f"{_cell(num)}) {_cell(txt)}".strip())
    return " / ".join(out).strip()


def _assemble(jimun, jaryo, sql, bogi, expl) -> str:
    parts = []
    if jimun:
        parts.append("[지문] " + jimun)
    if jaryo:
        parts.append("[자료] " + jaryo)
    if sql:
        parts.append("[SQL] " + sql)
    if bogi:
        parts.append("[보기] " + bogi)
    if expl:
        parts.append("[해설] " + expl)
    return "\n".join(parts)


def build_doc(assets, choices=None, explanation="") -> str:
    """임베딩·해시 입력 문서. 5섹션(있을 때만), 3,000자 초과 시 [자료] 후미 절단."""
    jimun = _join_text_blocks(assets or [])
    jaryo = _join_jaryo(assets or [])
    sql = _join_sql(assets or [])
    bogi = _format_choices(choices or [])
    expl = (explanation or "").strip()

    doc = _assemble(jimun, jaryo, sql, bogi, expl)
    if len(doc) > MAX_DOC:
        overflow = len(doc) - MAX_DOC
        jaryo_t = jaryo[: max(0, len(jaryo) - overflow)]
        logger.warning(
            "doc_builder: 문서 %d자 > %d → [자료] %d자 절단",
            len(doc), MAX_DOC, len(jaryo) - len(jaryo_t),
        )
        doc = _assemble(jimun, jaryo_t, sql, bogi, expl)
        if len(doc) > MAX_DOC:  # 안전망(현 데이터 max 2,704자 → 미발생)
            doc = doc[:MAX_DOC]
    return doc


def build_question_text(assets) -> str:
    """파생 question_text = [지문] + [자료] 본문(라벨 없음). 표/erd 평탄화 포함."""
    jimun = _join_text_blocks(assets or [])
    jaryo = _join_jaryo(assets or [])
    return "\n".join(p for p in (jimun, jaryo) if p).strip()


def build_sql_code(assets) -> str:
    """파생 sql_code = sql_query + sql_ddl + sql_dml 코드."""
    return _join_sql(assets or [])


def content_hash(doc_text) -> str:
    """md5 hexdigest. build_doc() 결과(절단 후)를 넘긴다."""
    return hashlib.md5((doc_text or "").encode("utf-8")).hexdigest()
