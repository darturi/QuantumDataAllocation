# Test Generation

This directory contains the scripts that generate benchmark test cases
for the data-allocation solvers.  Each test case is a problem instance:
storage nodes with capacities, data partitions with sizes, a
replication factor (`k_safety`), per-`(p, n)` request frequencies, and
per-partition communication costs.

After the Phase-4 refactor:

* Capacities are **arbitrary non-negative integers** — no Mersenne
  rounding (which the old generator applied to work around an S1 bug
  that has now been fixed).
* Each instance is stratified by a **tightness** parameter
  (`0.0` = loose capacity, `1.0` = exact minimum) so experiments can
  isolate the effect of the storage constraint.
* The generator runs an **ILP feasibility probe** before accepting an
  instance, with retries up to `feasibility_retries`.  This prevents
  the silent "ILP=399/400" failure mode of the old test bank.

## Quick start

From the project root:

```bash
python -m util.test_generation.populate_test_bank
```

This populates `test_bank/` with both unit- and arbitrary-partition
test cases across both tiers.  Generation is deterministic given a base
seed — running it again produces byte-identical output.

## File overview

| File | Purpose |
|------|---------|
| `populate_test_bank.py` | Top-level orchestrator.  Defines parameter grids for tier 1 and tier 2 and calls the batch generators. |
| `generate_test_case.py` | Generates a single arbitrary-partition instance.  Accepts a `tightness` parameter; verifies feasibility with an ILP probe. |
| `generate_unit_test_case.py` | Same shape as above but with `size_p = 1` for every partition. |
| `generate_paired_test_cases.py` | Generates matched pairs of test cases (one arbitrary, one unit) that share request frequencies and communication costs.  Useful when isolating the effect of partition-size variation alone. |
| `json_to_dict.py` | Loader.  Reads a generated JSON and returns the `(nodes, partitions, k_safety, requests, comm_costs)` tuple. |

## Output structure

```
test_bank/
    unit_partition/
        tier1/
            n2_p3/      ← 10 JSON files
            ...
            n9_p50/
        tier2/
            n2_p3/
            ...
            n15_p100/
    arbitrary_partition/
        tier1/
        tier2/
```

Each leaf directory contains 10 test cases named
`n-{N}_p-{P}_{i}.json`, `i = 1..10`.

## Tightness parameter

`tightness ∈ [0.0, 1.0]` controls how much slack is added beyond the
minimum capacity that guarantees feasibility:

| tightness | per-node capacity |
|-----------|-------------------|
| `0.0` | uniform in `[min_cap, 2.0 · min_cap]` |
| `0.5` | uniform in `[min_cap, 1.5 · min_cap]` |
| `1.0` | exactly `min_cap` |

The minimum is derived per instance as
`⌈k · Σ size_p / N⌉` (and at least `max(size_p)` so each node can hold
the largest single partition).

Higher tightness produces harder problems where the storage constraint
binds at the optimum.  Conclusions about storage encodings (slack vs
unbalanced penalty) are only meaningful at high tightness — at low
tightness, the constraint barely participates in the optimisation, so
all storage encodings look equivalent.

**Note** for arbitrary partitions: `tightness = 1.0` is sometimes
intrinsically infeasible (variable-size partitions can't always be
bin-packed at exact min capacity).  The generator retries up to
`feasibility_retries` times before raising `RuntimeError`.

## Grids and tiers

`populate_test_bank.py` exposes two grids: a **lean** default (used
because the dense grid is overkill for paired comparisons) and a
**full** opt-in via `--full`.

### Lean grid (default)

| | Nodes | Partitions | Cases per cell |
|---|---|---|---|
| Tier 1 | 3, 5, 9 | 4, 12, 26, 50 | 5 |
| Tier 2 | 5, 9, 15 | 18, 50, 100 | 5 |

With 3 tightness levels and both formulations, the lean grid produces
roughly 720 cases total (360 per formulation across both tiers).

Why the cuts:

* **N=2** dropped — with k_safety=2 every valid placement is forced,
  so the encoding has nothing to choose between.
* **N=7** dropped — interpolates between 5 and 9; doesn't change the
  scaling story.
* Small **P** values dropped — P=3 and P=4 are statistically
  indistinguishable; P=8 and P=12 likewise.
* **5 cases per cell** (not 10) — paired comparison between S1 and S2
  (same instance, same seed) cuts variance ~5–10× compared to
  unpaired, so 5 paired samples are sufficient for rank-ordering.

### Full grid (opt-in)

Run with `python -m util.test_generation.populate_test_bank --full`.

| | Nodes | Partitions | Cases per cell |
|---|---|---|---|
| Tier 1 | 2, 3, 5, 7, 9 | 3, 4, 8, 12, 18, 26, 36, 50 | 10 |
| Tier 2 | 2, 3, 5, 7, 9, 12, 15 | 3, 8, 18, 36, 50, 75, 100 | 10 |

Produces ~5,340 cases.  Use only when you need tight per-cell error
bars or fine-grained scaling curves — hours-to-days to run downstream.

## Test-case format

```json
{
    "nodes": {
        "n1": 10,
        "n2": 6
    },
    "partitions": {
        "p1": 1,
        "p2": 1,
        "p3": 1
    },
    "k_safety": 2,
    "requests": {
        "(p1, n1)": 4,
        "(p1, n2)": 7,
        "(p2, n1)": 0,
        "(p2, n2)": 3,
        "(p3, n1)": 9,
        "(p3, n2)": 1
    },
    "comm_costs": {
        "p1": 5,
        "p2": 2,
        "p3": 8
    },
    "tightness": 0.5
}
```

Notes:

* `nodes` capacities are arbitrary integers (e.g. `10`, `6` — neither
  Mersenne).  The old `nodes_raw` field for "backwards compatibility"
  is gone since there is no rounding to expose any more.
* Request keys are string-encoded tuples like `"(p1, n2)"`.
  `json_to_dict.json_to_test_case()` parses these back into Python
  tuple keys.
* `tightness` is recorded so downstream analysis can stratify results.

## Feasibility guarantees

The generator enforces these conditions:

1. **Total capacity is sufficient**:
   `Σ C_n ≥ k_safety · Σ size_p`.
2. **Every node can hold the largest partition**:
   `min C_n ≥ max size_p`.
3. **ILP probe**: the generated instance must be feasible per CBC.
   If not, the generator re-samples (up to `feasibility_retries`,
   default 20).  This catches the third-condition failure modes that
   variable-size bin-packing can produce even when conditions 1 and 2
   hold.

## Reproducibility

Every test case uses a deterministic seed derived from the base seed,
node count, and partition count:
`seed = base_seed + n_nodes · 1000 + n_partitions`.  Within a batch of
10 cases, case `i` uses seed `base_seed + i`.  Tier 1 uses
`base_seed = 1000`; tier 2 uses `2000`.

## Loading a test case

```python
from util.test_generation.json_to_dict import json_to_test_case
from solvers.simulated_solvers.SQA import SQASolver

nodes, partitions, k_safety, requests, comm_costs = json_to_test_case(
    "test_bank/unit_partition/tier1/n3_p8/n-3_p-8_1.json"
)

solver = SQASolver(nodes, partitions, k_safety, requests, comm_costs)
time_taken, result = solver.solve()
solver.format_answer(result)
```

## Tests

Generator behaviour is covered by `tests/test_generators.py`:

* Every (`tightness`, `n_nodes`, `n_partitions`) combination produces a
  feasible instance.
* The generator actually produces **non-Mersenne** capacities (sanity
  check that Phase 4's rounding removal stuck).
* JSON round-trip preserves every field.
