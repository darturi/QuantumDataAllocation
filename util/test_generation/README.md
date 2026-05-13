# Test Generation

This directory contains the scripts that generate benchmark test cases for the data-allocation solvers. Each test case defines a problem instance: a set of storage nodes with capacities, a set of data partitions with sizes, a replication factor (k-safety), per-(partition, node) request frequencies, and per-partition communication costs. The solvers attempt to assign partitions to nodes in a way that satisfies the k-safety and storage constraints while minimising communication cost.

## Quick start

From the QuantumClean project root:

```
python -m util.test_generation.populate_test_bank
```

This populates `test_bank/` with 1,780 JSON test cases across both formulations and both tiers. The script is deterministic — running it again overwrites every file with identical content.

## File overview

| File | Purpose |
|---|---|
| `populate_test_bank.py` | Top-level orchestrator. Defines the parameter grids for tier 1 and tier 2, then calls the batch generators to populate `test_bank/unit_partition/` and `test_bank/arbitrary_partition/`. This is the script you run. |
| `generate_test_case.py` | Generates a single arbitrary-partition test case. Partition sizes are drawn randomly from a configurable range (default 5–20). Node capacities are scaled from a feasibility-derived minimum and rounded up to the nearest Mersenne number. Also provides `generate_batch()` for writing multiple cases to disk. |
| `generate_unit_test_case.py` | Generates a single unit-partition test case. All partition sizes are fixed to 1 and capacities represent partition counts rather than bytes. Also provides `generate_unit_batch()`. |
| `generate_paired_test_cases.py` | Generates matched pairs of test cases (one arbitrary, one unit) that share identical request frequencies and communication costs. Useful for controlled experiments that isolate the effect of the formulation change. Provides `generate_paired_batch()` for writing pairs to disk. |
| `json_to_dict.py` | Loader utility. Reads a generated JSON file and returns the `(nodes, partitions, k_safety, requests, comm_costs)` tuple that the solver constructors expect. Handles the string-to-tuple key conversion for the requests dict. |

## Output structure

```
test_bank/
    unit_partition/
        tier1/
            n2_p3/          (10 JSON files)
            n2_p4/
            ...
            n9_p50/
        tier2/
            n2_p3/
            ...
            n15_p100/
    arbitrary_partition/
        tier1/              (same grid as unit tier 1)
        tier2/              (same grid as unit tier 2)
```

Each leaf directory contains 10 test case files named `n-{N}_p-{P}_{i}.json` where `i` ranges from 1 to 10.

## Tiers

**Tier 1** matches the parameter range used in earlier grid-sweep experiments, making it suitable for apples-to-apples comparisons with previous results.

| | Nodes | Partitions |
|---|---|---|
| Tier 1 | 2, 3, 5, 7, 9 | 3, 4, 8, 12, 18, 26, 36, 50 |
| Tier 2 | 2, 3, 5, 7, 9, 12, 15 | 3, 8, 18, 36, 50, 75, 100 |

**Tier 2** extends both axes to larger problem sizes where optimised formulations (e.g. slack-free, domain-wall) are expected to show a clearer advantage. Tier 2 is a superset of tier 1 by design — the overlap makes it possible to compare across tiers at shared grid points.

## Test case format

Every JSON file has the following structure:

```json
{
    "nodes": {
        "n1": 31,
        "n2": 15
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
    }
}
```

Unit-partition test cases also include a `nodes_raw` field (identical to `nodes`) for backward compatibility.

The request keys are string-encoded tuples like `"(p1, n2)"`. The `json_to_dict.json_to_test_case()` function handles parsing these back into Python tuple keys `("p1", "n2")` when loading a test case for a solver.

## Mersenne capacities

All node capacities are rounded up to the nearest Mersenne number (numbers of the form 2^k - 1: 1, 3, 7, 15, 31, 63, 127, ...). This is a requirement of the QUBO storage constraint formulation — the slack variables use binary-weighted chunks that sum to exactly 2^k - 1. If a capacity were not a Mersenne number, the slack variables could sum beyond the actual capacity, and the constraint would fail to penalise storage overflows.

## Feasibility guarantees

The generators enforce two feasibility conditions on every test case:

1. **Total capacity is sufficient**: the sum of all node capacities is at least k-safety times the total size of all partitions. This ensures there is physically enough space to store k copies of every partition.
2. **Every node can hold the largest partition**: each node's capacity is at least as large as the biggest individual partition (relevant for the arbitrary-partition formulation where sizes vary).

The `capacity_factor` parameter controls how much slack is added beyond the feasibility minimum. Lower values (e.g. 1.1–1.3) produce tighter problems where the storage constraint is more likely to bind; higher values (e.g. 1.5) produce looser problems where the solver has more room. The unit-partition cases use a `capacity_factor` of 1.3 (tighter) and the arbitrary-partition cases use 1.5 (looser), reflecting the different difficulty profiles of the two formulations.

## Reproducibility

Every test case is generated with a deterministic seed derived from the base seed, node count, and partition count: `seed = base_seed + n_nodes * 1000 + n_partitions`. Within a batch of 10 cases, case `i` uses seed `base_seed + i`. This means regenerating the test bank always produces byte-identical output, and individual test cases can be reproduced in isolation if you know the seed.

Tier 1 uses a base seed of 1000 and tier 2 uses 2000, so there is no seed collision between tiers.

## Loading test cases for a solver

```python
from util.test_generation.json_to_dict import json_to_test_case
from simulated_solvers.SQA import SQASolver

nodes, partitions, k_safety, requests, comm_costs = json_to_test_case(
    "test_bank/unit_partition/tier1/n3_p8/n-3_p-8_1.json"
)

solver = SQASolver(nodes, partitions, k_safety, requests, comm_costs)
time_taken, result = solver.solve()
solver.format_answer(result)
```
