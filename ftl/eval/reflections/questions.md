# Open Questions

Genuine uncertainties. Not hypotheses to test—things to notice.

---

## Active

### Why does structural framing work?

The mechanism matters for generalization. Current hypothesis: negation is computationally harder than exclusion. "Don't do X" requires representing X then suppressing; "X is incoherent" never represents X as an option.

Alternative: framing clarity. Category errors are easier to understand than policy lists.

Watching for evidence.

### What makes a good evaluation template?

Four templates exist (anki, pipeline, errors, refactor). Unknown: which properties make a template useful for revealing protocol issues vs. just exercising the system.

### When does the harness itself need evaluation?

Meta-question. The instruments measure FTL; nothing measures the instruments. Potential failure mode: instruments drift from reality, metrics become vanity.

---

## Resolved

### Can learner spawning in campaigns be prevented?

**Yes**. Ontological framing via "Two Workflows" section. See L001.

### How can spawn relationships be captured?

**Resolved**. The main orchestrator session (UUID.jsonl) contains Task tool calls that spawn all agents. By collecting this file alongside agent-*.jsonl, the complete spawn chain is visible. See L002.

### How to match spawns to agents reliably?

**Resolved**. Match by (type, task_id) not (type, mtime). File mtimes cluster within milliseconds at collection time. Task_id extracted from spawn intent is authoritative. Fallback to type-only matching handles agents without task assignments (planner, synthesizer). See L003.

---
