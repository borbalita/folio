# 001 — Phone agent: a friend calls you

- Created: 2026-11-13
- Status: Complete
- Current stage: 001/01 done

## Approval state

- 2026-11-13: in chat, the owner asked for a phone agent: pick a persona (doctor, AI-job interviewer, friend) and talk to it like a phone call. They chose: voice in the browser (not a real phone number, not text); the owner and demo visitors can call; nothing is stored after hang-up. Approach A (browser talks to OpenAI Realtime over WebRTC with a short-lived key from the backend) chosen over a backend audio relay and over speech-to-text → LLM → text-to-speech. Design approved; the owner asked to build it as one PR.

## Problem

The portfolio shows chat agents only. The owner wants a voice agent that feels like a phone call with someone, starting with a friend ringing you for a catch-up, and later a doctor and an interviewer for AI jobs.

## Current system

- **Agents:** the picker ([AgentPickerPage.tsx](../../../../frontend/src/pages/picker/AgentPickerPage.tsx)) shows the agents `/me` lists ([email_access.py](../../../../backend/app/auth/email_access.py) `agents_for`). Finance is shown to the owner and the demo user (`is_finance_user`).
- **LLM:** OpenAI only, key in `settings.openai_api_key`. No audio anywhere.

## Goals and non-goals

Goals:

- A "Phone" picker card for the owner and the demo user, opening `/phone`.
- A persona list: Friend works; Doctor and AI-job Interviewer are shown as "coming soon".
- The friend rings you; you answer and talk out loud; the friend talks back in real time; a live transcript shows on screen.
- Calls end at a time cap; a user can start only a few calls per hour.

Non-goals: real phone numbers; saved transcripts or call history; the doctor and interviewer prompts (later tasks); memory of past calls.

## Decisions

- **Voice in the browser over WebRTC to OpenAI Realtime.** Rejected: a telephony provider (number, cost, more privacy surface); a backend audio relay over WebSocket (more delay and code); chained STT → LLM → TTS (pauses between turns).
- **The backend mints a short-lived client secret** with the persona's instructions and voice baked in, so the API key and prompts stay on the server.
- **Nothing stored.** Audio goes from the browser to OpenAI; the transcript lives only in the page.
- **Owner and demo user only,** the same rule as Finance, because Realtime audio is billed per minute.
- **Cost limits:** `phone_call_max_seconds` (default 300) is enforced by the page hanging up; `phone_calls_per_hour` (default 10) is enforced by the backend refusing new secrets, counted in memory per process.

## Design

```text
/phone  persona picker ──► ringing screen ──Answer──► POST /phone/session {persona}
                                                        │  access + hourly limit
                                                        ▼
                                  OpenAI client_secrets.create(instructions, voice, model)
                                                        │  {secret, expiresAt, maxSeconds}
browser: getUserMedia ─► RTCPeerConnection ─SDP─► api.openai.com/v1/realtime/calls (Bearer secret)
         audio in/out + data channel "oai-events" (transcript events, response.create)
```

- **Backend** `app/phone/`: `personas.py` (id, name, voice, available, prompt file), `friend.md`, `session.py` (build session config, call OpenAI, hourly limit). Route `POST /phone/session` in `app/api/phone.py`: 403 for users other than the owner and demo user, 404 for an unknown or unavailable persona, 429 over the hourly limit. `GET /phone/personas` lists personas for the picker.
- **Session config:** model `openai_realtime_model` (default `gpt-realtime-mini`), the persona voice, instructions, input transcription on (`gpt-4o-mini-transcribe`) so the user's words show in the transcript, server voice activity detection.
- **Frontend** `pages/phone/`: `PhonePage` (persona list), `CallScreen` (ringing → connecting → in call → ended), `useRealtimeCall` (native WebRTC; sends `response.create` on connect so the friend speaks first; hangs up at `maxSeconds`). Mute and hang up buttons. No new dependency.
- **Failure modes:** mic permission denied → a clear message and back to the list; OpenAI or limit error → the API error text; connection drops → the call ends.
- **Privacy:** the privacy page says voice and transcripts go to OpenAI during a call and nothing is stored.

## Success criteria

1. The owner and the demo user see a Phone card; other users do not and get 403.
2. Picking Friend rings; answering connects and the friend speaks first; both sides show in the transcript.
3. The call hangs up by itself at the cap; the eleventh call in an hour is refused.
4. Doctor and Interviewer show as coming soon and cannot be called.

## Tasks

- [x] [01 — Friend caller](tasks/01-friend-caller.md)
