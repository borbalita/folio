# 002/04 — Security alerts

Plan: [04-security-alerts.plan.md](04-security-alerts.plan.md)

## Goal
Security stories in scope reach the owner's Telegram once per incident, with real updates, and are marked on the dashboard.

## Scope
- Classifier: one structured call in the notify step, after the story rebuild, on non-demo items from the last 2 days with no classification. Input: titles, blurbs, and the last 7 days of alert headlines. Output per item: `security` and, when true, `new`, `update` or `repeat`. The prompt carries the spec's scope rubric. Results go to `news_item_notes`.
- Planning: a story with a `new` or `update` item is sent as `news_security`; it shares `news:<email>:<position>` keys with Big, so one story sends one message. `news_security` is added to the kind enum and to `ck_notifications_kind` (hand-written; autogenerate misses check changes).
- Message: `🔒 <headline>` or `🔒 Update: <headline>`, with the explanation, plus who is affected and what to do when the newsletter says.
- A failed classification logs its type and retries next run; big-story messages still go out. The job counts include classified items.
- Backfill: `python -m ingest.news_security --days 30` writes `security` only, in day batches, and never sends.
- Dashboard: Security badge, `only=security`, and the filter button. Within a day: big, security, then newsletter order.
- Update [06-notifications overview](../../../../06-notifications/overview.md), and the privacy page's Telegram line with "Last updated".

## Out of scope
- Other topics; a setting to turn alerts off; alerts for old stories.

## Acceptance criteria
- Given new items, when the notify step runs, then one classification call is made and results are stored per email and position. (test)
- Given items already classified, when the step runs again, then no call is made for them, also after re-embedding. (test)
- Given a failed classification, when the step runs, then big-story messages still go out and the next run retries. (test)
- Given a demo item, when the step runs, then it isn't classified and sends nothing. (test)
- Given an answer with an unknown item index, when it is parsed, then that entry is dropped and the rest are kept. (test)
- Given `new`, `update` and `repeat` on separate stories, when planning runs, then the first two send (`🔒` and `🔒 Update:`) and the third doesn't. (test)
- Given a story that is both big and security, when planning runs, then it sends one `news_security` message. (test)
- Given a story that gains a security item after its message went out, when planning runs, then it sends nothing more. (test)
- Given the backfill, when it runs, then no notification rows appear and `alert_status` stays null. (test)
- Given the 30-day backfill on real newsletters, when the owner reviews the list of marked and borderline unmarked items, then they agree with it, adjusting the rubric until they do. This happens before the branch merges, so no alert goes out first. (manual)
- Given PHP2Shell's real items from 22–28 Oct classified in date order, when the results are read, then one `new` and at most a few `update`s result, and the owner agrees those updates are real. (manual)
- Given a recent real security story sent to the owner's Telegram from a local run, when they read it, then they confirm it reads well. (manual)
- Given the dashboard, when the owner picks Security, then only marked stories show, with their badge. (browser)
- Given the running app, when `/privacy` opens, then the Telegram line mentions security alerts and the date is updated. (browser)

## Dependencies
002/02.

## Decisions made
- Classification keys on `(email_id, position)` and picks items whose note has no `security` value (a missing note counts), so re-embedding never reclassifies. It is the first half of the notify step and runs whether or not Telegram is on, so the dashboard gets its badges.
- Classification is a separate function, `classify_recent`, called by `_notify` before `record_notifications`. Its count is the job's `news_classified`. Because it handles model failures itself and returns 0, the big-story path is unaffected.
- A `security` verdict with no alert status stores a null status and sends nothing. An alert status on a non-security item is dropped. Items the model leaves out stay unclassified and are asked about again next run.
- One story with a `new` item and an `update` item is sent as `new` (no "Update:"), since the first alert about an incident is not an update.
- A big story whose security items are all `repeat` is still announced as a Big story. Only `new` and `update` turn a message into `news_security`.
- A security-only story (not big) is sent with the same fallback form as big stories when the explanation call fails: `🔒 <first title>`, its blurb, the links.
- The backfill covers days up to two days before today and leaves the last two to the notify step. Otherwise an item it marked would count as classified and never be alerted. It classifies one day per call with no alert history, and a failed day is counted and skipped.
- The filter value is `only=security`; `build_days` and `list_stories` take `only` (`big`, `security` or None) instead of `only_big`. A story gets the Security badge when any of its items is marked, whatever the alert status (a `repeat` is still a security story). Big stories sort first (those that are also security keep newsletter order among the big ones), then security, then the rest.
- The migration's downgrade deletes `news_security` rows, since the narrower constraint can't hold them.
- The classifier uses the newsletter-extraction model and reasoning effort settings, like the explanation call.
