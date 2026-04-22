"""대시보드·텔레그램과 동일한 실루엣(카테고리) 필터 — ``luxefinder-frontend`` ``LISTING_CATEGORY_FILTERS`` 와 키워드 동기화."""

from __future__ import annotations

from typing import Iterable

# 프론트 ``LISTING_CATEGORY_FILTERS`` id / keywords 와 일치해야 함
_CATEGORY_DEFS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "tote_shoulder",
        (
            "토트",
            "숄더",
            "숄더백",
            "쇼퍼",
            "네버풀",
            "neverfull",
            "갈레리아",
            "galleria",
            "book tote",
            "북토트",
        ),
    ),
    (
        "crossbody",
        ("크로스", "크로스백", "메신저", "슬링", "crossbody", "messenger"),
    ),
    (
        "clutch_chain",
        ("클러치", "woc", "체인백", "미니백", "wallet on chain"),
    ),
    (
        "top_handle",
        ("탑핸들", "탑 핸들", "사첼", "투핸들", "top handle"),
    ),
    ("backpack", ("백팩", "배낭", "럭색", "backpack")),
    ("bucket_hobo", ("버킷", "호보", "호보백", "새들", "saddle", "bucket")),
)

_ALL_IDS: frozenset[str] = frozenset(d[0] for d in _CATEGORY_DEFS)


def listing_matches_selected_categories(
    *,
    raw_title: str,
    normalized_model: str,
    selected_ids: Iterable[str] | None,
) -> bool:
    """선택이 전체(또는 비어 있음)면 통과. 그 외 OR 매칭."""
    ids = [str(x) for x in (selected_ids or []) if str(x) in _ALL_IDS]
    n = len(_ALL_IDS)
    if not ids or len(ids) >= n:
        return True
    blob = f"{raw_title} {normalized_model}".lower()
    for cid in ids:
        for def_id, kws in _CATEGORY_DEFS:
            if def_id != cid:
                continue
            if any(kw.lower() in blob for kw in kws):
                return True
    return False
