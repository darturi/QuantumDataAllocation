# Quantum Hardware Solvers

This directory contains QPU versions of the three simulated SQA
solvers.  Each one inherits `build_bqm()` from its simulated parent
**unchanged** — the QUBO formulation is identical, only the sampler
changes.  Simulated and hardware results for the same formulation are
therefore directly comparable.

For details on how each BQM is constructed, see
[`../simulated_solvers/README.md`](../simulated_solvers/README.md).

## Prerequisites

```
pip install -e ".[hardware]"      # installs dwave-system
dwave setup                       # configure your LEAP API token
dwave ping                        # verify connectivity
```

The hardware import is deferred inside `_get_hw_registry()` in both
experiment runners, so the rest of the repo continues to work in
environments without `dwave-system`.

## Files

| File | Class | Inherits from | Label | In default HW registry? |
|------|-------|---------------|-------|--------------------------|
| `SQA_HW.py` | `SQAHardwareSolver` | `SQASolver` | S1 HW | yes |
| `SQA_SF_HW.py` | `SQASFHardwareSolver` | `SQASlackFreeSolver` | S2 HW | yes |
| `SQA_DW_HW.py` | `SQADWHardwareSolver` | `SQADomainWallSolver` | S3 HW | **no** (opt-in via `include_s3=True`) |
| `__init__.py` | — | — | — | — |

S3 on hardware is opt-in for the same reason S3 is opt-in everywhere
else (see `../simulated_solvers/README.md`), with the additional
hardware concern that the linking constraint inflates chain lengths
faster than the assignment-only encodings.

## Constructor parameters

All three hardware solvers inherit the constructor of their simulated
parent.  In particular:

* `SQAHardwareSolver` takes the same five problem-definition arguments
  as `SQASolver`.
* `SQASFHardwareSolver` and `SQADWHardwareSolver` additionally accept
  `lambda_1` and `lambda_2` (positive floats, or both `None` for
  auto-calibration).  Calibration on hardware uses the same
  `dimod.ExactSolver`-based search as the simulated path; it does
  *not* require a QPU call.

All three additionally accept:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `solver_name` | `None` | D-Wave QPU identifier (e.g. `"Advantage_system6.4"`).  `None` = LEAP client default. |

Pinning a `solver_name` improves reproducibility, since D-Wave
periodically recalibrates machines and retires older systems.

## `solve()` parameters

QPU `solve()` swaps the simulated parameters for hardware ones:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `num_reads` | 100 | Annealing cycles (samples). Each is a real anneal, so the default is much lower than the simulated 1000. |
| `annealing_time` | 20 | Anneal duration in microseconds (Advantage supports ≈ 0.5–2000 µs). |
| `chain_strength` | `None` | Coupling strength for physical qubit chains. `None` uses `EmbeddingComposite`'s default heuristic (`uniform_torque_compensation`). |

`num_sweeps` and `beta_range` (simulation concepts) do not apply.

## Chain strength tuning

When `EmbeddingComposite` maps logical variables to physical qubits, a
single logical variable can require multiple physical qubits coupled
ferromagnetically into a "chain".  `chain_strength` controls how
strongly they're coupled:

* **Too weak**: chains break during annealing → high
  `chain_break_fraction` in the results, invalid logical states.
* **Too strong**: chain couplings dominate the energy landscape →
  problem signal is washed out, validity collapses anyway.

A reasonable manual starting point:

```python
chain_strength = 0.8 * max(abs(v) for v in bqm.quadratic.values())
```

S2's calibrated `λ₂` can be very small (≪ 1) on some instances while
its quadratic couplings on `A_{p,n}` pairs are `2·λ₂·size_p·size_p'`.
On hardware this is fine — chain strength dominates the smaller of the
two — but if you observe high chain breaks specifically on S2,
inspecting `solver.lambda_1` / `solver.lambda_2` is a useful first
diagnostic.

## `hardware_summary()`

After `solve()`, returns a dict of QPU execution metadata:

| Key | Description |
|-----|-------------|
| `wall_time_ms` | Total wall time including network + queue + readout |
| `qpu_access_time_us` | Total time the job spent on the QPU |
| `qpu_anneal_time_per_sample_us` | Anneal duration per sample (should match `annealing_time`) |
| `physical_qubits` | Sum of chain lengths across all logical variables |
| `logical_variables` | BQM variable count |
| `chain_break_fraction` | Mean fraction of samples with at least one broken chain |
| `num_reads` | Number of samples returned |

For scientific comparisons of hardware vs simulated performance, use
`qpu_access_time_us` (or the per-stage breakdown in `solver.qpu_timing`)
— wall-clock time on hardware is dominated by network latency and
queue wait, not computation.

## Additional instance attributes

After `solve()`, each hardware solver populates:

| Attribute | Description |
|-----------|-------------|
| `self.result` | Best sample (lowest energy) |
| `self.sampleset` | Full `dimod.SampleSet` with all reads |
| `self.embedding` | Logical → physical qubit mapping |
| `self.qpu_timing` | Full timing breakdown |
| `self.chain_break_fraction` | Mean chain break fraction |
| `self.physical_qubits` | Total physical qubits consumed |
| `self.lambda_1`, `self.lambda_2` | Calibrated lambdas (S2 HW, S3 HW only) |

## Usage example

```python
from solvers.quantum_hardware_solvers import SQASFHardwareSolver
from util.test_generation.json_to_dict import json_to_test_case
from util.calculate_solution_cost import calculate_solution_cost, is_valid_solution

nodes, partitions, k_safety, requests, comm_costs = json_to_test_case(
    "test_bank/unit_partition/tier1/n3_p4/n-3_p-4_1.json"
)

solver = SQASFHardwareSolver(nodes, partitions, k_safety, requests, comm_costs)
time_ms, result = solver.solve(num_reads=200, annealing_time=50)

cost = calculate_solution_cost(nodes, partitions, k_safety, requests, comm_costs, result)
valid = is_valid_solution(nodes, partitions, k_safety, requests, comm_costs, result)

print(f"Cost: {cost}, Valid: {valid}")
print(f"Calibrated lambdas: {solver.lambda_1}, {solver.lambda_2}")
print(solver.hardware_summary())
```

## Formulation restrictions

After Phases 1–3 there are no per-solver capacity or partition-size
restrictions: all three solvers accept arbitrary non-negative integer
capacities and partition sizes.  See
[`../simulated_solvers/README.md`](../simulated_solvers/README.md) for
the encoding-specific caveats (e.g. S2's calibrated lambdas; S3's
near-optimum-only guarantee on tight instances).
