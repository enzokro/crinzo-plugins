# Open Questions

Genuine uncertainties. Not hypotheses to test—things to notice.

---

## Active

### What is the optimal test methodology for token efficiency?

Four data points now:
- **v36 baseline**: Implementation-first, tests written during integration → 908K tokens
- **v38 TDD**: Test-per-task, tests co-evolve with implementation → 993K tokens (+9.3%)
- **v40 SPEC-first**: All tests written upfront, then implement to pass → 1,444K tokens (+45.4%)
- **v41 SPEC-first**: Same methodology, different failure → 2,195K tokens (+142%)

**Ranking by efficiency**: Implementation-first > TDD >> SPEC-first

**SPEC-first has proven DISASTROUSLY inefficient** with two consecutive runs showing +45% and +142% regressions. TWO distinct failure modes identified:
1. **v40**: API mismatch (tests assumed Table interface, got Database)
2. **v41**: Test isolation assumptions (tests assumed id=1, got id=4 due to SQLite auto-increment)

**Critical insight**: SPEC-first creates immutable contracts that builders cannot renegotiate. When tests have invalid assumptions, builders must work around them instead of fixing them.

**Updated hypothesis**: SPEC-first should be ABANDONED for exploratory builds. The combination of (1) uncertainty about implementation constraints and (2) inability to modify tests creates a structural trap with no escape.

**Open question**: Is there a "SPEC-lite" approach? E.g., write test NAMES/signatures upfront, but defer test BODIES until implementation is understood?

### Should SPEC-first methodology be abandoned entirely?

v40 and v41 both used SPEC-first and both showed catastrophic regressions (+45% and +142% respectively). The methodology has TWO identified failure modes:
1. API mismatch (v40)
2. Test isolation assumptions (v41)

Both failures share the root cause: **builders cannot modify tests**. When SPEC tests contain invalid assumptions, builders have no escape except convoluted workarounds in implementation code.

v41's Builder 003 explicitly diagnosed "the test is fundamentally broken because it assumes id=1" but could only modify app.py, leading to a 1.16M token debugging spiral implementing a hack.

**Recommendation**: Return to implementation-first or TDD for next run. If SPEC-first is to be retained, tests MUST be modifiable by downstream builders.

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

**Status**: DEFINITIVELY CONFIRMED in v41 - moving to Resolved section.

v30=3.4, v31=4.4, v32=3.4, v33=4.7, v34=3.4, v35=5.4, v36=4.3, v38=5.6, v40=7.35, **v41=17.6 (NEW RECORD - 140% above v40)**. Now have ten data points.

**DEFINITIVELY CONFIRMED**: Entropy measures exploration pattern depth within agents, NOT failure modes. v41 achieved HT=17.6 with 5/5 tasks complete. Builder 003 alone had 21 reasoning traces - one deep debugging session dominated total entropy.

**Confirmed formula**: HT ≈ sum(per_agent_reasoning_trace_count) × complexity_factor
- v41=17.6: Builder 003 had 21 traces. Entropy variance component = 14.63.
- v40=7.35: Total traces across builders ~25+, SPEC-first methodology required extensive exploration
- v38=5.6: Builder 001 had 8-step trace with extensive exploration
- v35=5.4: Builder 004 had 7 reasoning traces (1 blocked)
- v30=3.4: Minimal exploration, action-first patterns throughout

**Key insight**: Entropy = cognitive effort, not failure correlation. One extremely deep debugging session can DOMINATE total entropy. v41's successful but painful completion proves entropy is NOT capped by task success. Optimization: reduce entropy by preventing debugging spirals (better context, mutable specs), not by avoiding failures.

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

### What does entropy (HT) measure?

**Definitively resolved in anki-v41**. Entropy measures cognitive exploration depth within agents, NOT failure modes.

v41 provides ultimate confirmation: HT=17.6 (140% above v40) with 5/5 tasks complete, 1 fallback. Builder 003 alone had 21 reasoning traces, driving entropy to record levels despite successful completion.

**Confirmed formula**: HT ≈ sum(per_agent_reasoning_trace_count) × complexity_factor

Data points: v30=3.4, v31=4.4, v32=3.4, v33=4.7, v34=3.4, v35=5.4, v36=4.3, v38=5.6, v40=7.35, v41=17.6

**Key insight**: One extremely deep debugging session can DOMINATE total entropy. Entropy is NOT capped by task success.

**Optimization implication**: Reduce entropy by preventing debugging spirals (better upfront context, mutable specs, workspace warnings), not by avoiding failures. Entropy is cognitive effort; low entropy = action-first patterns with minimal exploration.

### Why did entropy drop significantly in v30?

**Fully resolved with v40 data**. v30's HT=3.4 reflected minimal exploration patterns (action-first cognitive state). v40's HT=7.35 with perfect success proves entropy is NOT correlated with failures. The variance across runs (3.4 to 7.35) reflects different cognitive exploration depths based on methodology and context availability.

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
