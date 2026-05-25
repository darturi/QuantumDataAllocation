# Solvers

This directory contains all solvers for the data-allocation optimisation
problem.  The problem asks: given a set of storage nodes with limited
capacity and a set of data partitions that must each be replicated on
exactly `k` nodes, find the allocation that minimises total remote
communication cost.

Every solver subclasses `SolverBase` (in `util/solver_base.py`), which
requires `solve()` and `format_answer()` and stores results in
`self.result` and timing in `self.time_taken`.

## Directory structure

```
solvers/
├── README.md                          ← this file
├── ILP.py                             ← exact classical baseline (PuLP/CBC)
├── simulated_solvers/
│   ├── README.md                      ← per-solver formulation docs
│   ├── SQA.py                         ← S1 (binary slack)
│   ├── SQA_SF.py                      ← S2 (calibrated unbalanced penalty)
│   └── SQA_DW.py                      ← S3 (opt-in; see below)
└── quantum_hardware_solvers/
    ├── README.md                      ← hardware parameters and metadata docs
    ├── __init__.py
    ├── SQA_HW.py                      ← S1 on QPU
    ├── SQA_SF_HW.py                   ← S2 on QPU
    └── SQA_DW_HW.py                   ← S3 on QPU (opt-in)
```

## Solver summary

| Solver | Type | Variables | Partition sizes | Capacities | Default registry |
|--------|------|-----------|-----------------|------------|-------------------|
| **ILP** | Classical (PuLP/CBC) | Assignment | Any | Any | yes |
| **S1** | Simulated SQA | Assignment + binary slack | Any | Any | yes |
| **S2** | Simulated SQA | Assignment | Any | Any | yes |
| **S3** | Simulated SQA | Assignment + wall vars | Any | Any | **no** (opt-in) |
| **S1 HW** | D-Wave QPU | Assignment + binary slack | Any | Any | yes (when hardware=True) |
| **S2 HW** | D-Wave QPU | Assignment | Any | Any | yes (when hardware=True) |
| **S3 HW** | D-Wave QPU | Assignment + wall vars | Any | Any | no (opt-in via `include_s3=True`) |

The **Mersenne-capacity** restriction that appeared in earlier versions
of this table is gone (Phase 1).  The **unit-partition** restriction
that previously applied to S2 and S3 is also gone (Phase 2/3) — both
encode `size_p` explicitly in the storage penalty now.

## ILP baseline (`ILP.py`)

Uses PuLP + CBC to find the provably optimal solution via classical
integer linear programming.  Handles the capacity inequality natively,
no QUBO encoding required.  It's the ground truth used both at runtime
(for optimality gap) and in the test suite (oracle for QUBO ground
states).  Just call `solver.solve()`.

## Simulated solvers

Three QUBO formulations sampled on the CPU via D-Wave's
`PathIntegralAnnealingSampler`.  Full formulation details for each are
in [`simulated_solvers/README.md`](simulated_solvers/README.md).

* **S1** is Paper-1 faithful: binary slack variables convert the
  storage inequality into an equality.  Default in the registry.
* **S2** is Paper-2 faithful: an unbalanced penalty `−λ₁·h + λ₂·h²`
  encodes the inequality directly, with `(λ₁, λ₂)` calibrated per
  instance using `dimod.ExactSolver` (small) or a heuristic (large).
  Default in the registry.
* **S3** layers a domain-wall k-safety chain on top of S2's storage.
  The chain has to be linked back to `A_{p,n}` via `(Σ A − Σ W)²`,
  which reintroduces `O(N²)` couplings — so S3 does *not* deliver the
  coupling reduction it was originally advertised to.  Kept in the
  repo as a documented negative result, but **excluded from the
  default registry**.  Opt in via `SOLVER_REGISTRY_SIM_WITH_S3`.

## Hardware solvers

QPU versions of S1–S3.  Each inherits `build_bqm()` from its simulated
parent unchanged and only overrides `solve()` to use
`EmbeddingComposite(DWaveSampler())`.  The BQM is identical to the
simulated version, so simulated and hardware results for the same
formulation are directly comparable.  Hardware solvers additionally
expose `hardware_summary()` for QPU timing, physical qubit count, and
chain-break statistics.

The hardware path has never been committed to `result_bank/` in this
repo — the default-registry-on-hardware run includes ILP + S1 + S2; S3
on hardware is opt-in via `include_s3=True`.

For full details on hardware parameters
(`annealing_time`, `chain_strength`, `solver_name`), see
[`quantum_hardware_solvers/README.md`](quantum_hardware_solvers/README.md).
