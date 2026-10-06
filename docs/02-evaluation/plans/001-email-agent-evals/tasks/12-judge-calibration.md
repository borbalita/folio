# 001/12 — Judge calibration

**Goal**: Measure how well the judge agrees with human grading, per candidate model.

**Why**: Judge scores are only trusted after calibration.

**Scope**
- Push about 30 answer outputs (mixed Luna and Sol) to a Langfuse annotation queue with human score configs for support and facts.
- If real failures are scarce, add a few corrupted copies of good answers (a changed amount or date, a citation swapped to the wrong email), so the judge is tested on failures too, not only passes.
- Script that reads human grades and judge verdicts and reports agreement, the judge-passed-human-failed rate, and disagreements, overall and per model.
- Record the outcome and any rubric changes in the eval README.

**Out of scope**: automatic rubric tuning.

**Likely areas affected**: `backend/evals/calibrate.py`.

**Acceptance criteria**: After hand grading, the script prints agreement per model and lists every disagreement.

**Test strategy**: Unit test agreement arithmetic; manual grading session.

**Dependencies**: 001/11.

**Review notes**: Keep some graded outputs aside when changing the rubric, to check agreement on unseen examples.

**Complexity**: Small.
