"""
keyword_filter.py

Final stage: pure deterministic keyword filtering (no Gemini, no
ambiguity) over the cleaned + recency-filtered postings. This is a
straightforward case-insensitive substring match against your role
keywords list - intentionally simple and predictable, since this is the
filter you said you wanted to be deterministic.
"""

KEYWORDS = [
    "software engineer",
    "engineer",
    "data",
    "data analyst",
    "data scientist",
    "statistician",
    "data engineer",
    "bioinformatics",
    "biostatistics",
    "analyst",
    "business analyst",
]

NOT_KEYWORDS = [
    "senior",
    "sr",
    "II",
    "III",
    "manager"
]


def matches_keywords(position: str, keywords: list[str] = KEYWORDS, not_kw: list[str] = NOT_KEYWORDS) -> bool:
    """
    Returns True if the posting position titles have the keywords I'm
    looking for and NOT any of the ones I'm not.
    """
    position_lower = position.lower()
    if any(kw.lower() in position_lower for kw in not_kw):
        # print('wrong position')
        return False
    else:
        # print('right position')
        return any(kw.lower() in position_lower for kw in keywords)


def filter_by_keywords(
    fresh_results: dict[str, list[dict]], keywords: list[str] = KEYWORDS, not_kw: list[str] = NOT_KEYWORDS
) -> dict[str, list[dict]]:
    """
    Takes {url: [{position, date_posted_raw, resolved_age_description}]},
    returns the same shape but only with postings whose position matches
    at least one keyword.
    """
    final_results = {}
    for url, postings in fresh_results.items():
        matched = [p for p in postings if matches_keywords(p.get("position", ""), keywords, not_kw)]
        if matched:
            final_results[url] = matched
    return final_results

# matches_keywords("engineer manager", keywords=KEYWORDS, not_kw=NOT_KEYWORDS)