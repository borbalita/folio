# 001/02 — Doctor and interviewer

## Goal
The Doctor and AI-job Interviewer personas can be called like the friend.

## Scope
- Prompts `doctor.md` (Dr. Lee, GP check-in) and `interviewer.md` (Alex, AI Engineer screening); both personas available.
- An optional per-persona cap; the interviewer gets 600 seconds.
- Picker description names all three; privacy page asks not to share real health details.

## Acceptance criteria
- Given the persona list, when read, then all three can be called. (test)
- Given each persona, when a session is asked for, then it carries that persona's prompt and its own voice. (test)
- Given the doctor prompt, when read, then it forbids diagnosing and prescribing and names 112. (test)
- Given an interviewer session, when created, then `maxSeconds` is 600; the friend keeps the default. (test)
- Given the demo user on `/phone`, when they call the Doctor and the Interviewer, then each opens in character. (browser)

## Dependencies
001/01.

## Notes
- Implementation plan: none; a small follow-on to 001/01's plan.

## Verified

2026-11-13, branch `feat/phone-personas`.

- All three callable: `test_every_persona_can_be_called`, `test_personas_list_has_all_three`. Pass.
- Own prompt and voice per persona: `test_each_session_has_its_own_prompt_voice_and_transcription` (3 cases), `test_voices_differ_between_personas`. Pass.
- Doctor safety rules: `test_doctor_prompt_keeps_the_safety_rules`. Pass.
- Interviewer cap 600 s, friend default: `test_interviewer_gets_a_longer_call_than_the_default`, `test_interviewer_session_has_the_longer_cap`. Pass.
- Browser, demo user, silent stand-in mic (the pane blocks microphones): Doctor opened with "Hello, this is Dr. Lee from the practice. I'm just calling for a quick check-in on how you've been. Is now a good time?"; Interviewer opened with "Hi, this is Alex from Lumen Labs. I'm calling for the AI Engineer role interview…" and laid out the plan. Pass.
