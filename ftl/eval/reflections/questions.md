# Open Questions

Genuine uncertainties. Not hypotheses to test—things to notice.

---

## Active

### Is ST (epiplexity) correlated with efficiency or repeatability?

v32 showed ST=42.8 with 632K tokens (efficient). v31 showed ST=46.0 with 755K tokens (less efficient). This is inverse to the expected relationship. ST may measure structural consistency (how repeatable the execution pattern is) rather than efficiency (how few tokens it uses). Need to track ST vs tokens across more runs to see if this inverse correlation holds.

Hypothesis: ST measures conformance to learnable patterns, not absolute token cost. A highly structured but verbose execution scores high on ST.

### What does entropy (HT) actually measure?

v30=3.4, v31=4.4, v32=3.4, v33=4.7. The bimodal hypothesis (two stable states at 3.4 and 4.4) is now refuted - v33's 4.7 is outside both bands. Entropy appears to be neither noise nor bimodal, but genuinely variable. More puzzling: v33 had BETTER protocol fidelity than v32 but HIGHER entropy. Clean protocol → more entropy? Need to understand what HT captures. Current hypothesis: HT measures behavioral variance across agents, not execution quality. Protocol fidelity may actually increase variance by enforcing distinct roles.

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

### Why did entropy drop significantly in v30?

**Partially resolved, needs update**. v31's HT=4.4 suggested the v30 drop to HT=3.4 was noise. However, v32 returned to HT=3.4 again. The pattern is now v30=3.4, v31=4.4, v32=3.4 - potentially bimodal rather than noisy. See active question "Is entropy (HT) bimodal rather than continuous?" for updated hypothesis.

### Will cross-run learning compound?

**Resolved in anki-v29**. Yes, cross-run learning compounds when BOTH mechanisms are active: (1) upfront seeding via session_context/planner prompts, (2) runtime injection via workspace warnings. v29 achieved 690K tokens (-17.2% from v28's 834K). Task 003 specifically improved 46% (286K → 154K). The workspace warning "CRITICAL WARNING - date-string-mismatch" prevented the debugging spiral that plagued v23, v26, v28. See L011.

### How to prevent runtime debugging spirals?

**Resolved in anki-v29**. Workspace warnings work. Embed "CRITICAL WARNING - [pattern-name]" with mitigation in task workspace. Builder consumes workspace at task start AND references it during implementation. v29 achieved 46% token reduction on task 003 (154K vs 286K) using this approach. No code injection needed - workspace-level warnings are sufficient. See L011.

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
