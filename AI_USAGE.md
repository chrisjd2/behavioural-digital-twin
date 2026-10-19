# AI usage log

Salesforce allows and encourages AI use, provided it is disclosed honestly. Each work session adds one entry. Commits co-authored by the coding agent carry a `Co-Authored-By` trailer, which can be checked in git history.

| Date | What AI did | What I decided | What I verified by hand | Surprise / what broke |
|---|---|---|---|---|
| 2026-10-19 | Helped draft `brief.md`. Ran a "grill me" design interview (Claude Code). Raised issues: the popularity baseline leaked future clicks, there was no personalisation-vs-realism control, position and tie bias, the repo is public, and N=60 was underpowered. Summarised `kleisi-ops-server` conventions. Drafted `CONTEXT.md`, ADR-0001 to ADR-0010 and PRD-01 to PRD-03. | Research question and arms. **Primary metric D − A paired AUC** and the decision rule. N=200 with a dev set of 30. Gemini over OpenAI, with no fine-tuning. Added the wrong-twin control. Time-respecting popularity using MIND train. Feed framing. Hook design (guess, then toggle history, then guess again). Outcome buckets. Interview kept as a Q&A bonus. Public repo with no data committed. Lightweight workflow. | *(to fill in: review of the ADRs and PRDs)* | *(to fill in)* |
