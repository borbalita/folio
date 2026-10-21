# 001/04 — News moves out of the Email agent: implementation plan

Task: [04-email-without-news.md](04-email-without-news.md). Spec: [README](../README.md), Design → Email agent.

- **Agent:** `email_assistant/agent.py` registers only `search_emails`; `tools/news.py` and its tests go (the News agent has its own tools and tests).
- **Deps:** `EmailAgentDeps` loses `news`; `seen_passages` holds `EmailPassage` only. The orchestrator's Email turn drops the `NewsPassage` branches; old threads' news citations render from stored rows and stay as they are.
- **Instructions:** a question about AI news from the newsletters gets one line saying the AI News assistant answers those, with `insufficient_evidence` true and no citations (the grounder accepts that without citations), and no tool call. Other mentions of news and stories go.
- **Picker:** Email's description "Search your mail, with citations to each message."; empty hint and placeholder without news.
- **Evals:** `evals/modes/answer.py` and `e2e.py` build `EmailAgentDeps` without a news retriever; their tests likewise.

Tests (red first): `test_email_agent.py` — the agent's tools are exactly `{"search_emails"}`; the instructions name the AI News assistant and `insufficient_evidence` for news questions and no longer mention `list_big_news` or `search_news`. The eval tests fail until the modes stop passing `news`.

Browser: an old Email thread with news citations still shows them; a news question in Email gets the pointer.
