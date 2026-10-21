# 001/01 — Story coverage and ranking: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** stories come back from news retrieval with their coverage, ranked big first, with a coverage line for the agent to quote.

**Architecture:** two queries. The first reads one aggregate row per story in the period (dates, `is_big`, distinct sources, item count), scoped to the user's mailboxes; Python ranks them and keeps the top `limit`. The second loads those stories' items. Ranking in Python keeps it a pure, testable function and puts the limit after ranking, not before.

**Tech Stack:** SQLAlchemy `text()` queries on Postgres, Pydantic models, pytest with fake sessions.

**Spec:** [../README.md](../README.md), task [01-coverage.md](01-coverage.md).

## Global Constraints

- Big = `news_stories.is_big` (both newsletters). Nothing about coverage is stored.
- Ranking order: `is_big` desc, sources desc, items desc, days desc, `last_seen` desc.
- Coverage line: `"both newsletters · 3 items · Oct 12–14"`; one newsletter: `"TLDR only · 1 item · Oct 12"`. Names: `tldr` → `TLDR`, `alpha_signal` → `Alpha Signal`. Dates `Oct 12`, `Oct 12–14`, `Sep 30–Oct 2` (en dash, no year).
- Every query repeats the owner scope (`scope_clause`); no mailbox → no query.
- No new dependencies.

## Review Focus

- A story whose items fall partly outside the user's mailboxes: counts and items include only the user's items (scope in both queries). Test in Task 1.
- Equal coverage: ties break by `last_seen` desc, then story id, so order is stable across calls. Test in Task 1.
- A period with a story that started before `since`: included when it overlaps (as today's `big_stories`). Test in Task 1 (SQL params).
- One item only: "1 item", not "1 items". Test in Task 2.
- An unknown source name (e.g. demo data): shown as stored, not dropped. Test in Task 2.

---

### Task 1: `Story`, ranking and `NewsRetriever.stories`

**Files:**
- Modify: `backend/app/retrieval/news/retriever.py` (replace `BigStory` and `big_stories` / `_big_stories`)
- Test: `backend/tests/retrieval/news/test_news_retriever.py`

**Interfaces:**
- Produces:
  - `class Story(BaseModel)`: `story_id: UUID`, `first_seen: date`, `last_seen: date`, `is_big: bool`, `sources: list[str]` (sorted distinct sources of the user's items), `item_count: int`, `items: list[NewsPassage]`; property `days -> int` = `(last_seen - first_seen).days + 1`.
  - `rank_stories(stories: list[Story]) -> list[Story]`: pure, the Global Constraints order, ties by `story_id`.
  - `NewsRetriever.stories(*, filters: NewsSearchFilters, limit: int, session: Session | None = None) -> list[Story]`: ranked, at most `limit`, items in source then position order; `filters.big_only` restricts to big.

- [ ] **Step 1: Write the failing tests**

```python
def test_rank_puts_big_first_then_sources_items_days_newest() -> None:
    big = _story(is_big=True, sources=["alpha_signal", "tldr"], items=2, first="2026-10-12", last="2026-10-12")
    many_items = _story(sources=["tldr"], items=4, first="2026-10-12", last="2026-10-12")
    long_run = _story(sources=["tldr"], items=1, first="2026-10-10", last="2026-10-13")
    newer = _story(sources=["tldr"], items=1, first="2026-10-14", last="2026-10-14")
    older = _story(sources=["tldr"], items=1, first="2026-10-11", last="2026-10-11")
    assert rank_stories([older, newer, long_run, many_items, big]) == [big, many_items, long_run, newer, older]

def test_rank_breaks_full_ties_by_story_id() -> None: ...  # two identical-coverage stories, order = sorted ids, both input orders

def test_stories_keeps_the_top_ranked_not_the_newest() -> None:
    # fake session: first execute() returns 3 aggregate rows (a newest single-source, an older big, a middle 2-item);
    # second execute() returns item rows for the kept ids
    stories = NewsRetriever().stories(filters=_filters(), limit=2, session=session)
    assert [s.story_id for s in stories] == [BIG_ID, TWO_ITEM_ID]
    assert session.params[1]["story_ids"] == [BIG_ID, TWO_ITEM_ID]

def test_stories_big_only_and_dates_go_into_the_aggregate_query() -> None:
    NewsRetriever().stories(filters=_filters(big_only=True, since=date(2026, 10, 12), until=date(2026, 10, 18)), limit=10, session=session)
    sql, params = session.statements[0], session.params[0]
    assert "s.is_big IS TRUE" in sql and "s.last_seen >= :since" in sql and "s.first_seen <= :until" in sql
    assert params["since"] == date(2026, 10, 12) and params["until"] == date(2026, 10, 18)

def test_stories_scope_both_queries_to_the_user() -> None: ...  # scope params (user_id, mailbox_ids) in params[0] and params[1]

def test_stories_with_no_mailbox_runs_no_query() -> None:
    assert NewsRetriever().stories(filters=_filters(mailbox_ids=[]), limit=10, session=session) == []
    assert session.statements == []
```

Replace the three `big_stories` tests with these; keep the `search` tests.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/retrieval/news/test_news_retriever.py -q` (from `backend/`)
Expected: FAIL, `ImportError: cannot import name 'rank_stories'`.

- [ ] **Step 3: Implement in `retriever.py`**

Aggregate query (one row per story with at least one in-scope item):

```sql
SELECT s.id, s.first_seen, s.last_seen, s.is_big,
       array_agg(DISTINCT ni.source ORDER BY ni.source) AS sources,
       count(ni.id) AS item_count
FROM news_stories s
JOIN news_items ni ON ni.story_id = s.id
JOIN emails e ON e.id = ni.email_id
JOIN mailboxes m ON m.id = e.mailbox_id
WHERE {scope} [AND s.is_big IS TRUE] [AND s.last_seen >= :since] [AND s.first_seen <= :until]
GROUP BY s.id, s.first_seen, s.last_seen, s.is_big
```

Rank with `rank_stories`, slice to `limit`, then load items with the existing item query restricted to `ni.story_id = ANY(:story_ids)` plus scope, ordered `ni.source, ni.position`, and attach them in ranked order.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/retrieval/news/test_news_retriever.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** `feat(news): rank stories by coverage (07-ai-news 001/01)`

### Task 2: Coverage line and story formatting; Email tool switch

**Files:**
- Modify: `backend/app/retrieval/news/formatting.py` (replace `format_big_stories`)
- Modify: `backend/app/email_assistant/tools/news.py` (`execute_list_big_news` calls `stories(filters with big_only=True, limit=settings.retrieval_top_k)` and `format_stories(..., empty="No big stories in that range.")`)
- Test: `backend/tests/retrieval/news/test_news_formatting.py`, `backend/tests/email_assistant/tools/test_news_tools.py`

**Interfaces:**
- Consumes: `Story` from Task 1.
- Produces:
  - `coverage_line(story: Story) -> str`
  - `format_stories(stories: list[Story], *, empty: str) -> str`: per story a header `"{"Big" if is_big else "Story"} — {coverage_line}"`, then its item blocks (unchanged `_item_block`), stories separated by `\n\n---\n\n`; `empty` when the list is empty.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize(("sources", "items", "first", "last", "expected"), [
    (["alpha_signal", "tldr"], 3, "2026-10-12", "2026-10-14", "both newsletters · 3 items · Oct 12–14"),
    (["tldr"], 1, "2026-10-12", "2026-10-12", "TLDR only · 1 item · Oct 12"),
    (["alpha_signal"], 2, "2026-09-30", "2026-10-02", "Alpha Signal only · 2 items · Sep 30–Oct 2"),
    (["demo_daily"], 1, "2026-10-12", "2026-10-12", "demo_daily only · 1 item · Oct 12"),
])
def test_coverage_line(sources, items, first, last, expected) -> None: ...

def test_format_marks_big_stories_and_lists_every_item_id() -> None: ...  # header "Big — both newsletters · 2 items · Oct 12", both [item ids] present
def test_format_empty_uses_the_given_text() -> None:
    assert format_stories([], empty="No big stories in that range.") == "No big stories in that range."
```

Update `test_news_tools.py`'s fake retriever to `stories(*, filters, limit, session=None)` and assert `list_big_news` passes `big_only=True`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/retrieval/news tests/email_assistant/tools/test_news_tools.py -q`
Expected: FAIL, `ImportError: cannot import name 'coverage_line'`.

- [ ] **Step 3: Implement `coverage_line` and `format_stories`; switch the Email tool**

- [ ] **Step 4: Run the fast suite**

Run: `LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY= EMAIL_RERANK=false uv run pytest -m "not integration" -q` and `uv run ruff check .`
Expected: all pass, ruff clean.

- [ ] **Step 5: Commit** `feat(news): coverage line for stories; Email list_big_news uses ranked stories (07-ai-news 001/01)`
