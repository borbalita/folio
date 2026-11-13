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
