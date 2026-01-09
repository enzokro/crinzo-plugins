# Open Questions

Genuine uncertainties. Not hypotheses to test—things to notice.

---

## Active

### Will cross-run learning compound?

v25 receives patterns from v23+v24. Will pattern signals increase appropriately? Will failure mode warnings actually prevent debugging spirals? Will knowledge transfer across domains (anki → pipeline)?

This is the key unlock for autonomous improvement.

**Status**: Answered in v28. Upfront memory injection WORKS (prior_knowledge.md reaches session_context and planner) but DOESN'T PREVENT runtime debugging spirals. Builder 003 hit date-string pattern at 286K despite knowledge seeding. The issue: knowledge is seeded at task START, but the debugging spiral occurs DURING test verification (after implementation). The builder discovers the issue through runtime failure, not through missing context.

**Conclusion**: Cross-run learning requires TWO mechanisms:
1. Upfront seeding (DONE) - knowledge available at planning
2. Runtime injection (NOT DONE) - warnings in implementation (code comments, workspace caveats, test fixtures)

New question added: "How to prevent runtime debugging spirals?"

### How to prevent runtime debugging spirals?

v23, v26, v28 all hit date-string-mismatch during Builder 003 test verification. Pattern: implement route → run tests → discover SQLite stores dates as strings → debug string/date comparison. Each time: 220K-286K tokens.

Knowledge seeding doesn't help because the issue is discovered DURING test verification, not at task start. Potential interventions:
1. **Workspace warning**: Add "Known issue: SQLite dates stored as strings" to 003 workspace
2. **Code comment injection**: Pre-seed main.py with `# Note: next_review is stored as ISO string`
3. **Test fixture setup**: Pre-configure test to expect string dates
4. **Planner specification**: Include date handling in task description

Which intervention is least invasive yet most effective?

### Why does planner still explore with complete specs?

v24 planner said "PROCEED" first but still did 5 tool calls (3 reads, 2 bash). The spec was complete. Is this confirmation behavior? Or protocol ambiguity?

Category test says "Zero exploration" for complete specs. Something's not clicking.

### What's the optimal protocol refresh cadence?

v13→v21 accumulated patches, then v22 regressed. v23 refactored, improved 35%. Should we consolidate every N runs? After every regression? Based on contradiction detection?

### Can first-thought classification predict cost early?

L006 says first thought reveals cognitive state. Could we detect "Let me look at Y" patterns and abort/retry with more context? Would save tokens on doomed runs.

### When does the harness itself need evaluation?

Meta-question. The instruments measure FTL; nothing measures the instruments. Potential failure mode: instruments drift from reality, metrics become vanity.

The epiplexity metric is new (v23). Is it measuring what we think?

---

## Resolved

### Can learner spawning in campaigns be prevented?

**Yes**. Ontological framing via "Two Workflows" section. See L001.

### How can spawn relationships be captured?

**Resolved**. The main orchestrator session (UUID.jsonl) contains Task tool calls that spawn all agents. By collecting this file alongside agent-*.jsonl, the complete spawn chain is visible. See L002.

### How to match spawns to agents reliably?

**Resolved**. Match by (type, task_id) not (type, mtime). File mtimes cluster within milliseconds at collection time. Task_id extracted from spawn intent is authoritative. Fallback to type-only matching handles agents without task assignments (planner, synthesizer). See L003.

### How to propagate failure mode knowledge across runs?

**Resolved**. Cross-run learning architecture: synthesizer extracts patterns → merge.sh persists to accumulator → setup.sh seeds to next run → planner/router consume. See L010.

### Why did v22 regress despite more guidance?

**Resolved**. Accumulated patches created contradictions. Agents executed both "Skip Section 1" AND Section 1. See L005, L008.

### How to make verification coherent?

**Resolved**. Added "Filter rule" to planner: `-k <filter>` requires ALL tests contain filter substring. Verification must be locally satisfiable. See L007.

---
