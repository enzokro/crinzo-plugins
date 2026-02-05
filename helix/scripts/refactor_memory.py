#!/usr/bin/env python3
"""
Refactor helix.db into a coherent knowledge graph.
The memory I wish I had when developing and debugging helix.
"""

import sys
sys.path.insert(0, '.')
from lib.memory.core import store, health
from lib.db.connection import get_db, write_lock

def clear_and_rebuild():
    """Clear existing insights and rebuild with coherent structure."""
    conn = get_db()

    # Backup current state
    print("Current state:")
    print(health())

    # Clear all insights and edges
    print("\nClearing existing data...")
    with write_lock():
        conn.execute("DELETE FROM memory_edge")
        conn.execute("DELETE FROM insight")
        conn.commit()

    print("Building new knowledge graph...\n")

    memories = []

    # =================================================================
    # SECTION 1: DEBUGGING HELIX (when things break)
    # =================================================================

    memories.append((
        """DEBUGGING: Feedback loop not updating with_feedback count
SYMPTOMS: Tasks deliver successfully, injection-state files exist, but with_feedback unchanged
CHECK ORDER:
1. injection-state/{task_id}.json has 'names' array with injected memory names
2. task-status.jsonl has outcome 'delivered' or 'blocked' for that task_id
3. SubagentStop hook ran (check for task_id match between injection-state and task-status)
4. Hook calls feedback() with correct names from injection state
5. feedback() in core.py increments helped/failed via use_count
ROOT CAUSE: Usually SubagentStop hook not matching task_id between injection-state and task-status, or feedback() not being called""",
        ["debugging", "feedback-loop", "systemic"]
    ))

    memories.append((
        """DEBUGGING: wait.py returns but INSIGHT lines not visible to orchestrator
SYMPTOMS: Builder emits INSIGHT in output, orchestrator never sees it during build loop
ROOT CAUSE: wait.py polls task-status.jsonl which only contains summary field, not full output
INSIGHT lines only appear in late task-notifications after agent completes
FIX NEEDED: SubagentStop hook should extract INSIGHT before wait.py returns, write to separate file
WORKAROUND: Accept late task notifications will reveal insight data after build loop""",
        ["debugging", "wait-py", "insights", "systemic"]
    ))

    memories.append((
        """DEBUGGING: Memories injected but not relevant to task domain
SYMPTOMS: inject_context returns helix-internal memories for domain tasks (LRU cache gets CLI todo patterns)
ROOT CAUSE: Semantic search finds similar words but wrong domain context. Embeddings don't capture task-type (algorithm vs CLI vs web)
FIX OPTIONS:
1. Add domain tags and filter on recall
2. Use intent parameter (currently unused by inject_context)
3. Separate memory pools per domain
4. Weight recently-successful memories higher for similar task types""",
        ["debugging", "injection", "relevance", "systemic"]
    ))

    memories.append((
        """DEBUGGING: Builder outcome is 'unknown' in task-status.jsonl
SYMPTOMS: task-status.jsonl shows outcome: 'unknown' instead of 'delivered' or 'blocked'
ROOT CAUSE: SubagentStop hook regex didn't match builder output format
REQUIRED: Builder must output exactly 'DELIVERED:' or 'BLOCKED:' at start of line
Hook regex: r'^(DELIVERED|BLOCKED):' with MULTILINE flag
COMMON ISSUES: Wrong case 'Delivered:', wrong punctuation 'DELIVERED -', missing colon""",
        ["debugging", "hooks", "builders", "failure"]
    ))

    memories.append((
        """DEBUGGING: Explorers complete but findings are empty
SYMPTOMS: wait-for-explorers returns, .helix/explorer-results/*.json have empty findings arrays
CHECK ORDER:
1. Explorer output contains JSON block with 'findings' key
2. SubagentStop uses get_last_json_block() to extract
3. JSON is valid (no trailing commas, proper quotes)
4. Explorer prompt requested structured output
ROOT CAUSE: Usually explorer output prose instead of structured JSON""",
        ["debugging", "explorers", "failure"]
    ))

    memories.append((
        """DEBUGGING: Parallel builders fail with 'file modified since read'
SYMPTOMS: When tasks 2 and 3 both edit same file, one gets Edit tool rejection
ROOT CAUSE: Edit tool requires file unchanged since last Read
FIX FOR BUILDER: Re-read file immediately before each edit
FIX FOR PLANNER: Avoid parallel tasks on same file, or orchestrator sequences them
LEARNED: Task 3 discovered this pattern during LRU cache build with TTL and eviction parallel tasks""",
        ["debugging", "parallel-builds", "edit-conflicts", "pattern"]
    ))

    # =================================================================
    # SECTION 2: HELIX ARCHITECTURE (how it works)
    # =================================================================

    memories.append((
        """ARCHITECTURE: Helix data flow through phases
EXPLORE: Spawn haiku explorers (background) → SubagentStop extracts findings → .helix/explorer-results/*.json → orchestrator merges
PLAN: Spawn opus planner (foreground) → returns PLAN_SPEC directly → orchestrator creates TaskCreate/TaskUpdate
BUILD: Spawn opus builders (background) → SubagentStop extracts outcome/insight → .helix/task-status.jsonl → wait.py polls
LEARN: Orchestrator reflects → stores session insights via store()
KEY FILES: injection-state/{task_id}.json (injected names), task-status.jsonl (outcomes), explorer-results/*.json (findings)""",
        ["architecture", "data-flow", "fact"]
    ))

    memories.append((
        """ARCHITECTURE: Memory scoring formula in recall()
BASE: score = (0.5 * relevance) + (0.3 * effectiveness) + (0.2 * recency)
RELEVANCE: Cosine similarity between query embedding and memory embedding
EFFECTIVENESS: use_count based, higher for memories that helped
RECENCY: Days since last_used, exponential decay
RESULT: Memories that are semantically similar, have helped before, and were recently useful score highest""",
        ["architecture", "scoring", "fact"]
    ))

    memories.append((
        """ARCHITECTURE: Tag-based memory categorization
DEBUGGING tags: debugging, failure, systemic - problems and their solutions
PATTERN tags: pattern, build-pattern - reusable solutions that worked
ARCHITECTURE tags: architecture, fact - immutable knowledge about helix
CONVENTION tags: convention, checklist - standards and processes
EVAL tags: eval, metrics - testing and validation guidance
EVOLUTION tags: evolution, history - tracking changes over time
Use multiple tags per memory for cross-category discovery""",
        ["architecture", "tags", "fact"]
    ))

    memories.append((
        """ARCHITECTURE: Database schema (insight table)
insight: id, name (unique slug), content (full text), embedding (384-dim blob), effectiveness (0-1), use_count, created_at, last_used, tags (JSON array)
memory_edge: from_name, to_name, rel_type (similar|solves|causes|co_occurs), weight (max 10.0)
exploration: objective, data (JSON), created_at - cached exploration results
CONNECTION: WAL mode, foreign keys, write_lock() for concurrency
EMBEDDINGS: all-MiniLM-L6-v2 via sentence-transformers, cosine similarity >= 0.85 for duplicates""",
        ["architecture", "database", "fact"]
    ))

    memories.append((
        """ARCHITECTURE: Hook system triggers and outputs
SessionStart: Creates .helix/plugin_root, initializes DB, checks venv
SubagentStop: Extracts DELIVERED/BLOCKED/INSIGHT from agent output, writes task-status.jsonl, applies feedback
HOOK OUTPUT LOCATIONS:
  explorer → .helix/explorer-results/{agent_id}.json
  builder → .helix/task-status.jsonl (appended line)
  planner → returns directly (foreground, no hook output)
CRITICAL: Hooks run in Claude Code's process after agent completion, not during""",
        ["architecture", "hooks", "fact"]
    ))

    # =================================================================
    # SECTION 3: DEVELOPING HELIX (adding features)
    # =================================================================

    memories.append((
        """DEVELOPING: Adding a new parameter to recall()
UPDATE IN ORDER:
1. core.py - Add to recall() signature, wire into scoring logic
2. core.py - Add argparse argument in CLI section (add_parser area)
3. __init__.py - Export if public API
4. SKILL.md Quick Reference - Add one-liner showing usage
5. reference/memory-api.md - Document fully
TEST: python3 lib/memory/core.py recall "test" --new-param value
VERIFY: Import works, CLI accepts flag, behavior correct""",
        ["developing", "recall", "checklist", "convention"]
    ))

    memories.append((
        """DEVELOPING: Cross-component features touch these files
PRIMITIVE (core.py): Raw capability - store, recall, feedback, health
INJECTION (context.py/injection.py): How memories get into agent prompts
EXTRACTION (hooks/SubagentStop): How memories get pulled from agent output
EXPORT (__init__.py): Public API surface
ORCHESTRATION (SKILL.md): How Claude uses the feature
REFERENCE (reference/*.md): Detailed documentation
EXAMPLE: Adding intent-aware recall required: core.py (logic), SKILL.md (instructions)""",
        ["developing", "architecture", "pattern"]
    ))

    memories.append((
        """DEVELOPING: Prefer minimal targeted changes over architectural rewrites
EXAMPLE - Five additions that matched research systems (MAGMA/Zep/A-MEM):
1. Edge weight cap at 10.0 (3 lines) - prevents runaway reinforcement
2. Multi-hop expand_depth (5 lines) - graph traversal
3. Temporal edge sorting (15 lines) - recent edges first
4. Conflict detection in store() (25 lines) - warns on similar memories
5. Intent routing in recall() (30 lines) - why/how/what/debug modes
TOTAL: ~80 lines closed 5 capability gaps. Each change isolated and testable.""",
        ["developing", "philosophy", "decision"]
    ))

    memories.append((
        """DEVELOPING: Testing memory system changes
THREE-LAYER VERIFICATION:
1. Import check: python -c 'from lib.memory.core import new_func; print("ok")'
2. CLI test: python lib/memory/core.py <cmd> <args> - verify argparse accepts flags
3. Functional test: store test data, recall, verify behavior
NO FORMAL TEST SUITE: Verification is manual through CLI
DATABASE: .helix/helix.db - inspect with sqlite3 for edge cases
RESET: python -c 'from lib.db.connection import reset_db; reset_db()' for clean state""",
        ["developing", "testing", "convention"]
    ))

    # =================================================================
    # SECTION 4: RUNNING EVALS (testing helix)
    # =================================================================

    memories.append((
        """EVAL: Pre-flight checklist before running helix
1. python3 "$HELIX/lib/memory/core.py" health - Record total_insights, with_feedback, effectiveness
2. ls .helix/injection-state/ - Note existing files (shows injection history)
3. ls scratch/ - Check existing projects, avoid duplicate domains
4. Choose domain exercising memory recall (TypeScript+Jest matches many patterns)
GOOD DOMAINS: data structures, async patterns, state machines, CLI tools
BAD DOMAINS: Exact repeats of existing scratch/ projects""",
        ["eval", "checklist", "convention"]
    ))

    memories.append((
        """EVAL: Phase validation commands
AFTER EXPLORE:
  ls .helix/explorer-results/ - Should have N json files for N explorers
  cat .helix/explorer-results/*.json | jq '.findings | length' - Count findings
AFTER PLAN:
  TaskList - Verify task count and DAG structure
  ls .helix/injection-state/ - Note count before BUILD
AFTER EACH BUILD WAVE:
  ls -la .helix/injection-state/ | tail -5 - New files for completed tasks
  cat .helix/task-status.jsonl | tail -3 - Verify delivered/blocked outcomes
AFTER LEARN:
  python3 "$HELIX/lib/memory/core.py" health - Compare to pre-flight""",
        ["eval", "validation", "convention"]
    ))

    memories.append((
        """EVAL: Metrics to track and what they mean
total_insights: Should increase if LEARN phase stored insights
with_feedback: Should increase if builders delivered with injected memories (BUG: often doesn't)
effectiveness: Average of helped/(helped+failed+1) - trending indicator
tasks_delivered: X/Y from build phase - 100% good but not required
tests_passing: If project has tests, X/Y - verifies builds work
learning_extraction: % of builders emitting INSIGHT lines (60% healthy)
builder_injection: % of builders receiving memories (should be 100%)
injection_state_files: Count of .helix/injection-state/*.json files""",
        ["eval", "metrics", "fact"]
    ))

    memories.append((
        """EVAL: Known issues to flag in eval logs
1. with_feedback unchanged - Feedback loop broken, hook not applying feedback
2. outcome: 'unknown' - Builder output didn't match DELIVERED/BLOCKED regex
3. Empty injection-state dir - inject_context not being called or not writing
4. injected_memories: [] - No relevant memories found for task
5. Planner BLOCKED - Impossible requirement or missing exploration context
6. Builder BLOCKED - Task dependency not met or code conflict
7. INSIGHT not visible during loop - wait.py visibility gap (expected behavior)""",
        ["eval", "known-issues", "systemic"]
    ))

    memories.append((
        """EVAL: Interpreting results for helix development
HEALTHY SESSION: 80%+ tasks delivered, with_feedback increased, 40%+ insight emission, total increased, effectiveness stable
UNHEALTHY SIGNALS:
  with_feedback unchanged despite deliveries → feedback loop bug
  0% insight emission → builder prompts need INSIGHT instruction
  effectiveness dropping → bad memories being reinforced
  tasks_delivered < 50% → planning or exploration issues
ACTION: Each unhealthy signal maps to DEBUGGING memories in this graph""",
        ["eval", "interpretation", "pattern"]
    ))

    # =================================================================
    # SECTION 5: BUILD PATTERNS (from eval projects)
    # =================================================================

    memories.append((
        """BUILD PATTERN: Greenfield TypeScript project setup
package.json: typescript, jest, ts-jest, @types/jest as devDependencies
tsconfig.json: ES2020 target, strict mode, declaration files, outDir: dist
jest.config.js: ts-jest preset, testMatch: **/*.test.ts
DIRECTORY: src/ for source, src/__tests__/ for tests
VERIFICATION: npm install succeeds, npx tsc --noEmit passes
PARALLELISM: Setup task has no deps, runs parallel with core implementation""",
        ["build-pattern", "typescript", "setup", "pattern"]
    ))

    memories.append((
        """BUILD PATTERN: DAG structure for data structure projects
OPTIMAL PARALLELISM:
  Wave 1: [project-setup] + [core-data-structure] - No deps, parallel
  Wave 2: [feature-A] + [feature-B] - Both depend on core, parallel if different code sections
  Wave 3: [tests] - Depends on all implementation tasks
EXAMPLE (LRU Cache): 001+004 parallel → 002+003 parallel → 005 sequential
ANTI-PATTERN: Linear DAG (1→2→3→4→5) wastes parallelism opportunity""",
        ["build-pattern", "dag", "parallelism", "pattern"]
    ))

    memories.append((
        """BUILD PATTERN: Testing time-dependent code
INJECT TimeProvider interface with now() method
Production: RealTimeProvider uses Date.now()
Tests: MockTimeProvider with advance(ms), set(timestamp) methods
JEST FAKE TIMERS:
  beforeEach(() => jest.useFakeTimers())
  afterEach(() => jest.useRealTimers())
  jest.advanceTimersByTime(ms) to trigger timeouts
USED IN: rate-limiter, circuit-breaker, lru-cache-ttl, retry-queue""",
        ["build-pattern", "testing", "time", "pattern"]
    ))

    memories.append((
        """BUILD PATTERN: Sentinel nodes in linked list structures
USE sentinel head/tail to eliminate null checks:
  this.head = new Node(null, null)
  this.tail = new Node(null, null)
  this.head.next = this.tail
  this.tail.prev = this.head
BENEFITS:
  addToHead: Always has this.head.next (never null)
  removeNode: Always has node.prev and node.next
  Empty list check: head.next === tail
USED IN: LRU cache, command stack, event queues""",
        ["build-pattern", "data-structures", "linked-list", "pattern"]
    ))

    memories.append((
        """BUILD PATTERN: Circuit breaker state machine
STATES: CLOSED → OPEN → HALF_OPEN → CLOSED
TRANSITIONS:
  CLOSED: Track failures. If failures >= threshold in window → OPEN
  OPEN: Reject all. After timeout → HALF_OPEN
  HALF_OPEN: Allow one probe. Success → CLOSED. Failure → OPEN
LAZY TRANSITION: Check timeout in getState() rather than external timer
  if (state === OPEN && Date.now() > openedAt + timeout) state = HALF_OPEN
USED IN: resilient-client, retry-circuit""",
        ["build-pattern", "circuit-breaker", "state-machine", "pattern"]
    ))

    memories.append((
        """BUILD PATTERN: Undo/redo with dual stack
ARCHITECTURE:
  undoStack: Commands executed
  redoStack: Commands undone
OPERATIONS:
  execute(cmd): cmd.execute(), push undoStack, clear redoStack
  undo(): pop undoStack, cmd.undo(), push redoStack
  redo(): pop redoStack, cmd.execute(), push undoStack
BATCH: Track executed indices, rollback in reverse on failure
PERSISTENCE: Serialize stack to JSON, reconstruct on load""",
        ["build-pattern", "undo-redo", "command-pattern", "pattern"]
    ))

    memories.append((
        """BUILD PATTERN: TTL cache with expiration
STORE expiresAt timestamp (not duration):
  node.expiresAt = ttl > 0 ? Date.now() + ttl : null
CHECK on get():
  if (node.expiresAt && Date.now() > node.expiresAt) { remove; return undefined }
CLEANUP: Periodic sweep via setInterval
  for each entry: if isExpired() then remove
DISPOSE: clearInterval on cache destruction
USED IN: lru-cache-ttl, session storage, token caches""",
        ["build-pattern", "cache", "ttl", "pattern"]
    ))

    # =================================================================
    # SECTION 6: EVOLUTION (helix history)
    # =================================================================

    memories.append((
        """EVOLUTION: Helix capability progression
SESSIONS 10-12: Basic flow (explore→plan→build), greenfield detection working
SESSIONS 13-15: Parallel builders, wait.py polling, background task management
SESSIONS 16-17: Memory injection via inject_context, injection-state tracking
SESSIONS 18-19: SubagentStop extracts insights, feedback loop attempted
SESSIONS 20+: Identified feedback bug, wait.py visibility gap, relevance issues
CURRENT: Build mechanics solid, learning loop partially broken
NEXT: Fix feedback application, surface insights during build, improve relevance""",
        ["evolution", "history"]
    ))

    memories.append((
        """EVOLUTION: Projects completed during helix evals
100% DELIVERY: todo-app (2x), fsm-designer, taskboard, command-stack, rate-limiter (2x), dep-resolver, resilient-client, circuit-breaker, retry-queue, event-sourcing, reactive-spreadsheet, constraint-solver, merkle-tree, observable-store, semaphore-pool, lru-cache-ttl
PARTIAL: memory-palace (0/3), collab-editor
PATTERNS: TypeScript+Jest reliable, parallel DAGs maximize throughput, data structures and async patterns exercise memory well
TOTAL: ~20 successful projects across eval sessions""",
        ["evolution", "projects"]
    ))

    memories.append((
        """EVOLUTION: Research system comparison (MAGMA/Zep/A-MEM/MemOS)
HELIX HAD: Type-specific scoring, effectiveness weighting, semantic search
HELIX ADDED: Edge weight caps, multi-hop traversal, temporal sorting, conflict detection, intent routing
HELIX MISSING:
  - Automatic consolidation (exists but never called)
  - Sample size normalization in effectiveness
  - Domain-aware retrieval
  - Cross-session memory linking
CONCLUSION: Core architecture sound, gaps in automation and refinement""",
        ["evolution", "research", "decision"]
    ))

    # =================================================================
    # STORE ALL MEMORIES
    # =================================================================

    print(f"Storing {len(memories)} memories...")
    stored_names = []
    for content, tags in memories:
        result = store(content, tags)
        print(f"  {result['status']}: {result['name'][:50]}...")
        stored_names.append(result['name'])

    # =================================================================
    # CREATE EDGES
    # =================================================================

    print(f"\nCreating edges...")

    # Map short names to full names for edge creation
    name_map = {}
    conn = get_db()
    for row in conn.execute("SELECT name FROM insight"):
        name_map[row['name'][:40]] = row['name']

    edges = [
        # Debugging → Architecture (caused_by)
        ("debugging-feedback-loop-not-updating-wit", "architecture-hook-system-triggers-and-ou", "caused_by"),
        ("debugging-wait-py-returns-but-insight-li", "architecture-hook-system-triggers-and-ou", "caused_by"),
        ("debugging-memories-injected-but-not-rele", "architecture-memory-scoring-formula-in-r", "caused_by"),
        ("debugging-builder-outcome-is-unknown-in-", "architecture-hook-system-triggers-and-ou", "caused_by"),

        # Architecture links (co_occurs)
        ("architecture-helix-data-flow-through-pha", "architecture-hook-system-triggers-and-ou", "co_occurs"),
        ("architecture-memory-scoring-formula-in-r", "architecture-tag-based-memory-categoriza", "co_occurs"),
        ("architecture-database-schema-insight-tab", "architecture-memory-scoring-formula-in-r", "co_occurs"),

        # Developing links (similar)
        ("developing-adding-a-new-parameter-to-rec", "developing-cross-component-features-touc", "similar"),
        ("developing-cross-component-features-touc", "architecture-helix-data-flow-through-pha", "similar"),

        # Eval links (co_occurs)
        ("eval-pre-flight-checklist-before-running", "eval-phase-validation-commands", "co_occurs"),
        ("eval-metrics-to-track-and-what-they-mean", "eval-interpreting-results-for-helix-deve", "co_occurs"),
        ("eval-known-issues-to-flag-in-eval-logs", "debugging-feedback-loop-not-updating-wit", "similar"),

        # Build pattern links (similar)
        ("build-pattern-greenfield-typescript-proj", "build-pattern-dag-structure-for-data-str", "co_occurs"),
        ("build-pattern-testing-time-dependent-cod", "build-pattern-circuit-breaker-state-mach", "co_occurs"),
        ("build-pattern-sentinel-nodes-in-linked-l", "build-pattern-undo-redo-with-dual-stack", "similar"),
        ("build-pattern-ttl-cache-with-expiration", "build-pattern-testing-time-dependent-cod", "co_occurs"),

        # Evolution links
        ("evolution-helix-capability-progression", "evolution-projects-completed-during-heli", "co_occurs"),
        ("evolution-research-system-comparison-mag", "developing-prefer-minimal-targeted-chang", "caused_by"),
    ]

    created = 0
    for from_prefix, to_prefix, rel_type in edges:
        from_name = name_map.get(from_prefix)
        to_name = name_map.get(to_prefix)
        if from_name and to_name:
            try:
                with write_lock():
                    conn.execute(
                        "INSERT OR IGNORE INTO memory_edge (from_name, to_name, rel_type, weight, created_at) VALUES (?, ?, ?, 1.0, datetime('now'))",
                        (from_name, to_name, rel_type)
                    )
                    conn.commit()
                created += 1
            except Exception as e:
                print(f"  Edge error: {e}")
        else:
            if not from_name:
                print(f"  Missing: {from_prefix}")
            if not to_name:
                print(f"  Missing: {to_prefix}")

    print(f"  Created {created} edges")

    print("\n" + "="*60)
    print("REFACTORING COMPLETE")
    print("="*60)
    print(health())

if __name__ == "__main__":
    clear_and_rebuild()
