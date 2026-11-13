# 001/01 — Friend caller

## Goal
The owner and demo visitors can take a voice call from the friend persona in the browser.

## Scope
- Backend `app/phone/` (personas, friend prompt, session secret, hourly limit) and `POST /phone/session`, `GET /phone/personas`.
- `phone` in `/me` for the owner and the demo user.
- Frontend `/phone`: persona list, ringing screen, call screen with transcript, mute, hang up and time cap.
- Privacy page entry.

## Acceptance criteria
- Given a user who is neither the owner nor the demo user, when they ask for a session, then they get 403 and `/me` has no `phone`. (test)
- Given the demo user, when they ask for a Friend session, then OpenAI is asked for a secret with the friend instructions and voice, and the reply has the secret and `maxSeconds`. (test)
- Given an unavailable or unknown persona, when a session is asked for, then 404. (test)
- Given a user at the hourly limit, when they ask again, then 429. (test)
- Given the demo user on `/phone`, when they pick Friend and answer, then the friend speaks first and the transcript shows both sides. (manual: needs a mic and speakers)
- Given a call, when the cap is reached, then it hangs up by itself. (browser, with a short cap)
- Given the picker, when signed in as the demo user, then a Phone card shows and Doctor and Interviewer show as coming soon. (browser)

## Dependencies
None.

## Notes
- Implementation plan: [01-friend-caller.plan.md](01-friend-caller.plan.md).

## Verified

2026-11-13, branch `feat/phone-agent`.

- Other users → 403 and no `phone` in `/me`: `test_other_users_get_no_phone_and_403`. Pass.
- Demo user → Friend secret with the friend prompt and voice, reply has secret and `maxSeconds`: `test_demo_user_gets_a_friend_secret`, `test_friend_session_has_its_prompt_voice_and_transcription`. Pass.
- Unavailable or unknown persona → 404: `test_unavailable_or_unknown_persona_is_404`. Pass.
- Over the hourly limit → 429: `test_calls_over_the_hourly_limit_are_429`, `test_limiter_refuses_once_the_hour_is_full_and_frees_up_after`. Pass.
- Picker as the demo user: Phone card shows (2×2 grid); `/phone` lists Friend, and Doctor and AI-job Interviewer as "Coming soon". Pass.
- Time cap: with `PHONE_CALL_MAX_SECONDS=25`, a Friend call connected to OpenAI Realtime, showed "0:03 · 22s left", and ended by itself with "Time is up for this call." Pass.
- Friend speaks first, transcript shows both sides: the browser pane blocks microphones, so a silent synthetic mic track stood in. Sam opened with "Hey! It's Sam. Got a minute? I was just thinking about you. How have you been?" and it showed in the transcript. Mic denied showed "Microphone access was blocked…". **Your side of the conversation is not yet checked with a real mic and speakers (manual, owner).**
