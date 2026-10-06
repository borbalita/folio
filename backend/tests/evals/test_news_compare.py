from evals.news_compare import (
    ItemGroup,
    grounded_choice,
    group_items,
    match_items,
    normalize_url,
    url_in_text,
)
from ingest.email.news import ExtractedItem


def _item(title: str, url: str, sponsor: bool = False) -> ExtractedItem:
    return ExtractedItem(title=title, blurb="", url=url, sponsor=sponsor)


def test_normalize_url_drops_tracking_and_cosmetic_differences() -> None:
    assert normalize_url("HTTPS://Example.com/a/?utm_source=tldr&id=7#top") == (
        "https://example.com/a?id=7"
    )
    assert normalize_url("https://example.com/a?id=7") != normalize_url(
        "https://example.com/a?id=8"
    )


def test_match_prefers_url_then_similar_title() -> None:
    expected = [
        _item("OpenAI ships a model", "https://a.example/1"),
        _item("Robots learn to fold laundry", "https://b.example/2"),
        _item("Unrelated", "https://c.example/3"),
    ]
    actual = [
        _item("Robots learn to fold laundry!", "https://b.example/2-typo"),
        _item("Different wording entirely", "https://a.example/1?utm_medium=email"),
    ]

    assert match_items(expected, actual) == [(0, 1), (1, 0)]


def test_items_are_used_once() -> None:
    expected = [_item("Same", "https://a.example"), _item("Same", "https://a.example")]
    actual = [_item("Same", "https://a.example")]

    assert match_items(expected, actual) == [(0, 0)]


def test_groups_show_missing_items_url_and_sponsor_disagreements() -> None:
    runs = {
        "ref": [
            _item("Story A", "https://a.example"),
            _item("Ad", "https://ad.example", sponsor=True),
            _item("Story B", "https://b.example"),
        ],
        "cheap": [
            _item("Story A", "https://a.example"),
            _item("Ad", "https://ad.example", sponsor=False),
            _item("Story B", "https://b.example/oops"),
            _item("Story C", "https://c.example"),
        ],
    }

    groups = group_items(runs, reference="ref")
    reasons = {
        next(iter(group.versions.values())).title: group.disagreement(["ref", "cheap"])
        for group in groups
    }

    assert [next(iter(group.versions.values())).title for group in groups] == [
        "Story A",
        "Ad",
        "Story B",
        "Story C",
    ]
    assert reasons["Story A"] == []
    assert reasons["Ad"] == ["sponsor flag differs"]
    assert reasons["Story B"] == ["different URLs"]
    assert reasons["Story C"] == ["missing in ref"]


def test_unanimous_sponsor_is_still_reviewed() -> None:
    runs = {
        "ref": [_item("Ad", "https://ad.example", sponsor=True)],
        "cheap": [_item("Ad", "https://ad.example", sponsor=True)],
    }

    (group,) = group_items(runs, reference="ref")

    assert group.disagreement(["ref", "cheap"]) == ["flagged sponsor"]


def test_new_items_keep_their_reading_order_between_neighbours() -> None:
    runs = {
        "ref": [_item("A", "https://a.example"), _item("D", "https://d.example")],
        "other": [
            _item("A", "https://a.example"),
            _item("B", "https://b.example"),
            _item("C", "https://c.example"),
            _item("D", "https://d.example"),
            _item("E", "https://e.example"),
        ],
    }

    groups = group_items(runs, reference="ref")

    titles = [next(iter(group.versions.values())).title for group in groups]
    assert titles == ["A", "B", "C", "D", "E"]


def test_the_url_found_in_the_text_settles_a_url_dispute() -> None:
    body = "Read more: https://a.example/real-story (2 minute read)"
    versions = {
        "ref": _item("Story", "https://a.example/real-story"),
        "cheap": _item("Story", "https://a.example/invented"),
    }

    assert grounded_choice(versions, body) == "ref"
    group = ItemGroup(versions=versions)
    assert group.disagreement(["ref", "cheap"], body) == []
    assert group.disagreement(["ref", "cheap"]) == ["different URLs"]


def test_without_a_link_in_the_text_the_empty_url_is_right() -> None:
    versions = {
        "ref": _item("Story", ""),
        "cheap": _item("Story", "https://alphasignal.com/go/made-up"),
    }

    assert grounded_choice(versions, "No links in this edition.") == "ref"


def test_two_urls_in_the_text_need_a_person() -> None:
    body = "https://a.example/one and https://a.example/two"
    versions = {
        "ref": _item("Story", "https://a.example/one"),
        "cheap": _item("Story", "https://a.example/two"),
    }

    assert grounded_choice(versions, body) is None
    assert ItemGroup(versions=versions).disagreement(["ref", "cheap"], body) == [
        "different URLs"
    ]


def test_a_front_page_link_in_the_footer_does_not_ground_a_url() -> None:
    body = "Story text without a link. Unsubscribe | https://app.alphasignal.ai"
    versions = {
        "ref": _item("Story", ""),
        "cheap": _item("Story", "https://app.alphasignal.ai"),
    }

    assert grounded_choice(versions, body) == "ref"


def test_a_button_label_is_not_a_link() -> None:
    body = "Big launch today. READ MORE"

    assert not url_in_text("READ MORE", body)
    assert url_in_text("https://a.example/story", "see https://a.example/story")


def test_items_without_article_links_are_matched_by_title_not_position() -> None:
    expected = [_item("First story", ""), _item("Second story", ""), _item("Third story", "")]
    # The run skips the first item and puts a front-page link on another.
    actual = [_item("Second story", "https://app.alphasignal.ai"), _item("Third story", "")]

    assert match_items(expected, actual) == [(1, 0), (2, 1)]
