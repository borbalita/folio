# 001/12 — Finance chat with cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The owner asks Finance about invoices and prepares payments in chat. Answers carry invoice and payment cards drawn from current data, and nothing can be approved by the model.

**Architecture:**
- **Agent:** a PydanticAI Finance agent, a sibling of the email agent, with five tools: list invoices, get one invoice, search transactions, list accounts, and prepare payments (drafts only).
- **Cards:** the agent's output is the answer text plus cards: `{kind: "invoices" | "payments", ids}`. Every id must have come from a tool result in this turn. Unknown ids are dropped and logged, and a card left with no ids is dropped.
- **Orchestrator:** it gets a `_FinanceChatAgent`. The citation path is generalised to "data parts", so citations stay `data-citation` and cards become `data-finance-card`. Both are streamed and stored the same way.
- **Frontend:**
  - Finance gets a Chat section: a thread list, then a thread view reusing `ChatThreadView`.
  - `MessageList` renders `data-finance-card` parts. An invoices card loads the current invoices by id and renders them with 06's `InvoiceList`. A payments card loads the drafts and renders 10's `PaymentCard`, which has the tick and Approve.

**Tech Stack:** PydanticAI (existing), FastAPI, SQLAlchemy, React + TS with the AI SDK (existing). No new dependencies.

**Spec:** [../README.md](../README.md) (Decisions: "The Finance chat answers with cards…"), task [12-finance-chat.md](12-finance-chat.md).

## Global Constraints

- **No approving from chat:** the agent has no tool that approves, marks paid, or edits. Approval happens only through the existing `POST /finance/payment-drafts/{id}/approve`, from the card.
- **Payments name no account** (owner's decision, 2026-10-16, PR #35). The task's "pay them all from N26" becomes "pay them all", and the spec's success criterion 5 changes to match (owner agreed, 2026-10-16). `list_accounts` stays, for questions about connected banks and their expiry.
- **Instructions:**
  - Dates in Europe/Berlin (`settings.email_timezone`).
  - Amounts only from tool results.
  - For "pay" requests, call `prepare_payments` and say the payments await the owner's approval on the cards.
  - Never claim something was paid or approved.
- **Card grounding:** ids are checked against `deps.seen_invoice_ids` and `deps.seen_draft_ids`, filled by the tools. A dropped id is logged as `finance_card_id_dropped` with the kind and a count, not the ids' content.
- **Data part shape:** `{"type": "data-finance-card", "data": {"kind": "invoices" | "payments", "ids": [str, ...]}}`. It is stored in the message's `parts`, like citations.
- **Tracing:** the existing content-free export applies (eval plan 004). The finance turn is tagged `["chat", "finance"]` like the other agents.
- **Status label while tools run:** `Looking at your finances`.

## Review Focus

1. **The model copies an invoice id from earlier in the thread, or invents one.** It's not in this turn's seen ids, so it is dropped and logged. (Task 2 test: acceptance criterion.)
2. **"Pay them all" when some invoices are `needs_info` or already paid.** `create_drafts` skips them; the tool result says which were skipped and why, so the answer can say so; payment cards show only the drafts. (Task 1 test.)
3. **Reopening an old thread after an invoice was paid.** The card fetches current data, so it shows paid. (Task 4: browser.)
4. **A card whose invoice or draft no longer exists, or belongs to another mailbox.** The card shows "No longer available" instead of breaking the message. (Task 4.)
5. **The model returns text with no cards for a "what's open" question.** That's allowed (no grounding error); the test fixes the expected behaviour only for the tool-driven path. (Task 2 test.)

---

### Task 1: Finance agent and tools

**Files:** `backend/app/finance_assistant/{__init__,agent,deps,outputs,tools}.py`, `backend/app/finance_assistant/instructions.md`, `backend/app/database/transactions.py` (`search_transactions`), `backend/tests/finance_assistant/test_tools.py`

**Interfaces (produces):**
- `FinanceAgentDeps(user_id, thread_id, mailbox_ids, seen_invoice_ids: set[UUID], seen_draft_ids: set[UUID], status_queue)`.
- `FinanceCard(kind: Literal["invoices", "payments"], ids: list[UUID])`.
- `FinanceAnswer(answer: str, cards: list[FinanceCard] = [])`.
- `FinanceTurnResult(answer, usage)`.
- Tools (all `async`, DB through `asyncio.to_thread`), each returning compact text:
  - `list_invoices(status: Literal["open", "needs_info", "paid"] | None = None)`: one line per invoice with id, payee, amount, currency, due date, status and reference. Records ids.
  - `get_invoice(invoice_id)`: the fields plus match state. Records the id.
  - `search_transactions(text: str | None, since: date | None, until: date | None, limit: int = 20)`: date, bank, counterparty, amount and remittance.
  - `list_accounts()`: bank, connected, status, and valid until.
  - `prepare_payments(invoice_ids)`: `payments.create_drafts`. Lists the draft ids and the skipped invoices with their reasons. Records draft ids.
- `run_finance_agent(prompt, deps) -> FinanceTurnResult`. The prompt is prefixed with today's date in Europe/Berlin, like `email_prompt`.

- [ ] Write failing tests:
  - `test_list_invoices_filters_open_and_records_ids`
  - `test_prepare_payments_records_drafts_and_reports_skipped` (Review Focus 2)
  - `test_no_tool_can_approve`: the agent's tool names are exactly the five above.
  - `test_search_transactions_scoped_to_user`
- [ ] Run them and see them fail. Implement. Run them and see them pass. Commit: `feat(finance): finance agent and tools (001/12)`.

### Task 2: Orchestrator: finance turns with cards

**Files:** `backend/app/chat/orchestrator.py`, `backend/app/chat/streaming.py`, `backend/app/chat/messages.py`, `backend/app/finance/__init__.py` (remove `STUB_REPLY`), `backend/tests/chat/test_orchestrator_dispatch.py`, `backend/tests/chat/test_finance_turn.py`

**Interfaces:**
- `_ChatAgent.data_parts(result, deps) -> list[dict]` replaces `citation_payloads` at the stream and storage call sites.
- `iter_grounded_stream(text, parts)` yields each part as given.
- `assistant_message_for_storage(text, usage=, parts=)`.
- Document and email agents keep their exact wire output: their `data-citation` parts are unchanged.
- `_FinanceChatAgent`:
  - Its grounder accepts any answer.
  - Its `data_parts` filters the card ids.
  - It saves no citation rows.

- [ ] Write failing tests:
  - `test_open_invoices_answer_shows_an_invoice_card` (acceptance criterion): with a fake agent run whose tool fills the seen ids, the stream and the stored message carry an invoices `data-finance-card` with those ids.
  - `test_pay_them_all_creates_drafts_and_payment_cards_none_approved` (acceptance criterion): the real `prepare_payments` tool runs against a patched `create_drafts`; the stored message has a payments card; approve is never called.
  - `test_unknown_card_id_is_dropped_and_logged` (acceptance criterion).
  - The existing dispatch tests are kept; the stub test becomes `test_finance_thread_uses_finance_agent`.
  - Existing citation streaming and storage tests stay green.
- [ ] Run them and see them fail. Implement. Run them and see them pass, then run the full suite. Commit: `feat(chat): finance turns stream and store cards (001/12)`.

### Task 3: Spec and task wording

**Files:** `docs/05-finance/plans/001-finance-agent/README.md` (success criterion 5), `tasks/12-finance-chat.md` (criterion 2).

- [ ] Change "pay them all from N26" to "pay them all" in both places, citing the 2026-10-16 decision. Commit with Task 2, or on its own.

### Task 4: Frontend: Finance chat and cards

**Files:** `frontend/src/App.tsx` (routes `/finance/chat` and `/finance/chat/:threadId`), `frontend/src/pages/finance/FinanceLayout.tsx` (a Chat section), `frontend/src/pages/finance/FinanceChatPage.tsx` (new: thread list and new chat, outlet context compatible with `ChatThreadPage`), `frontend/src/lib/agents.ts` (`finance.path` for chat links), `frontend/src/lib/chat-messages.ts` (`FinanceCardData` and keeping `data-finance-card` parts), `frontend/src/components/chat/MessageList.tsx` (renders cards), `frontend/src/components/finance/FinanceChatCard.tsx` (new)

- **Invoices card:** fetch `api.listInvoices()` once per card and keep the ids it lists. Render with `InvoiceList`, with selection and `PayInvoices`, as on the Invoices page. Missing ids: "N invoices are no longer available".
- **Payments card:** `api.getPaymentDrafts(ids)`, rendering `PaymentCard` for each. A fetch error shows "These payments are no longer available".
- **Assistant messages with cards:** render even when the text is empty.
- [ ] `pnpm tsc --noEmit` and `pnpm lint` are clean. Commit: `feat(finance): chat with invoice and payment cards (001/12)`.

### Verification (main session)

- **Browser:** ask "What do I still need to pay?", then "Pay them all". Tick and Approve one payment card: the QR shows. Reopen an old thread after marking an invoice paid on the Invoices page: the card shows it as paid.
