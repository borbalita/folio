from datetime import UTC, date, datetime

from evals import news_review
from evals.news_data import Newsletter
from evals.news_review import REFERENCE_RUN, Decision, Decisions, MissingItem
from evals.news_runs import NewsletterResult, RunFile
from ingest.email.news import ExtractedItem


def _newsletter(key: str, source: str = "tldr") -> Newsletter:
    return Newsletter(
        key=key,
        source=source,
        sent_date=date(2026, 9, 1),
        subject=f"Edition {key}",
        body=" ".join(
            f"https://{name}.example/story"
            for name in ("a", "ad", "b", "x", "m")
        )
        + " https://b.example/right https://b.example/wrong",
        email_id="00000000-0000-0000-0000-000000000001",
    )


def _item(title: str, url: str, sponsor: bool = False) -> ExtractedItem:
    return ExtractedItem(title=title, blurb=f"{title} blurb", url=url, sponsor=sponsor)


def _run(model: str, items: list[ExtractedItem], key: str = "n01") -> RunFile:
    return RunFile(
        version="news-test",
        model=model,
        effort=None,
        started_at=datetime(2026, 10, 6, tzinfo=UTC),
        results=[NewsletterResult(key=key, items=items)],
    )


RUNS = {
    REFERENCE_RUN: _run(
        "gpt-5.5",
        [
            _item("Agreed", "https://a.example/story"),
            _item("Ad", "https://ad.example/story", sponsor=True),
            _item("Bad URL", "https://b.example/right"),
        ],
    ),
    "cheap@none": _run(
        "cheap",
        [
            _item("Agreed", "https://a.example/story"),
            _item("Ad", "https://ad.example/story", sponsor=False),
            _item("Bad URL", "https://b.example/wrong"),
            _item("Extra", "https://x.example/story"),
        ],
    ),
}


def test_full_check_picks_a_fixed_spread_per_source() -> None:
    newsletters = [_newsletter(f"n{i:02d}", "tldr") for i in range(1, 13)] + [
        _newsletter(f"n{i:02d}", "alpha_signal") for i in range(13, 19)
    ]

    keys = news_review.full_check_keys(newsletters)

    # The middle newsletter of each third: positions 3, 7, 11 of 12 and 2, 4, 6 of 6.
    assert keys == {"n03", "n07", "n11", "n14", "n16", "n18"}


def test_only_disputed_items_are_reviewed_outside_full_checks(monkeypatch) -> None:
    monkeypatch.setattr(news_review, "full_check_keys", lambda newsletters: set())

    (review,) = news_review.build_review([_newsletter("n01")], RUNS)

    assert not review.full_check
    assert [group.reasons for group in review.groups] == [
        ["sponsor flag differs"],
        ["different URLs"],
        ["missing in gpt-5.5@default"],
    ]


def test_undecided_disputes_block_the_expected_items() -> None:
    decisions = Decisions(runs_hash="x")

    items, undecided = news_review.expected_items(_newsletter("n01"), RUNS, decisions, full=False)

    assert [item.title for item in items] == ["Agreed"]
    assert len(undecided) == 3


def test_decisions_become_expected_items_in_reading_order() -> None:
    decisions = Decisions(
        runs_hash="x",
        groups={
            "n01:1": Decision(verdict="sponsor", run=REFERENCE_RUN),
            "n01:2": Decision(verdict="news", run="cheap@none"),
            "n01:3": Decision(verdict="skip", run="cheap@none"),
        },
        missing={"n01": [MissingItem(title="Missed", url="https://m.example/story")]},
    )

    items, undecided = news_review.expected_items(_newsletter("n01"), RUNS, decisions, full=False)

    assert undecided == []
    assert [(item.title, item.url, item.sponsor) for item in items] == [
        ("Agreed", "https://a.example/story", False),
        ("Ad", "https://ad.example/story", True),
        ("Bad URL", "https://b.example/wrong", False),
        ("Missed", "https://m.example/story", False),
    ]


def test_full_check_needs_a_decision_even_where_runs_agree() -> None:
    decisions = Decisions(runs_hash="x")

    _, undecided = news_review.expected_items(_newsletter("n01"), RUNS, decisions, full=True)

    assert "n01:0" in undecided


def test_build_refuses_while_decisions_are_missing(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(news_review, "load_newsletters", lambda version: [_newsletter("n01")])
    monkeypatch.setattr(news_review, "load_runs", lambda version: RUNS)
    monkeypatch.setattr(news_review, "runs_hash", lambda version: "x")
    monkeypatch.setattr(news_review, "load_decisions", lambda version: Decisions(runs_hash="x"))
    monkeypatch.setattr(news_review, "review_dir", lambda version: tmp_path)

    assert news_review.build("news-test") == 1
    assert "still need a decision" in capsys.readouterr().err
    assert not (tmp_path / "expected.json").exists()


def test_recurring_blocks_share_a_title_key_across_editions() -> None:
    assert news_review.title_key("TLDR 2026-09-01 REACH 8 MILLION TECH PROFESSIONALS") == (
        news_review.title_key("TLDR 2026-09-02 Reach 8 million tech professionals!")
    )
    assert news_review.title_key("Advertise") != news_review.title_key("Want to work at TLDR?")


def test_unanimous_sponsors_are_accepted_outside_full_checks(monkeypatch) -> None:
    monkeypatch.setattr(news_review, "full_check_keys", lambda newsletters: set())
    runs = {
        REFERENCE_RUN: _run("gpt-5.5", [_item("Ad", "https://ad.example/story", sponsor=True)]),
        "cheap@none": _run("cheap", [_item("Ad", "https://ad.example/story", sponsor=True)]),
    }

    review = news_review.build_review([_newsletter("n01")], runs)
    items, undecided = news_review.expected_items(
        _newsletter("n01"), runs, Decisions(runs_hash="x"), full=False
    )

    assert review == []
    assert undecided == []
    assert [(item.title, item.sponsor) for item in items] == [("Ad", True)]


def test_unanimous_sponsors_are_still_shown_in_full_checks() -> None:
    runs = {
        REFERENCE_RUN: _run("gpt-5.5", [_item("Ad", "https://ad.example/story", sponsor=True)]),
        "cheap@none": _run("cheap", [_item("Ad", "https://ad.example/story", sponsor=True)]),
    }

    _, undecided = news_review.expected_items(
        _newsletter("n01"), runs, Decisions(runs_hash="x"), full=True
    )

    assert undecided == ["n01:0"]


def test_unusable_urls_become_no_link_in_the_answer_key() -> None:
    newsletter = _newsletter("n01").model_copy(
        update={"body": "Story https://a.example/story Footer https://app.alphasignal.ai READ MORE"}
    )
    runs = {
        REFERENCE_RUN: _run("gpt-5.5", [
            _item("Story", "https://a.example/story"),
            _item("Homepage", "https://app.alphasignal.ai"),
            _item("Button", "READ MORE"),
        ]),
    }

    items, _ = news_review.expected_items(newsletter, runs, Decisions(runs_hash="x"), full=False)

    assert [item.url for item in items] == ["https://a.example/story", "", ""]


def test_reference_answers_take_the_reference_run_with_usable_links_only() -> None:
    newsletter = _newsletter("n01").model_copy(
        update={"body": "Story https://a.example/story Footer https://app.alphasignal.ai"}
    )
    runs = {
        REFERENCE_RUN: _run("gpt-5.5", [
            _item("Story", "https://a.example/story"),
            _item("Ad", "https://app.alphasignal.ai", sponsor=True),
        ]),
        "cheap@none": _run("cheap", [_item("Only cheap", "https://c.example/story")]),
    }

    expected = news_review.reference_answers([newsletter], runs)

    assert expected["n01"]["review"] == "reference"
    assert [(item["title"], item["url"], item["sponsor"]) for item in expected["n01"]["items"]] == [
        ("Story", "https://a.example/story", False),
        ("Ad", "", True),
    ]
