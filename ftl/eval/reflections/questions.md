# Open Questions

Genuine uncertainties. Not hypotheses to test—things to notice.

---

## Active

### Does TDD methodology reduce or increase token cost?

v38 used TDD (test-first) methodology and regressed +9.3% (993K vs v36's 908K). Builder 001 consumed 272K tokens (vs v36's 59K = +361%) despite following TDD correctly. The test surfaced a library behavior issue (`transform=True` not working as documented in fastlite 0.2.3).

**Hypothesis**: TDD efficiency depends on bug source:
- Application bugs: TDD reduces cost (catch early, fix once)
- Library/framework bugs: TDD may INCREASE cost (discover in test phase, investigate external behavior)

v38's Builder 001 trace shows TDD working correctly (write test → run test → see failure) but the failure pointed to library behavior, triggering exploration of fastlite internals. The builder even reached "Debugging budget exceeded" before accepting workaround.

Need more TDD runs to determine if v38 was an outlier (library bug) or if TDD consistently increases token cost by surfacing issues that would have been deferred in implementation-first approach.

### Why does identical protocol composition yield opposite outcomes?

v32 and v34 both had single_planner=false, single_synthesizer=false (synthesizer-as-planner pattern). Yet v32 achieved -16.2% improvement while v34 regressed +6.8% - a 23 percentage point swing. If protocol composition isn't deterministic, what is? Candidates:

1. **LLM sampling variance** - model temperature causes inherent outcome variance
2. **Cache state** - v32 may have benefited from warm caches that v34 lacked
3. **Orchestrator prompt drift** - subtle changes in how orchestrator invokes agents
4. **Task content coupling** - protocol patterns interact with task specifics non-linearly

This is important because it affects how to interpret protocol fidelity metrics. If protocol composition has high variance outcomes, optimizing for specific patterns may be futile.

### Is ST (epiplexity) correlated with efficiency or repeatability?

v32 showed ST=42.8 with 632K tokens (efficient). v31 showed ST=46.0 with 755K tokens (less efficient). This is inverse to the expected relationship. ST may measure structural consistency (how repeatable the execution pattern is) rather than efficiency (how few tokens it uses). Need to track ST vs tokens across more runs to see if this inverse correlation holds.

Hypothesis: ST measures conformance to learnable patterns, not absolute token cost. A highly structured but verbose execution scores high on ST.

### What does entropy (HT) actually measure?

v30=3.4, v31=4.4, v32=3.4, v33=4.7, v34=3.4, v35=5.4, v36=4.3, **v38=5.6**. Now have eight data points. **Hypothesis REFUTED in v38**: Blocked/failed outcomes do NOT dominate entropy. v38 achieved HT=5.6 (highest ever) with 0 blocked tasks and 0 fallbacks. All 3 builders completed successfully.

**New hypothesis after v38**: Entropy measures exploration pattern depth within agents, not just failure modes. v38 Builder 001 had trace pattern "AEEEEE.A" (8 reasoning steps with 5 marked as exploration) - high behavioral variance on a SUCCESSFUL task. The extensive debugging of fastlite `transform=True` behavior created high entropy without triggering failure.

**Updated formula candidate**: HT ≈ f(sum of exploration_trace_lengths) + small contribution from blocked_outcomes. This explains:
- v38=5.6: Builder 001 had 8-step reasoning trace with extensive exploration (no blocks)
- v35=5.4: Builder 004 had 7 reasoning traces (1 blocked)
- v36=4.3: Cleaner execution paths, fewer exploration steps per builder
- v30=3.4: Minimal exploration, action-first patterns throughout

The variance component in entropy is directly measurable: v38's info_theory shows `entropy.components.variance=5.6`. Need to investigate correlation between per-agent trace_count sum and entropy.

### How should workspace warnings handle cross-task bug manifestation?

v35 revealed a gap in the workspace warning mechanism. The date-string-mismatch warning protected task 003 (study routes), which completed cleanly in 130K tokens. But task 004 (tests) wrote tests that exercised study routes and hit the same bug, consuming 429K tokens and ending BLOCKED. The warning was task-specific, but the bug manifestation was cross-task.

**Partial resolution in v36**: Option 3 (expand Delta) naturally occurred - v36 Builder 004 fixed main.py when tests revealed the bug. This suggests builders can expand scope when completion requires it. The blocked state in v35 may have been due to stricter Delta interpretation, not a hard constraint.

Remaining options to explore:
1. **Propagate warnings to all downstream tasks** - Any task whose tests/verification might touch warned-about code gets the warning
2. **Fix upstream** - The `transform=True` warning is now understood to be necessary but insufficient. Need to add query comparison guidance (`.isoformat()` on Python dates)
4. **Integrated verification** - Don't skip verification in tasks 002/003 even if test file is empty (fail fast)

**New insight from v36 synthesizer**: The pattern evolved to "date-string-mismatch-query" - recognizing that `transform=True` handles storage but query comparisons need explicit `.isoformat()`. This refinement should prevent future occurrences.

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
