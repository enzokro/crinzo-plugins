---
version: 2.0
---

# Error Matching Rules

This document defines error matching for Builder retry decisions and Observer failure extraction.

See [ONTOLOGY.md](ONTOLOGY.md#block-status) for BLOCK vs FAIL distinction.

## Matching Algorithm

```
FOR each failure in prior_knowledge:
  1. Semantic similarity check
  2. Regex pattern match (if failure.match exists)

Match found → apply fix if budget allows
No match → BLOCK (discovery needed)
```

## Match Determination (Your Judgment)

Similarity scores are **guidance, not gates**. Determine match based on:

- Does the error describe the **same underlying issue**?
- Would the recorded fix **plausibly apply** here?
- Consider: exact substring (high confidence), semantic similarity (moderate), conceptual relation (low)

**A 0.5 similarity with obvious applicability beats 0.7 with tangential relevance.**

State your rationale: `"Matched {failure_name} because {reason}"`

## Similarity Reference (Not Thresholds)

| Error Pair | Typical Similarity | Guidance |
|------------|-------------------|----------|
| Same error, different wording | 0.7-0.9 | Strong match candidate |
| Related error type | 0.5-0.7 | Evaluate fix applicability |
| Conceptually similar | 0.3-0.5 | Match only if fix clearly applies |
| Unrelated | <0.3 | Likely not a match |

## Actions After Match Decision

| Decision | Budget >= 2 | Budget < 2 |
|----------|-------------|------------|
| Match found | Apply fix, retry | BLOCK (budget exhausted) |
| No match | BLOCK (discovery) | BLOCK (discovery) |

## Retry Count (Your Judgment)

Default: 1 retry. Override based on error characteristics:

| Indicator | Retry Guidance | Rationale |
|-----------|----------------|-----------|
| Timeout/connection errors | Up to 2 | Transient network issues |
| "flaky" in failure.tags | Up to 2 | Known intermittent failure |
| Race condition patterns | Up to 2 | Timing-dependent |
| Assertion with identical values | 1 max | Deterministic logic error |
| Import/syntax errors | 1 max | Won't self-resolve |

State rationale: `"Allowing {n} retries because {flakiness indicator}"`

BLOCK after max retries reached—even flaky errors need investigation if persistent.

## Discovery Principle

Builder MUST NOT attempt fixes for unmatched errors. Blocking preserves learning opportunities for Observer.
