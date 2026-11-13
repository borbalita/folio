# 001/01 — Friend caller: implementation plan

1. **Tests first** (`tests/phone/test_session.py`, `tests/api/test_phone.py`): access (403, `/me`), friend session config sent to a fake OpenAI client, 404 for unavailable/unknown persona, 429 at the limit.
2. **Config:** `openai_realtime_model`, `openai_realtime_transcribe_model`, `phone_call_max_seconds`, `phone_calls_per_hour`.
3. **`app/phone/personas.py` + `friend.md`:** a frozen dataclass per persona; Doctor and Interviewer `available=False`.
4. **`app/phone/session.py`:** `session_config(persona)`, `CallLimiter` (timestamps per user, sliding hour), `create_call_secret(persona)` via `AsyncOpenAI.realtime.client_secrets.create`.
5. **`app/api/phone.py`:** routes; `require_phone_access` in `app/auth/phone_access.py`; `agents_for` adds `phone`; router in `main.py`.
6. **Frontend:** `AgentName` gets `phone`; `AGENTS.phone` (icon `Phone`, `hasThreads: false`); picker order; `/phone` route behind `AgentRoute`; `api.phonePersonas` / `api.createPhoneSession`; `useRealtimeCall`; `PhonePage`; `CallScreen`.
7. **Privacy page** entry and date.
8. `uv run pytest -m "not integration"`, `pnpm exec tsc -b --noEmit`, `pnpm lint`, browser check, PR.
