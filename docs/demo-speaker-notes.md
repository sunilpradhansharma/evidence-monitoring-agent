# Evidence Monitoring AI Agent — demo speaker notes

A ~1-page script to read aloud while presenting the web UI to a Medical Affairs / Commercial
audience. Each section is 2–4 sentences. Acronyms are expanded on first use. Keep it consistent
with the on-screen copy.

---

**Opening — what this system does.**
This is the Evidence Monitoring AI Agent. It checks, on a schedule, how public AI models — large
language models, the technology behind chatbots — describe our therapy compared with competitors,
so Medical Affairs and Commercial can see what prospects, patients, and providers are being told.

**The guardrail to state up front.**
Nothing is sent to any model unless a human approves it first. The system only queries, records,
and shows findings; it never contacts anyone or takes action on its own. The AI produces a score;
deterministic rules in our code — not the AI — decide what gets flagged.

**The headline (top of the Reports tab).**
At the top you see one plain-language sentence summarizing the selected run: the average sentiment
toward our therapy and how many responses were flagged, with a short "why" — for example, a
competitor rated higher on some questions, or our therapy not mentioned on others. It's the
thirty-second read of the run.

**The run summary cards — and what "truncated" and "capture rate" mean.**
The cards count this run's responses: total, successful, and two cards that flag trouble. The
Truncated card turns amber if any answer was cut off at the model's length limit — we keep the
partial text and still score it. The Failed/blocked card turns red if any call failed or was
blocked by a provider safety filter. Capture rate is the share of attempts we successfully
captured; our target is at least ninety-five percent, shown with a green check when met.

**The coverage map (question × model).**
This grid is the heart of the view: each row is an approved question, each column a model, and each
colored cell shows how that model represented our therapy — green favorable, amber partial, red
negative or flagged, gray absent, and purple for a wrong-indication answer. A small dashed corner
tag marks a truncated response. Click any cell to read the full answer and the scoring rationale.

**Sentiment by model.**
Below the map, this shows the average sentiment toward our therapy for each model on a scale from
minus one to plus one, with a small bar and the exact value, plus a breakdown by therapeutic area.
It tells you which models are warmest or coolest about our therapy at a glance.

**Citation status.**
This panel counts whether the model cited the correct indication — the disease or condition the
therapy is for. The one to watch is "wrong indication," shown in a distinct alarming color: it
means the model returned content for the wrong disease, which could route a person to the wrong
information.

**Alerts and flagged responses.**
Here is the triaged list. Each flagged response shows the question, the model, the rule that fired,
and a one-line reason; wrong-indication is reserved for the highest severity. Anything truncated is
tagged so you know it was judged on partial text. Expand any item for the full response and
rationale.

**The Approvals tab — the live approval moment.**
This is the only tab that can change anything, and the change is always human-made and audited. The
banner restates the rule: only approved questions are ever sent, and every approve or reject is
recorded with the reviewer's name and a timestamp in an append-only audit log. I'll type my name —
notice the buttons stay disabled until I do — pick a pending question, and approve it; it moves into
the read-only approved list, and that action is now in the audit trail.

**Closing — this is a working POC; here's what's next.**
Everything you've seen runs locally today on real captured responses — proof of concept, or POC,
not a mock-up. Next steps are scaling the approved question bank across more therapeutic areas,
moving storage and the AI calls to our production cloud behind the same clean interfaces, and adding
run-over-run change detection so we can see when a model's answer shifts over time.
