# 001/11 — LLM judge: implementation plan

Task: [11-judge.md](11-judge.md).

## Approach

- `evals/judge.py`: two PydanticAI agents on `AnthropicModel("claude-sonnet-5-5")`, one per rubric, with `NativeOutput` (JSON schema output). Sonnet 5.5 rejects forced tool use, so output tools aren't an option.
- Schemas put `reason` before `verdict`: `ClaimVerdict` (`supported` / `not_supported`) and `FactVerdict` (`correct` / `wrong` / `missing`).
- `faithfulness` = supported / claims, for any answer that isn't a refusal (an unanswerable case answered from a look-alike is still judged). `fact_recall` = correct / expected facts, for answerable cases that were answered. None when there's nothing to judge, including an answer with no claims.
- Errors: each call's exception, or a facts list that doesn't match the expected facts, is kept as text; the score stays None and Langfuse gets a `judge_error` score.
- Prompts: question, answer, cited passages (full text with sender, subject, date), and expected facts in tags; `<`, `&`, and `"` escaped so data can't close a tag.
- Wiring: `AnswerResult` and `E2EResult` get `judge: JudgeScores | None`; the answer mode's summary, Langfuse scores, and print line add the two metrics; rubric texts join the run's prompts, so their hashes are in the metadata.
- Config: optional `anthropic_api_key`; `judge_model()` fails fast without it. `--no-judge` keeps code-check-only runs possible.

## Tests (first)

- Score arithmetic, refusal and no-facts not-applicable, no claims → None, a failed call and a short facts list → error with no score, prompt delimiting and escaping, reason before verdict in both schemas, Langfuse comments and `judge_error`. The judge runs on PydanticAI's `FunctionModel`.

## Verification

- `uv run pytest -m "not integration"`.
- Paid run: answer test on v2 for Luna with the judge; read the verdicts on a handful of cases; check Langfuse shows `faithfulness` and `fact_recall` with per-claim and per-fact reasons.
