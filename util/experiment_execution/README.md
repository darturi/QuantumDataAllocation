# Experiment Execution

The harness in this directory loads pre-generated test cases from
`test_bank/`, runs every registered solver on each one, records a set
of statistics about the output, and writes results incrementally to a
JSON file in `result_bank/`.

It supports three solver types: classical ILP (baseline), simulated SQA
(Path Integral Monte Carlo on CPU), and QPU (D-Wave hardware).
Simulated and hardware results are written to separate directories.

## Quick start

```bash
# Default registry: ILP + S1 + S2.  Sampler budget defaults are
# num_reads=200, num_sweeps=500 -- tuned for the lean tier-1 test bank.
python -m util.experiment_execution.run_unit_partition_experiment
python -m util.experiment_execution.run_arbitrary_partition_experiment
```

For the full grid or tier 2, raise the sampler budget back up (see
"Sampler budget" below):

```python
from util.experiment_execution.run_unit_partition_experiment import run_unit_experiment
run_unit_experiment(tier="tier2", num_reads=1000, num_sweeps=1000)
```

To opt in to S3 (see below):

```python
from util.experiment_execution.run_unit_partition_experiment import (
    run_unit_experiment, SOLVER_REGISTRY_SIM_WITH_S3,
)
run_unit_experiment(extra_registry=SOLVER_REGISTRY_SIM_WITH_S3)
```

To run on D-Wave hardware (`pip install -e ".[hardware]"` + LEAP token):

```python
from util.experiment_execution.run_unit_partition_experiment import run_unit_experiment
run_unit_experiment(tier="tier1", hardware=True, num_reads=100, annealing_time=20)
```

Hardware mode also supports S3 via `include_s3=True`.

## File overview

| File | Purpose |
|------|---------|
| `run_experiment.py` | Core Phase-5 harness.  `run_experiment(...)`, `discover_test_cases(...)`, plus per-type runners (`_run_ilp`, `_run_sqa`, `_run_qpu`). |
| `run_unit_partition_experiment.py` | Thin wrapper.  Defines `SOLVER_REGISTRY_SIM` (ILP + S1 + S2) and `SOLVER_REGISTRY_SIM_WITH_S3` (adds S3).  Writes results as `UnitExperiment_N.json`. |
| `run_arbitrary_partition_experiment.py` | Same shape as the unit runner.  S1 and S2 both support arbitrary partition sizes after Phase 2, so both are in the default registry. |

## Default vs opt-in registries

| Registry | Solvers | When to use |
|----------|---------|--------------|
| `SOLVER_REGISTRY_SIM` (default) | ILP, S1, S2 | Headline benchmark runs |
| `SOLVER_REGISTRY_SIM_WITH_S3` | ILP, S1, S2, **S3** | To reproduce the documented S3 negative result |
| `_get_hw_registry()` (default) | S1 HW, S2 HW (plus ILP from the sim registry) | Hardware runs |
| `_get_hw_registry(include_s3=True)` | adds S3 HW | Hardware S3 reproduction |

S3 is opt-in because its claimed coupling reduction does not
materialise on this problem class — see
[`../../solvers/simulated_solvers/README.md`](../../solvers/simulated_solvers/README.md).
The implementation is correct (it passes the loose-case oracle test) but
strictly dominated by S2 on every metric I measured.

## Solver types and dispatch

`run_experiment()` dispatches by the `"type"` field in each registry
entry:

| Type | Runner | Solver interface | Parameters passed |
|------|--------|------------------|-------------------|
| `"ilp"` | `_run_ilp()` | `solver.solve()` | None |
| `"sqa"` | `_run_sqa()` | `solver.solve(num_reads, num_sweeps, beta_range)` | `num_reads`, `num_sweeps`, `beta_range` |
| `"qpu"` | `_run_qpu()` | `solver.solve(num_reads, annealing_time, chain_strength)` | `num_reads`, `annealing_time`, `chain_strength` |

Registry entries can also carry `"kwargs": {...}` which are passed to
the solver constructor — useful for pinning S2/S3 lambdas:

```python
{"name": "SQA_SF_fixed", "class": SQASlackFreeSolver, "type": "sqa",
 "kwargs": {"lambda_1": 200.0, "lambda_2": 0.5}}
```

## Test-case metadata in results

Every per-case entry carries the test-case JSON's input dimensions
(`n_nodes`, `n_partitions`, `k_safety`) plus any **metadata** fields
from the source JSON, prefixed with `tc_` to avoid colliding with
solver-result keys.  Currently the only such field is:

| Entry key | Source | Description |
|-----------|--------|-------------|
| `tc_tightness` | `tightness` in test-case JSON | Storage-constraint tightness in `[0, 1]`.  Lets downstream analysis stratify results by how much the capacity constraint binds. |

Any new metadata added to the generator will surface automatically
under the same `tc_*` prefix -- no harness change required.

## Recorded statistics (Phase 5 schema)

Every per-solver result entry contains:

### All solvers

| Field | Description |
|-------|-------------|
| `cost` | Total communication cost.  `null` if the solver failed. |
| `valid` | Whether the solution satisfies *all* constraints. |
| `k_safety_violations` | Number of partitions whose copy count ≠ k_safety. |
| `capacity_overruns` | Number of nodes whose load exceeds capacity. |
| `wall_time_ms` | Wall-clock `solve()` duration in milliseconds. |
| `optimality_gap_absolute` | `solver_cost − ilp_cost` (may be negative if ILP failed but solver didn't). |
| `optimality_gap_relative` | `(solver_cost − ilp_cost) / ilp_cost`; `0.0` when both costs are zero; `null` only when genuinely undefined. |
| `error` | Exception message if the solver threw, otherwise `null`. |

### SQA solvers (additional)

| Field | Description |
|-------|-------------|
| `bqm_variables` | BQM variable count. |
| `bqm_interactions` | BQM quadratic coupling count. |
| `lambda_1`, `lambda_2` | Calibrated lambdas (S2, S3 only; `null` for S1). |

### QPU solvers (additional, on top of SQA fields)

| Field | Description |
|-------|-------------|
| `physical_qubits` | Sum of chain lengths after minor embedding. |
| `chain_break_fraction` | Mean fraction of samples with broken chains. |
| `qpu_anneal_time_per_sample_us` | Anneal duration per sample.  Use this, not wall time, for hardware comparisons. |

### How each statistic is calculated

**Communication cost.**  The objective the solvers are minimising:

```
cost = Σ over (p, n):  r_{p,n} · c_p · (1 − A_{p,n})
```

For every (partition, node) pair where the partition is *not* stored,
we pay the remote-fetch cost.  ILP finds the exact minimum; SQA/QPU
solvers approximate it.

**Validity.**  A solution is valid iff:

1. Each partition is stored on exactly `k_safety` nodes.
2. Each node's load (sum of assigned partition sizes) ≤ capacity.

ILP enforces these as hard constraints; QUBO solvers encode them as
penalty terms, so violations are possible if penalties are insufficient
or the annealer doesn't reach the ground state.

**`k_safety_violations` and `capacity_overruns`.**  Counts of the two
constraint families above.  Together with `valid`, these turn "the
solver failed" into a useful signal — you can distinguish "barely
infeasible" from "wildly wrong".

**Absolute vs relative gap.**  The absolute gap is always
`solver_cost − ilp_cost`.  The relative gap divides by `ilp_cost` —
but only when that's safe.  When both costs are zero (trivial
instances), relative is `0.0` (not `null`), which lets aggregate stats
include those cases.  When `ilp_cost == 0` but the solver returned a
non-zero cost, relative is `null` (the ratio is undefined; the absolute
gap captures the failure).

**BQM variables / interactions.**  Number of binary variables and
quadratic couplings.  Smaller is generally better (fewer qubits, less
embedding overhead), but fewer variables doesn't mean a better
formulation if it's solving a different problem.

**Lambdas.**  For S2 and S3, the calibrated `(λ₁, λ₂)` pair used to
build the BQM.  Recorded so any result can be reproduced exactly.

**Solve time.**  Wall-clock around `solver.solve()`.  Not directly
comparable across types — CBC startup, PIMC sweep cost, and network
RTT live in different orders of magnitude.  Treat as a budget tracker,
not a quantum-speedup metric.  For QPU comparisons, use
`qpu_anneal_time_per_sample_us`.

## Sampler budget

`num_reads` and `num_sweeps` are the dominant wall-clock levers for
SQA runs.  The defaults are tuned for the **lean** test bank:

| Problem size (BQM vars) | Recommended num_reads × num_sweeps |
|--------------------------|-------------------------------------|
| ≤ 20 | 100 × 200 |
| 20–40 | **200 × 500 (default)** |
| 40–80 | 500 × 1000 |
| > 80 | 1000 × 1000 |

For tier 1 unit, almost all cases have ≤ 50 BQM variables, so the
defaults are appropriate.  For tier 2 or the full grid, bump to
`num_reads=1000, num_sweeps=1000` (the previous default).

Reducing the sampler budget cuts wall time roughly linearly; cutting
test-case counts also cuts wall time linearly.  Together a tier-1 unit
sweep at lean defaults runs in tens of minutes rather than hours.

## Filtering and partial runs

```python
from util.experiment_execution.run_unit_partition_experiment import run_unit_experiment

# Tier 1, only 3-node and 5-node problems
run_unit_experiment(tier="tier1", node_counts=[3, 5])

# Tier 2 cases with 50 or 100 partitions
run_unit_experiment(tier="tier2", partition_counts=[50, 100])

# Quick sanity check: first 10 test cases only
run_unit_experiment(max_cases=10)

# Adjust SQA parameters
run_unit_experiment(num_reads=500, num_sweeps=500)

# Hardware: tier 1, small problems, custom anneal time
run_unit_experiment(
    tier="tier1", hardware=True, node_counts=[2, 3],
    num_reads=200, annealing_time=50,
)
```

## Result output

Auto-incrementing filenames, separate directories for simulated vs
hardware:

```
result_bank/
    simulated_solver_results/
        UnitExperiment_1.json
        ArbitraryExperiment_1.json
    quantum_hardware_results/
        UnitExperiment_HW_1.json
```

Each run produces a new file; previous results are never overwritten.

### Sample result JSON (Phase 5)

```json
{
    "metadata": {
        "date": "2026-05-15",
        "time": "10:30:00",
        "total_cases": 6,
        "num_reads": 500,
        "num_sweeps": 500,
        "solvers": ["ILP", "SQA", "SQA_SF"],
        "harness_version": "phase5",
        "note": "Unit-partition benchmark: all partition sizes = 1."
    },
    "results": {
        "unit_n3p5_t70_1": {
            "source_file": "result_bank/verification_small/cases/unit_n3p5_t70_1.json",
            "n_nodes": 3, "n_partitions": 5, "k_safety": 2,
            "solvers": {
                "ILP": {
                    "cost": 88, "valid": true,
                    "k_safety_violations": 0, "capacity_overruns": 0,
                    "wall_time_ms": 2.3, "error": null,
                    "optimality_gap_absolute": 0,
                    "optimality_gap_relative": 0.0
                },
                "SQA": {
                    "cost": 88, "valid": true,
                    "k_safety_violations": 0, "capacity_overruns": 0,
                    "wall_time_ms": 1177.3,
                    "bqm_variables": 24, "bqm_interactions": 99,
                    "lambda_1": null, "lambda_2": null,
                    "error": null,
                    "optimality_gap_absolute": 0,
                    "optimality_gap_relative": 0.0
                },
                "SQA_SF": {
                    "cost": 88, "valid": true,
                    "k_safety_violations": 0, "capacity_overruns": 0,
                    "wall_time_ms": 587.7,
                    "bqm_variables": 15, "bqm_interactions": 45,
                    "lambda_1": 952.5, "lambda_2": 0.1,
                    "error": null,
                    "optimality_gap_absolute": 0,
                    "optimality_gap_relative": 0.0
                }
            }
        }
    }
}
```

`metadata.harness_version: "phase5"` marks files written by the
post-remediation harness; older files lack this field.

## Incremental saves

The harness writes the full JSON to disk after every test case, so an
interrupted run preserves all completed results.  `_NumpyEncoder` is
installed on every write (Phase 5 fix — the old harness defined the
encoder but didn't always install it, which would corrupt mid-run
saves when a solver returned numpy scalars).

## Solver registry format

```python
{"name": "SQA_SF", "class": SQASlackFreeSolver, "type": "sqa",
 "kwargs": {"lambda_1": 200.0, "lambda_2": 0.5}}     # kwargs optional
```

The `type` field controls dispatch as described above; `name` is used
as the result-JSON key and in progress output; `kwargs` (optional) are
passed to the solver constructor.

## Adding a new solver

1. Implement the solver as a subclass of `SolverBase`.
2. Add `build_bqm()` if it's QUBO-based.
3. Import it in the relevant wrapper script and add it to the
   appropriate registry list with the correct `type`.
4. For hardware solvers, put the import inside `_get_hw_registry()` so
   `dwave-system`-less environments still load.
5. Add at least one ExactSolver-based oracle test in `tests/`.

## Dependencies

* `util.calculate_solution_cost` — cost + validity utilities.
* `util.test_generation.json_to_dict` — `(nodes, …)` tuple loader.
* `solvers.simulated_solvers.SQA_SF.calibrate_lambdas` (transitively,
  via S2/S3) — instance-specific lambda calibration via
  `dimod.ExactSolver` for small problems, heuristic for large ones.
