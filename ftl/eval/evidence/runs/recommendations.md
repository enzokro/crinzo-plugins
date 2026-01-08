# FTL Agent Recommendations: anki-v13 → anki-v17

*Generated: 2026-01-08 10:31*

---

## Summary by Agent Type

| Type | Count | Avg Token Delta | Total Saved |
|------|-------|-----------------|-------------|
| planner | 1 | -76% | -123,181 |
| router | 4 | +8% | +48,704 |
| builder | 4 | -27% | -1,476,509 |
| synthesizer | 1 | +9% | +34,972 |

---

## Recommendations

### planner.md

**Average Delta**: -76%
**Consistent**: Yes
**Primary Change**: Removed Glob exploration

**Observed Changes**:
  - Removed Glob exploration (1x)
  - Shallower reasoning (1x)

**Sample Evidence**: 161,202 → 38,021 tokens

---

### builder.md

**Average Delta**: -27%
**Consistent**: No
**Primary Change**: Removed Glob exploration

**Observed Changes**:
  - Removed Glob exploration (2x)
  - Fewer Reads (2x)
  - Earlier first action (2x)

**Sample Evidence**: 947,961 → 112,952 tokens

---

## Agent Pair Details

### Step 0: planner

**Tokens**: 161,202 → 38,021 (-76%)
**Tools**: 7 → 4
**Reasoning Depth**: 4 → 1

**Behavioral Changes**:
  - Removed Glob exploration
  - Shallower reasoning (4 → 1)

**Epiplexity Metrics**:
  - Exploration overhead: 57% → 100%
  - Action density: 14% → 0%
  - First action pos: 4 → 4

### Step 1: router task 001

**Tokens**: 172,080 → 178,547 (+4%)
**Tools**: 11 → 10
**Reasoning Depth**: 6 → 6

**Behavioral Changes**:
  - Lower action density (46% → 30%)

**Epiplexity Metrics**:
  - Exploration overhead: 46% → 50%
  - Action density: 46% → 30%
  - First action pos: 5 → 5

### Step 2: builder task 001

**Tokens**: 947,961 → 112,952 (-88%)
**Tools**: 25 → 7
**Reasoning Depth**: 15 → 5

**Behavioral Changes**:
  - Removed Glob exploration
  - Fewer Reads (8 → 2)
  - Earlier first action (pos 8 → 2)
  - Shallower reasoning (15 → 5)
  - Fewer tool calls (25 → 7)

**Epiplexity Metrics**:
  - Exploration overhead: 32% → 29%
  - Action density: 60% → 71%
  - First action pos: 8 → 2

### Step 3: router task 002

**Tokens**: 172,396 → 238,295 (+38%)
**Tools**: 10 → 12
**Reasoning Depth**: 6 → 7

**Behavioral Changes**:
  - Added Glob exploration

**Epiplexity Metrics**:
  - Exploration overhead: 60% → 50%
  - Action density: 30% → 25%
  - First action pos: 6 → 6

### Step 4: builder task 002

**Tokens**: 1,078,980 → 231,291 (-79%)
**Tools**: 24 → 11
**Reasoning Depth**: 13 → 8

**Behavioral Changes**:
  - Removed Glob exploration
  - Fewer Reads (11 → 4)
  - Earlier first action (pos 12 → 3)
  - Shallower reasoning (13 → 8)
  - Fewer tool calls (24 → 11)
  - Higher action density (42% → 64%)

**Epiplexity Metrics**:
  - Exploration overhead: 50% → 27%
  - Action density: 42% → 64%
  - First action pos: 12 → 3

### Step 5: router task 003

**Tokens**: 218,732 → 155,600 (-29%)
**Tools**: 12 → 9
**Reasoning Depth**: 6 → 4

**Behavioral Changes**:
  - Earlier first action (pos 2 → 0)

**Epiplexity Metrics**:
  - Exploration overhead: 17% → 0%
  - Action density: 42% → 44%
  - First action pos: 2 → 0

### Step 6: builder task 003

**Tokens**: 351,910 → 555,556 (+58%)
**Tools**: 14 → 19
**Reasoning Depth**: 9 → 11

**Behavioral Changes**:
  - More tool calls (14 → 19)

**Epiplexity Metrics**:
  - Exploration overhead: 36% → 21%
  - Action density: 64% → 74%
  - First action pos: 5 → 4

### Step 7: router task 004

**Tokens**: 189,033 → 228,503 (+21%)
**Tools**: 9 → 10
**Reasoning Depth**: 5 → 6

**Behavioral Changes**:
  - Later first action (pos 0 → 7)

**Epiplexity Metrics**:
  - Exploration overhead: 0% → 70%
  - Action density: 33% → 30%
  - First action pos: 0 → 7

### Step 8: builder task 004

**Tokens**: 102,063 → 104,606 (+2%)
**Tools**: 6 → 6
**Reasoning Depth**: 3 → 4

**Epiplexity Metrics**:
  - Exploration overhead: 50% → 50%
  - Action density: 50% → 50%
  - First action pos: 3 → 3

### Step 9: synthesizer

**Tokens**: 376,972 → 411,944 (+9%)
**Tools**: 16 → 16
**Reasoning Depth**: 7 → 8

**Behavioral Changes**:
  - Earlier first action (pos 4 → 0)

**Epiplexity Metrics**:
  - Exploration overhead: 25% → 0%
  - Action density: 56% → 62%
  - First action pos: 4 → 0
