# AI use and my contribution

I used AI while building and reviewing this project. I am responsible for the project I submit, and I want to be clear about which parts I directed and which parts AI helped implement.

## My contribution

I chose to build a practical clickstream sessionization project and set the direction: it should run locally on Windows, handle messy and late-arriving event data, be testable, and be clear enough for me to learn and explain. I asked for a detailed plan, edge-case coverage, setup instructions, and documentation of the design choices. I also directed this final review and asked that local changes stay uncommitted until I decide to commit them.

AI generated much of the implementation and test code. I do not claim that I independently wrote all of it. My responsibility is to review the result, understand the core behavior, check that it works, and be ready to explain the decisions and limitations. I am still working through that personal review; the assistant-run checks below are not a substitute for it.

## AI tools used

- **Claude (Anthropic), through claude.ai:** planning, code and test drafts, documentation drafts, and explanations during the initial build.
- **OpenAI Codex in the IDE:** submission review, sample and large-data verification, and a per-session reconciliation check with a regression test.

The available prompts are recorded in [`prompts/prompt_log.md`](../prompts/prompt_log.md). Some earlier Claude prompts could not be recovered; this limitation is disclosed in that file. AI responses are omitted.

## Where AI helped most

Claude generated much of the pipeline, tests, sample data generator, SQL, and first drafts of the documentation. I relied on it heavily for implementation. Codex reviewed the finished project and identified that reconciliation did not compare each session's recorded event count with the events in that session's time range.

## Checks performed by the coding assistant

These are assistant-run checks, not claims that I personally ran or independently reviewed every result.

- Earlier build review: the assistant reported 120 tests passing, along with successful sample and 100,000-row runs. Those results are recorded as historical checks from that review.
- On 2026-10-30, Codex ran the sample pipeline against a fresh database under `out/final_review/`: 30 events inserted, 10 rejected, and 11 sessions written. Reconciliation and answer-key checks passed. A rerun inserted 0 events and rebuilt 0 sessions; the sample SQL queries ran successfully.
- Codex added a check that compares every session's `event_count` with stored events in its time range, plus a regression test. The 11 reconciliation tests passed, followed by the full suite: 121 tests.
- Codex generated and processed 100,000 rows in `out/final_review/`: 94,000 events inserted, 6,000 rejected, and 14,534 sessions. Reconciliation and answer-key comparisons passed.

## What I still need to review personally

Before submission, I need to make sure I can explain the session boundary rule, ordering, duplicate handling, transaction and rollback behavior, reconciliation checks, and known limitations. I will update this statement with what I personally reviewed and changed after doing that work; I will not claim understanding or validation I have not completed.

## Limitations of AI-assisted work

- The generated tests reflect assumptions in the prompts. The separate generated answer key provides another check, but it does not eliminate that risk.
- The performance figures describe one machine and one generated workload; they are not a guarantee for other environments or larger data volumes.
