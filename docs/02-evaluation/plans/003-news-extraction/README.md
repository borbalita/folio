# 003 — Newsletter extraction benchmark and a cheaper extraction model

- Created: 2026-10-06
- Status: In progress
- Current stage: Implementation, 003/02.

## Approval state

Approved on 2026-10-06: real newsletters stored only in Langfuse with a private Supabase Storage backup, review where the models disagree plus a full check of 6 newsletters, the pass bar over all 64, and a separate extraction model setting that leaves production unchanged until a model passes.

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

### Reference answers: review where the models disagree

Stored `news_items` can't serve as the reference: sponsors were filtered out before storage, so sponsor flagging can't be scored from them. A GPT-5.5 run alone isn't a reference either, and hand-checking every item of 64 newsletters would take over three hours. Most items are easy and every model gets them the same, so the owner's time goes where answers differ.

1. **Runs first, on the local files.** A reference run with today's production setup (GPT-5.5, default effort) and one run per candidate, all on every newsletter, keeping sponsor flags and token usage. These runs are not Langfuse experiments yet, because the dataset isn't synced.
2. **Full check of 6 newsletters** (3 per source): the owner checks every item against the email. This catches mistakes all models share, which comparing models can't show.
3. **Dispute review across all 64**: a review file lists every item where any run disagrees with the reference (an item one run has and another lacks, a different URL, a different sponsor flag), and every item any run flagged as a sponsor. The owner decides each one.
4. The reviewed answers become the expected output: the owner's decision on every disputed item, the full check where one was done, and the unanimous answer everywhere else. Each newsletter is marked `full` or `disputes`.

The owner's time is about 30–45 minutes, depending on how often the models disagree.

### Production change: a separate extraction model setting

- New settings `news_extraction_model` (defaults to `openai_chat_model`, so nothing changes until it's set) and `news_extraction_reasoning_effort` (unset means the API default).
- `extract_with_model` takes the model and effort as arguments, so the benchmark calls the production prompt and schema, not a copy.

### Metrics, per newsletter and averaged

Items are matched to the reviewed answers by normalized URL, falling back to title similarity.

- **Item recall and precision** (non-sponsor items).
- **URL exact match** among matched items; a wrong URL is a broken citation link.
- **Sponsor leaks**: reference sponsors returned as news. **Sponsor drops**: news items flagged as sponsors.
- **Order**: share of matched item pairs in the same order.
- **Cost** from the returned token usage (reasoning tokens included) and a dated price table in `evals/prices.py`, plus **latency**.

Blurbs are free text and not scored in v1; a judge can come later if the numbers are close.

### Candidates and the pass bar

Candidates: `gpt-5.5` at low effort, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.6-luna`, each at its lowest supported reasoning effort. A candidate may replace GPT-5.5 when, over all 64 reviewed newsletters, recall is at least 0.97, URL exact match at least 0.98, and sponsor leaks are zero; the cheapest passing model wins. The reference run is scored against the same reviewed answers, since GPT-5.5 may not meet the bar either.

After sync, the official comparison runs as one Langfuse experiment per model. Cheap models are called again (cents). The GPT-5.5 reference is scored from its saved outputs instead of a second $5–8 run, and its run metadata says so.

Downstream story matching (do the 13 big stories survive) is left for after the story-matching speedup, because today it would take thousands of Jev calls per run.

## Tasks

- [x] 003/01 — `news_extraction_model` and `news_extraction_reasoning_effort` settings; `extract_with_model` takes model and effort; unit tests. No behavior change.
- [ ] 003/02 — `evals.news_export` to the gitignored working folder `evals/data/news-v1/`.
- [ ] 003/03 — Reference run and candidate runs on the local files, keeping outputs and token usage.
- [ ] 003/04 — Review file: full check of 6 newsletters, plus every disputed item and every sponsor flag across all 64; the owner's decisions become the expected output.
- [ ] 003/05 — Sync newsletters, reviewed items, and review marks to the Langfuse dataset `news-extraction-v1`; write the backup JSON to the private `eval-datasets` bucket; delete the working folder.
- [ ] 003/06 — `evals.run --mode extraction --model M [--effort E]` with the metrics above, a Langfuse experiment per model, and a local report; items are read from Langfuse.
- [ ] 003/07 — Official runs, compare, and set `news_extraction_model` if one passes.

## Cost

Reference run about $5–8, once; the four candidates together under $1 per full pass, run twice (before review and as official experiments). Each later rerun of one cheap model costs cents.

## Risks

- **Shared mistakes**: an error every model makes never shows up as a dispute. The 6 fully checked newsletters estimate how often that happens; if it's more than rare, check more newsletters fully.
- **Many disputes**: if a weak model disagrees on most items, the review grows. Drop that model from the review and score it afterwards.
- **Reasoning effort support** differs by model; the run records the effort actually sent and fails clearly if a model rejects it.
- **Price drift**: prices live in one dated table; reports store token counts, so cost can be recomputed.
- **One month of data**: newsletter layouts change; a later export becomes `news-v2` and v1 stays as the baseline.
