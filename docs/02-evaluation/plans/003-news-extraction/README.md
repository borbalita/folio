# 003 — Newsletter extraction benchmark and a cheaper extraction model

- Created: 2026-10-06
- Status: In progress
- Current stage: Implementation, 003/07.

## Approval state

Approved on 2026-10-06: real newsletters stored only in Langfuse with a private Supabase Storage backup, review where the models disagree plus a full check of 6 newsletters, the pass bar over all 64, and a separate extraction model setting that leaves production unchanged until a model passes.

Changed on 2026-10-06, during the review: no hand labelling for news-v1. The GPT-5.5 reference run is the answer key (see "Change: GPT-5.5 as the answer key").

## Problem

News extraction (`ingest/email/news.py`) sends every AI newsletter to `openai_chat_model`, the same GPT-5.5 that answers chat, at default reasoning effort. It is the main ingest cost: about $0.07–0.13 per newsletter, $5–9 a month, and an estimated $180–340 to backfill three years of history. The task is mostly copying (split a newsletter into items, copy title and URL, write one sentence, flag sponsors), so a much cheaper model may do as well. Cheaper models available on the account cost 25–50 times less per token (third-party price listings, October 2026):

| Model | Input / output per 1M tokens |
|---|---|
| `gpt-5.5` (now) | $5 / $30 |
| `gpt-5.4-mini` | $0.75 / $4.50 |
| `gpt-5.4-nano` | $0.20 / $1.25 |
| `gpt-5.6-luna` | $0.20 / $1.20 |

There is no way to tell whether quality holds without a benchmark, and new cheap models keep appearing, so the benchmark should be rerunnable.

## Decisions

### Real newsletters, stored in Langfuse, never in git

Plan 001 uses synthetic mail in a local database. Extraction is different: the real TLDR and Alpha Signal layouts, sponsor blocks, and tracking URLs are what is under test, and a generated newsletter would not reproduce them. The extraction call needs no database.

- Langfuse Cloud is the only lasting copy: the dataset `news-extraction-v1`. Each item's input is one newsletter (subject, RFC 2047-decoded; body; source; sent date), its expected output is the reviewed items with sponsor flags, and its metadata says how it was reviewed (`full` or `disputes`, see below). Runs read the dataset from Langfuse, so they work from any machine with the Langfuse keys and need nothing on disk.
- The newsletters contain per-recipient tracking and unsubscribe links, so they are never committed. Langfuse already receives the app's traces, so no new service sees this data.
- A one-off `evals.news_export` reads the stored `ai_newsletter` emails from the app database (read only) into the gitignored working folder `evals/data/news-v1/`. It is the one eval command that reads the app database, and it never writes. The folder only lives until the reviewed dataset is synced, then it is deleted.
- Because a synced dataset is frozen, the order is: export, reference and candidate runs on the local files, owner review, then sync.
- **Backup:** the sync also writes the full dataset as one JSON file (`news-extraction-v1.json`) to a private Supabase Storage bucket, `eval-datasets`, in the app's project. The newsletters could be re-exported from the app database, but the owner's review decisions exist nowhere else. This is the only eval write to the app's Supabase project: Storage only, no tables, once per dataset version.
- About 64 newsletters (40 TLDR, 24 Alpha Signal, September 2026).

### Reference answers: review where the models disagree (superseded, see below)

Stored `news_items` can't serve as the reference: sponsors were filtered out before storage, so sponsor flagging can't be scored from them. A GPT-5.5 run alone isn't a reference either, and hand-checking every item of 64 newsletters would take over three hours. Most items are easy and every model gets them the same, so the owner's time goes where answers differ.

1. **Runs first, on the local files.** A reference run with today's production setup (GPT-5.5, default effort) and one run per candidate, all on every newsletter, keeping sponsor flags and token usage. These runs are not Langfuse experiments yet, because the dataset isn't synced.
2. **Full check of 6 newsletters** (3 per source): the owner checks every item against the email. This catches mistakes all models share, which comparing models can't show.
3. **Dispute review across all 64**: a review file lists every item where any run disagrees with the reference (an item one run has and another lacks, a different URL, a different sponsor flag). The owner decides each one. Items every run flags as a sponsor are accepted without review (see below).
4. The reviewed answers become the expected output: the owner's decision on every disputed item, the full check where one was done, and the unanimous answer everywhere else. Each newsletter is marked `full` or `disputes`.

The owner's time is about 30–45 minutes, depending on how often the models disagree.

### Found during the runs (2026-10-06)

- **The text settles URL disputes.** Every TLDR URL a careful model returns appears verbatim in the newsletter text, so a URL is right when it is in the text. If no run's URL is in the text, the text has no link and an empty URL is right. Only two different URLs that both appear in the text go to the owner. This cut URL disputes between the cheap models from 123 to 11.
- **Alpha Signal items have no links, in production too.** All 156 Alpha Signal items stored in September have an empty URL, because the stored body has no per-article links. That's an ingest bug and is handled separately. For this benchmark an empty URL is the right answer for Alpha Signal, and a made-up URL is an error: `gpt-5.4-nano` invented 130.
- **Review size.** With five runs, 437 items needed a decision, well above the 30–45 minute estimate. Approved on 2026-10-06: outside the full checks, an item every run flags as a sponsor (78 of them) is accepted as a sponsor without review. A sponsor passed off as news still reaches the owner, as a differing sponsor flag. That left about 360 items, roughly 50–60 minutes.
- **Link rule, refined twice.** Front-page links first counted as no link at all, which also dropped real third-party links (a blog's front page, `blog/?p=10062`). Only the newsletters' own front pages (tldr.tech, alphasignal.ai) are unusable now. Matching by URL also uses article links only, after a replay of GPT-5.5 against itself showed items without links being paired by position. The frozen answer key still has no link for 3 TLDR items (n24, n39, n42) from the earlier rule; it costs every model the same, at most 0.4% of url_exact, so v1 stays.
- **GPT-5.5 invents links too.** Against its own answer key it has 2 invented URLs: GitHub links for an Alpha Signal edition that contains no links. So the zero-invented-URL bar is stricter than today's production.
- **Recurring blocks.** Job ads, "Advertise", and banners repeat in every TLDR edition and some models list them. The review offers the same decision for every undecided item with the same title (digits and punctuation ignored).

### Change: GPT-5.5 as the answer key

After about 25 of 358 decisions, the owner chose not to hand-label news-v1. The answer key is now the GPT-5.5 default-effort run (`evals.news_review reference`), with the link rule applied: a URL is kept only when it is a usable article link in the text, otherwise the expected URL is empty. Every newsletter is marked `reference`.

What this changes:

- Scores measure **agreement with GPT-5.5**, not correctness. A candidate that fixes one of GPT-5.5's mistakes is marked down for it, and mistakes all models share stay invisible.
- GPT-5.5 at default effort scores 100% by definition, so it is the baseline, not a candidate. GPT-5.5 at low effort is still a meaningful comparison.
- The question the benchmark answers becomes "can a cheaper model replace today's production extraction without changing what gets stored?", which is the practical decision here.

**In a real project we would hand-label part of the data.** Agreement with a stronger model is a reasonable first filter, but the decision to switch models should rest on human-checked answers: at least a few fully checked newsletters per source to catch mistakes all models share, and the items where models disagree, since that is where a cheaper model's errors show up. The review page (`evals.news_review serve`, then `build`) does exactly that and stays in the code for later versions. The owner's partial decisions are kept in the gitignored `evals/out/news-review/news-v1/decisions.json`.

### Production change: a separate extraction model setting

- New settings `news_extraction_model` (defaults to `openai_chat_model`, so nothing changes until it's set) and `news_extraction_reasoning_effort` (unset means the API default).
- `extract_with_model` takes the model and effort as arguments, so the benchmark calls the production prompt and schema, not a copy.

### Metrics, per newsletter and averaged

Items are matched to the reviewed answers by normalized URL, falling back to title similarity.

- **Item recall and precision** (non-sponsor items).
- **URL exact match** among matched items; a wrong URL is a broken citation link.
- **Invented URLs**: non-empty URLs that don't appear in the newsletter text. These become broken links.
- **Sponsor leaks**: reference sponsors returned as news. **Sponsor drops**: news items flagged as sponsors.
- **Order**: share of matched item pairs in the same order.
- **Cost** from the returned token usage (reasoning tokens included) and a dated price table in `evals/prices.py`, plus **latency**.

Blurbs are free text and not scored in v1; a judge can come later if the numbers are close.

### Candidates and the pass bar

Candidates: `gpt-5.5` at low effort, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.6-luna`, each at its lowest supported reasoning effort. A candidate may replace GPT-5.5 when, over all 64 newsletters and measured against the GPT-5.5 answer key, recall is at least 0.97, URL exact match at least 0.98, and sponsor leaks and invented URLs are zero; the cheapest passing model wins. (Before the change to GPT-5.5 as the answer key, the bar was against reviewed answers, and GPT-5.5 itself would have been scored too.)

After sync, the official comparison runs as one Langfuse experiment per model. Cheap models are called again (cents). The GPT-5.5 reference is scored from its saved outputs instead of a second $5–8 run, and its run metadata says so.

Downstream story matching (do the 13 big stories survive) is left for after the story-matching speedup, because today it would take thousands of Jev calls per run.

## Tasks

- [x] 003/01 — `news_extraction_model` and `news_extraction_reasoning_effort` settings; `extract_with_model` takes model and effort; unit tests. No behavior change.
- [x] 003/02 — `evals.news_export` to the gitignored working folder `evals/data/news-v1/`.
- [x] 003/03 — Reference run and candidate runs on the local files, keeping outputs and token usage.
- [x] 003/04 — ~~Review file: full check of 6 newsletters, plus every disputed item across all 64; the owner's decisions become the expected output.~~ Changed: the GPT-5.5 reference run is the answer key (`evals.news_review reference`). The review page is built and kept for later hand labelling.
- [x] 003/05 — Sync newsletters, expected items, and review marks to the Langfuse dataset `news-extraction-v1`; write the backup JSON to the private `eval-datasets` bucket; delete the working folder.
- [x] 003/06 — `evals.run --mode extraction --model M [--effort E]` with the metrics above, a Langfuse experiment per model, and a local report; items are read from Langfuse.
- [ ] 003/07 — Official runs, compare, and set `news_extraction_model` if one passes.

## Cost

Estimated: reference run about $5–8, the four candidates together under $1 per full pass.

Actual local runs on 2026-10-06 (64 newsletters each): GPT-5.5 default $3.44 (20,788 reasoning tokens), GPT-5.5 low $2.86 (620 reasoning tokens), `gpt-5.4-mini` $0.42, `gpt-5.4-nano` $0.12, `gpt-5.6-luna` $0.11. GPT-5.5 extraction costs about $0.054 per newsletter, under $4 a month, lower than the problem section's estimate. The official runs call the cheap models again for cents; the reference is scored from its saved outputs.

## Risks

- **Reference bias**: with GPT-5.5 as the answer key, its mistakes count as right and a candidate that fixes them is marked down. Hand-label a sample before relying on a close result (see the change above).
- **Many disputes**: hand review grew to 437 items with five runs. A later hand-labelled version should review fewer runs at once or label a fixed sample of newsletters fully.
- **Reasoning effort support** differs by model; the run records the effort actually sent and fails clearly if a model rejects it.
- **Price drift**: prices live in one dated table; reports store token counts, so cost can be recomputed.
- **One month of data**: newsletter layouts change; a later export becomes `news-v2` and v1 stays as the baseline.
