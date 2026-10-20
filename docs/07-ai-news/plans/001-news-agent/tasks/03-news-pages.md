# 001/03 — News pages and picker card

## Goal
The owner opens AI News from the picker and chats in their own news threads.

## Scope
- Picker card "AI News": "Big AI stories and briefings from your newsletters, with citations".
- `/news` routes reusing the Email chat layout and news citations; empty state with "What were the big stories this week?" and "Catch me up since Monday".

## Acceptance criteria
- Given the owner, when the picker opens, then the AI News card shows and opens `/news`. (browser)
- Given "What were the big stories this week?", when answered, then only big stories show, ranked, each with its coverage line, and citations open the articles. (browser)
- Given "Catch me up since Monday", when answered, then big stories come first, then other stories grouped by theme, all from that period. (browser)

## Dependencies
001/02.
