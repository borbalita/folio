"""Match extracted items across runs and find where the runs disagree (plan 003).

An item is identified by its normalized URL, falling back to title similarity, because
models copy long tracking URLs slightly differently and sometimes shorten titles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ingest.email.news import ExtractedItem

TITLE_MATCH = 0.85
"""Minimum title similarity for two items with different URLs to count as the same item."""


def normalize_url(url: str) -> str:
    """Comparable form: lower-case host, no utm_* parameters, fragment, or trailing slash."""
    parts = urlsplit(url.strip())
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
        ]
    )
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(
        None, left.casefold().strip(), right.casefold().strip()
    ).ratio()


def match_items(
    expected: list[ExtractedItem], actual: list[ExtractedItem]
) -> list[tuple[int, int]]:
    """Pairs of (expected index, actual index); each item is used at most once.

    Exact normalized URL first, then the most similar remaining titles above TITLE_MATCH.
    Only article links identify an item: empty URLs, front pages, and button labels repeat
    across items, so matching on them would pair items by position.
    """
    pairs: list[tuple[int, int]] = []
    free_expected = set(range(len(expected)))
    free_actual = set(range(len(actual)))

    by_url: dict[str, list[int]] = {}
    for index in sorted(free_actual):
        if is_article_link(actual[index].url):
            by_url.setdefault(normalize_url(actual[index].url), []).append(index)
    for expected_index in sorted(free_expected):
        if not is_article_link(expected[expected_index].url):
            continue
        candidates = by_url.get(normalize_url(expected[expected_index].url), [])
        if candidates:
            actual_index = candidates.pop(0)
            pairs.append((expected_index, actual_index))
            free_expected.discard(expected_index)
            free_actual.discard(actual_index)

    # Most similar first; ties go to the earlier items, so duplicates pair in reading order.
    scored = sorted(
        (
            (-title_similarity(expected[e].title, actual[a].title), e, a)
            for e in free_expected
            for a in free_actual
        ),
    )
    for negative_score, expected_index, actual_index in scored:
        if -negative_score < TITLE_MATCH:
            break
        if expected_index in free_expected and actual_index in free_actual:
            pairs.append((expected_index, actual_index))
            free_expected.discard(expected_index)
            free_actual.discard(actual_index)
    return sorted(pairs)


NEWSLETTER_HOSTS = ("tldr.tech", "tldrnewsletter.com", "alphasignal.ai")
"""The newsletters' own sites, linked from every edition's header and footer."""


def is_front_page(url: str) -> bool:
    """No path and no query beyond tracking parameters: `blog.example/?p=10062` is an article."""
    parts = urlsplit(url.strip())
    query = [
        key
        for key, _ in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    return parts.path in ("", "/") and not query


def is_own_site(url: str) -> bool:
    host = urlsplit(url.strip()).hostname or ""
    return any(host == own or host.endswith("." + own) for own in NEWSLETTER_HOSTS)


def is_article_link(url: str) -> bool:
    """An http(s) URL that isn't the newsletter's own front page. Footers link that page in
    every edition, and models sometimes copy a button label ("READ MORE") into the URL.
    A third-party front page can be the real link (TLDR links some blogs that way)."""
    parts = urlsplit(url.strip())
    return (
        parts.scheme in ("http", "https")
        and bool(parts.netloc)
        and not (is_front_page(url) and is_own_site(url))
    )


def url_in_text(url: str, body: str) -> bool:
    """A usable article link the newsletter text supports.

    Verbatim, or without the scheme ("github.com/google/ax/..."), or for GitHub the
    `owner/repo` the text names ("on GitHub at emir/claude-s40"): models rebuild those links.
    """
    if not is_article_link(url):
        return False
    url = url.strip()
    if url in body:
        return True
    parts = urlsplit(url)
    if (parts.netloc + parts.path).rstrip("/") in body:
        return True
    repo = parts.path.strip("/")
    return (
        parts.hostname in ("github.com", "www.github.com")
        and repo.count("/") == 1
        and repo in body
    )


def grounded_choice(versions: dict[str, ExtractedItem], body: str) -> str | None:
    """The run whose URL the text supports, or None when only a person can tell.

    Exactly one distinct URL found in the text wins. If no run's URL is in the text, the
    text has no link for this item, so a run that left the URL empty is right.
    """
    grounded: dict[str, str] = {}
    for run, item in versions.items():
        if url_in_text(item.url, body):
            grounded.setdefault(normalize_url(item.url), run)
    if len(grounded) == 1:
        return next(iter(grounded.values()))
    if not grounded:
        return next(
            (run for run, item in versions.items() if not item.url.strip()), None
        )
    return None


@dataclass
class ItemGroup:
    """One item as each run saw it; run name -> that run's version, missing when it lacked it."""

    versions: dict[str, ExtractedItem] = field(default_factory=dict)
    position: float = 0.0
    """Where it appears in the newsletter, for showing groups in reading order."""

    def disagreement(self, runs: list[str], body: str | None = None) -> list[str]:
        """Why this group needs a human decision; empty when every run agrees on news.

        With the newsletter text, URL differences the text settles are not counted.
        """
        reasons: list[str] = []
        missing = [run for run in runs if run not in self.versions]
        if missing:
            reasons.append("missing in " + ", ".join(missing))
        if len({normalize_url(item.url) for item in self.versions.values()}) > 1 and (
            body is None or grounded_choice(self.versions, body) is None
        ):
            reasons.append("different URLs")
        flags = {item.sponsor for item in self.versions.values()}
        if len(flags) > 1:
            reasons.append("sponsor flag differs")
        elif flags == {True}:
            reasons.append("flagged sponsor")
        return reasons


def group_items(
    runs: dict[str, list[ExtractedItem]], reference: str
) -> list[ItemGroup]:
    """Line up every run's items for one newsletter, starting from the reference run."""
    groups = [
        ItemGroup(versions={reference: item}, position=index)
        for index, item in enumerate(runs[reference])
    ]
    for name, items in runs.items():
        if name == reference:
            continue
        anchors = [next(iter(group.versions.values())) for group in groups]
        matched = {a: e for e, a in match_items(anchors, items)}
        previous = -1.0
        for index, item in enumerate(items):
            if index in matched:
                group = groups[matched[index]]
                group.versions[name] = item
                previous = group.position
                continue
            # Not in any run so far: place it between its neighbours in this run's order.
            following = next(
                (
                    groups[matched[i]].position
                    for i in range(index + 1, len(items))
                    if i in matched
                ),
                previous + 1.0,
            )
            previous = (previous + following) / 2
            groups.append(ItemGroup(versions={name: item}, position=previous))
    return sorted(groups, key=lambda group: group.position)
