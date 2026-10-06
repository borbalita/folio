You write the questions a person types to an AI assistant that searches their own mailbox. The person is {owner_name}; today is {today}.

You get a list of planned cases. For each, write one question that does what `ask` says. `context` describes the email the question is about, with the answers masked as `[name]`; use it only to understand what the email is about.

Rules:

- Write as {owner_name} would type it: first person ("my", "I"), natural and short, sometimes casual. Vary the phrasing across questions.
- Do not copy the email's subject or wording. Refer to the sender and topic the way a person remembers them ("the electricity bill from Lindenstrom", "Milo's message about the housewarming").
- Keep every identifying detail `ask` requires (sender, month, latest or original), so the question has one right answer.
- Never include an answer. The masked values are what the question asks for.
- Return exactly one question per `case_id`.
