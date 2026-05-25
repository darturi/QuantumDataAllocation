# Simulated Solvers

This directory contains three Simulated Quantum Annealing (SQA) solvers
for the data-allocation optimisation problem.  Each one constructs a
Binary Quadratic Model (BQM) encoding the same objective and constraints
but using a different QUBO formulation, then samples it on the CPU via
`PathIntegralAnnealingSampler` (Path Integral Monte Carlo).

All three subclass `SolverBase` and expose `build_bqm()` (build the BQM
without sampling) and `solve()` (build then sample).

## Files

| File | Class | Label | In default registry? |
|------|-------|-------|----------------------|
| `SQA.py` | `SQASolver` | S1 | yes |
| `SQA_SF.py` | `SQASlackFreeSolver` | S2 | yes |
| `SQA_DW.py` | `SQADomainWallSolver` | S3 | **no** (opt-in) |

The default benchmark registries are defined in
`util/experiment_execution/run_unit_partition_experiment.py` and
`run_arbitrary_partition_experiment.py`.  Both omit S3 — see the
"S3" section below for why.

## Common constructor arguments

| Parameter | Type | Description |
|-----------|------|-------------|
| `nodes` | `dict[str, int]` | Node capacities, e.g. `{"n1": 7, "n2": 10}` |
| `partitions` | `dict[str, int]` | Partition sizes |
| `k_safety` | `int` | Replication factor |
| `requests` | `dict[tuple, int]` | Request frequencies keyed by `(p, n)` |
| `comm_costs` | `dict[str, int]` | Per-partition communication cost |

S2 and S3 additionally accept `lambda_1` and `lambda_2` (positive floats,
or both `None` for auto-calibration — see below).

After `solve()`, `self.result` is a `dimod.SampleView` (lowest-energy
sample) and `self.time_taken` is wall-clock time in milliseconds.

## `solve()` parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `num_reads` | 1000 | Independent annealing runs per call |
| `num_sweeps` | 1000 | Monte Carlo sweeps per read |
| `beta_range` | `None` | Inverse temperature schedule; `None` = sampler default |

---

## S1 — `SQASolver` (`SQA.py`)

Faithful Paper-1 implementation: the storage inequality
`Σ A_{p,n} · size_p ≤ C_n` is encoded as an equality
`Σ A_{p,n} · size_p = Σ chunk_i · S_{n,i}` using binary slack variables
`S_{n,i}`.

### Chunk decomposition (no Mersenne restriction)

The previous version of this file required `C_n` to be a Mersenne
number (`2^k − 1`).  That restriction came from a buggy chunk
decomposition.  After the Phase-1 fix:

```
chunks = [1, 2, 4, …, 2^J, residual]
where J = largest j with 2^(j+1) − 1 ≤ C_n
      residual = C_n − (2^(J+1) − 1)
```

The chunks sum to exactly `C_n`, so the slack variables can represent
every integer in `[0, C_n]`.  Examples:

* `C = 7`   → `[1, 2, 4]`         (Mersenne; no residual)
* `C = 10`  → `[1, 2, 4, 3]`      (residual of 3 after `1+2+4=7`)
* `C = 100` → `[1, 2, 4, 8, 16, 32, 37]`  (residual 37 after `1+…+32=63`)

A run-time `assert sum(chunks) == capacity` is included for safety.

### Constraint encoding

* **k-safety (Q_R):**
  `(Σ_n A_{p,n} − k)²` enforced via
  `bqm.add_linear_equality_constraint(..., lagrange=h)` where
  `h = Σ r_{p,n} · c_p + 1` (Paper 1, Eq. 9).
* **Storage (Q_S):**
  `Σ A_{p,n} · size_p = Σ chunk · S_{n,·}` enforced as equality
  with the same `h`.
* **Cost (Q_C):**
  Linear bias `−r_{p,n} · c_p` on each `A_{p,n}`.

### Variable count

`P · N` assignment variables + `Σ_n len(chunks(C_n))` slack variables.
Slack count is `≈ ⌈log₂(C_n + 1)⌉` per node.

### Capacity & size support

* Capacities: **any** non-negative integer.
* Partition sizes: **any** non-negative integer.

---

## S2 — `SQASlackFreeSolver` (`SQA_SF.py`)

Faithful Paper-2 implementation of unbalanced penalisation.  For each
node `n` the slack `h_n = C_n − Σ_p A_{p,n} · size_p` is penalised by

```
ζ_n  =  −λ₁ · h_n  +  λ₂ · h_n²
```

This reverts to zero exactly at `h_n = 0`, rewards moderate slack, and
grows quadratically when `h_n < 0` (infeasible).

### Why `(λ₁, λ₂)` are calibrated, not fixed

Paper 2 (Sec. III) is explicit that `λ₁` and `λ₂` must be tuned per
instance.  An earlier version of this file used `λ₁ = λ₂ = h`, which
collapses ζ to the algebraically-equivalent but operationally-different
`(x − C)(x − C + 1)` — a non-negative function with minimum at
`x ∈ {C − 1, C}` that *penalises feasible slack* instead of rewarding
it.  That choice produced QUBOs whose ground states had cost up to 2.5×
the true optimum (see `CRITICAL_REVIEW.md` §1.2).

The current implementation:

* Refuses one-of-two lambdas: pass both, or pass neither and let the
  solver calibrate.
* For instances small enough to enumerate (`|P| · |N| ≤ 16`),
  `calibrate_lambdas` brute-forces the true optimum, builds the BQM
  for each `(λ₁, λ₂)` in a multiplicative grid, and picks the pair
  whose `dimod.ExactSolver` ground state matches (or comes closest to)
  the true optimum.
* For larger instances, falls back to a heuristic
  `λ₁ = 2 · max(C) · λ₂`, `λ₁ + λ₂ > h`.

The calibration accepts a custom `bqm_builder` so S3 can reuse the
search against its own (different) BQM.

### Constraint encoding

* **k-safety (Q_R):** `(Σ_n A_{p,n} − k)²`, weight
  `h_k = h · max(C_n)` to keep k-safety dominant over the storage
  penalty regardless of the calibrated `(λ₁, λ₂)`.
* **Storage (Q_S):** unbalanced penalty above, expanded for binary
  variables:
  ```
  linear[A_{p,n}]      = λ₁ · size_p + λ₂ · (size_p² − 2·C·size_p)
  quadratic[A_{p,n}, A_{p',n}] = 2 · λ₂ · size_p · size_p'
  ```
* **Cost (Q_C):** identical to S1.

### Variable count

`P · N` assignment variables only — no slack.

### Capacity & size support

* Capacities: **any** non-negative integer.
* Partition sizes: **any** non-negative integer.

### Recorded calibration

Both `lambda_1` and `lambda_2` are stored on the solver instance and
copied into the result JSON by the Phase-5 harness, so every result is
reproducible.

---

## S3 — `SQADomainWallSolver` (`SQA_DW.py`)

Domain-wall k-safety encoding (Chancellor 2019) layered on top of the
S2 calibrated unbalanced storage.

### Why S3 is opt-in, not in the default registry

The original docstring claimed an `O(N)` reduction in k-safety
couplings.  On the data-allocation problem that reduction does not
materialise: the domain-wall chain operates on auxiliary `W_{p,j}`
variables and must be linked back to the assignment variables `A_{p,n}`
via `(Σ_n A_{p,n} − Σ_j W_{p,j})² = 0`, which by itself introduces
`O(N²)` couplings.  Empirically S3 has *more* quadratic terms than S2
and sometimes more than S1, plus `P · N` extra binary variables.

S3 is kept in the repo for two reasons:

1. It's a documented negative result.  The encoding works correctly on
   loose instances (see oracle test) — it just doesn't win.  Future
   contributors who consider trying domain-wall here can verify the
   negative finding themselves.
2. The `test_s3_*` regression tests serve as a tripwire: if anyone
   finds a way to avoid the linking penalty, the tests will start
   passing strict equality and that change will be visible.

To use it deliberately:

```python
from util.experiment_execution.run_unit_partition_experiment import (
    SOLVER_REGISTRY_SIM_WITH_S3, run_unit_experiment,
)
run_unit_experiment(extra_registry=SOLVER_REGISTRY_SIM_WITH_S3)
```

### Constraint encoding

* **k-safety (Q_R)** — domain-wall chain:
  * Chain monotonicity (per partition):
    penalty `h_chain · (W_{j+1} − W_j · W_{j+1})` for each `j`.
  * Count enforcement: linear `−h_chain` on `W_k` and `+h_chain` on
    `W_{k+1}` to force `W_k = 1`, `W_{k+1} = 0`.
  * Linking: `(Σ_n A_{p,n} − Σ_j W_{p,j})² = 0` with weight
    `h_chain = h · max(C_n)`.  **This is the `O(N²)` term.**
* **Storage (Q_S):** identical to S2 (calibrated unbalanced penalty).
  Lambdas are calibrated against S3's own BQM via the `bqm_builder`
  hook on `calibrate_lambdas`, since the extra W variables change the
  energy landscape.
* **Cost (Q_C):** identical to S1 and S2.

### Variable count

`P · N` assignment variables + `P · N` wall variables = `2 · P · N`.

### Capacity & size support

* Capacities: **any** non-negative integer.
* Partition sizes: **any** non-negative integer (the unit-partition
  restriction in the old implementation has been lifted — the
  calibrated unbalanced storage handles `size_p` the same way S2 does).

### Known limitation

For tight instances (capacity ≈ `k · |P| / |N|`), no `(λ₁, λ₂)` in the
calibration grid produces a feasible ground state — the extra W
variables widen the search space enough that the unbalanced reward
swamps the chain reward.  The oracle tests handle this by calling
`pytest.skip` with a pointer to this README.  This is consistent with
Paper 2's own caveat that the unbalanced approach guarantees only
near-optimum, not strict-optimum, ground states.

---

## Tests

Every solver has at least one `dimod.ExactSolver` oracle test in
`tests/test_oracle.py`.  The test:

1. Builds the BQM.
2. Calls `dimod.ExactSolver` (exhaustive enumeration — *not* annealing).
3. Projects the lowest-energy sample onto the `A_{p,n}` variables.
4. Asserts the resulting assignment minimises the *original* problem's
   cost (via `util.brute_force.brute_force_solve`).

S1 and S2 require strict equality on all curated cases.  S3 requires
strict equality on the loose case and either strict equality or
`pytest.skip` on the tight cases (its documented limit).

## References

- Trummer, I. (2025). "Leveraging Quantum Computing for Optimal Data
  Allocation in Distributed Systems."  Q-Data '25.
- Montañez-Barrera, J. A., et al. (2022). "Unbalanced penalization: A
  new approach to encode inequality constraints for quantum
  optimization algorithms."  arXiv:2211.13914.
- Chancellor, N. (2019). "Domain wall encoding of discrete variables
  for quantum annealing and QAOA."  arXiv:1903.05068.
