# Experiment Execution

This directory contains the harness for running benchmark experiments against the pre-generated test cases in `test_bank/`. The harness loads test cases from disk, runs every registered solver on each one, records a set of statistics about each solver's output, and writes the results incrementally to a JSON file in `result_bank/simulated_solver_results/`.

## Quick start

From the QuantumClean project root:

```bash
# Run the unit-partition benchmark (tier 1, all solvers)
python -m util.experiment_execution.run_unit_partition_experiment

# Run the arbitrary-partition benchmark (tier 1, ILP + SQA only)
python -m util.experiment_execution.run_arbitrary_partition_experiment
```

Both commands require the test bank to be populated first. If `test_bank/` is empty, run `python -m util.test_generation.populate_test_bank` beforehand.

## File overview

| File | Purpose |
|---|---|
| `run_experiment.py` | Core harness. Provides `run_experiment()`, which takes a list of test case paths and a solver registry, runs everything, and writes the result JSON. Also provides `discover_test_cases()` for finding and filtering test cases on disk. |
| `run_unit_partition_experiment.py` | Thin wrapper for unit-partition benchmarks. Registers ILP + SQA + SQA_DW, discovers test cases from `test_bank/unit_partition/`, and writes results as `UnitExperiment_N.json`. |
| `run_arbitrary_partition_experiment.py` | Thin wrapper for arbitrary-partition benchmarks. Registers ILP + SQA only (the domain-wall solver requires unit partition sizes). Discovers from `test_bank/arbitrary_partition/`, writes results as `ArbitraryExperiment_N.json`. |

The two wrapper scripts are intentionally short. Each one wires up the right test-case directory, solver list, and output prefix, then delegates to the core harness. If you add a new solver, you only need to add it to the relevant wrapper's `SOLVER_REGISTRY` list.

## Recorded statistics

Every test case produces a per-solver result entry. The fields differ slightly between ILP and SQA solvers.

### ILP results

| Field | Description |
|---|---|
| `cost` | Total communication cost of the solution (see formula below). `null` if the solver failed. |
| `valid` | Whether the solution satisfies all constraints (k-safety and storage capacity). |
| `time_ms` | Wall-clock solve time in milliseconds. |
| `error` | Error message if the solver threw an exception, otherwise `null`. |

### SQA results

All of the above, plus:

| Field | Description |
|---|---|
| `bqm_variables` | Number of variables in the Binary Quadratic Model (assignment variables + any slack/auxiliary variables). |
| `bqm_interactions` | Number of quadratic interactions (couplings) in the BQM. |
| `optimality_gap` | Relative gap between the SQA cost and the ILP cost: `(sqa_cost - ilp_cost) / ilp_cost`. Only computed when both solutions are valid and the ILP cost is positive. `null` otherwise. |

### How each statistic is calculated

**Communication cost.** This is the objective function the solvers are minimising. For a solution with assignment variables A_pn (1 if partition p is stored on node n, 0 otherwise):

```
cost = sum over all (p, n):  r_pn * c_p * (1 - A_pn)
```

where r_pn is the request frequency for partition p at node n, and c_p is the communication cost for partition p. In plain terms: every time a partition is *not* stored locally on a node that requests it, the system pays the remote-fetch cost. The ILP finds the exact minimum; the SQA solvers approximate it.

**Validity.** A solution is valid if and only if it satisfies both constraints:

1. *k-Safety*: each partition is assigned to exactly k nodes (where k = k_safety, typically 2).
2. *Storage capacity*: the total size of partitions assigned to each node does not exceed that node's capacity.

The ILP enforces these as hard constraints, so a valid ILP solution is always feasible. The SQA solvers encode them as penalty terms in the QUBO objective, so an SQA solution can violate constraints if the penalty weights are insufficient or the annealer doesn't find a low-energy state.

**BQM variables.** The total number of binary variables in the QUBO formulation. This includes the assignment variables (one per partition-node pair) plus any auxiliary variables introduced by the formulation — slack variables for the standard SQA solver, or domain-wall chain variables for SQA_DW. Fewer variables generally means a smaller problem for the annealer.

**BQM interactions.** The number of quadratic couplings in the QUBO. This reflects the density of the problem graph that the annealer must navigate. Different formulations produce different coupling structures: the domain-wall encoding, for instance, replaces O(|N|^2) k-safety couplings with O(|N|) chain couplings, at the cost of introducing linking constraints.

**Optimality gap.** Measures how far an SQA solution is from the ILP optimum, expressed as a fraction. A gap of 0.0 means the SQA solver matched the ILP exactly. A gap of 0.15 means the SQA cost was 15% higher. This is only meaningful when both solutions are valid and the ILP cost is non-zero (when the ILP cost is 0, any valid SQA solution is also optimal).

**Solve time.** Wall-clock time measured with `time.perf_counter()` around the solver's `.solve()` call. For ILP this is the CBC branch-and-bound solve. For SQA this includes all num_reads annealing runs. Times are in milliseconds, rounded to one decimal place. Note that SQA times depend heavily on `num_reads` and `num_sweeps`.

## Filtering and partial runs

Both wrapper scripts accept optional filters so you can run subsets of the test bank without creating separate scripts:

```python
from util.experiment_execution.run_unit_partition_experiment import run_unit_experiment

# Run only tier 1, only 3-node and 5-node problems
run_unit_experiment(tier="tier1", node_counts=[3, 5])

# Run only tier 2 cases with 50 or 100 partitions
run_unit_experiment(tier="tier2", partition_counts=[50, 100])

# Quick sanity check: first 10 test cases only
run_unit_experiment(max_cases=10)

# Adjust SQA parameters
run_unit_experiment(num_reads=500, num_sweeps=500)
```

The `discover_test_cases()` function handles the filtering. It parses directory names (e.g. `n5_p18`) to match against `node_counts` and `partition_counts`, and applies `max_cases` as a hard cap on the total number of test cases after filtering.

## Result output

Results are written to `result_bank/simulated_solver_results/` with auto-incrementing filenames. Each run produces a new file — previous results are never overwritten.

```
result_bank/
    simulated_solver_results/
        UnitExperiment_1.json
        UnitExperiment_2.json
        ArbitraryExperiment_1.json
        ...
    quantum_hardware_results/
        (reserved for D-Wave hardware runs)
```

### Result JSON structure

```json
{
    "metadata": {
        "date": "2026-05-11",
        "time": "14:30:00",
        "total_cases": 400,
        "num_reads": 1000,
        "num_sweeps": 1000,
        "solvers": ["ILP", "SQA", "SQA_DW"],
        "note": "Unit-partition benchmark: all partition sizes = 1."
    },
    "results": {
        "n-3_p-8_1": {
            "source_file": "unit_partition/tier1/n3_p8/n-3_p-8_1.json",
            "n_nodes": 3,
            "n_partitions": 8,
            "k_safety": 2,
            "solvers": {
                "ILP": {
                    "cost": 42,
                    "valid": true,
                    "time_ms": 1.3,
                    "error": null
                },
                "SQA": {
                    "cost": 48,
                    "valid": true,
                    "time_ms": 350.2,
                    "bqm_variables": 38,
                    "bqm_interactions": 95,
                    "error": null,
                    "optimality_gap": 0.1429
                },
                "SQA_DW": {
                    "cost": 42,
                    "valid": true,
                    "time_ms": 410.7,
                    "bqm_variables": 30,
                    "bqm_interactions": 72,
                    "error": null,
                    "optimality_gap": 0.0
                }
            }
        }
    }
}
```

Each entry in `results` is keyed by the test case filename stem (e.g. `n-3_p-8_1`). The `source_file` field records the path relative to the test bank root, so you can trace any result back to its input.

## Incremental saves

The harness writes the full JSON to disk after every single test case. This means that if a long experiment is interrupted (crash, Ctrl-C, laptop running out of battery), all completed results are preserved in the output file. You can inspect partial results while an experiment is still running.

## Solver registry format

Each solver is registered as a dict with three keys:

```python
{"name": "SQA_DW", "class": SQADomainWallSolver, "type": "sqa"}
```

The `type` field determines how the harness invokes the solver. ILP solvers return a nested dict and don't have a BQM, so they follow a different code path than SQA solvers. The `name` is used as the key in the result JSON and in the progress output.

## Adding a new solver

1. Import the solver class in the relevant wrapper script.
2. Add it to the `SOLVER_REGISTRY` list with the appropriate `type`.
3. If it's an ILP-style solver (no BQM, returns a nested dict), use `"type": "ilp"`. If it's an SQA-style solver (has `build_bqm()` and `solve(num_reads, num_sweeps)`), use `"type": "sqa"`.

The core harness doesn't need to change.

## Dependencies on other modules

The harness imports from two utility modules that live outside this directory:

- `util.calculate_solution_cost` — provides `calculate_solution_cost()` and `is_valid_solution()`, used to evaluate every solver's output.
- `util.test_generation.json_to_dict` — provides `json_to_test_case()`, used to load test case JSON files into the tuple format the solver constructors expect.
