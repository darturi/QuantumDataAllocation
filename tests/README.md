# Tests

`pytest` suite that anchors the correctness claims of every solver.
This directory is the single most important guardrail in the repo —
the bugs documented in `CRITICAL_REVIEW.md` were possible because none
of this existed before.

## Run them

```
pip install -r requirements.txt    # includes pytest + hypothesis
python -m pytest tests/ -v
```

Expected final line: `28 passed, 2 skipped`.  The two skips are
explicit S3 infeasibility on tight cases — see
`solvers/simulated_solvers/README.md` §S3 and `test_oracle.py`.

## Files

| File | What it covers |
|------|-----------------|
| `conftest.py` | Hand-curated problem fixtures (`case_n3p3_loose`, `case_n3p4_tight`, `case_n3p3_non_mersenne_unit`, `case_n2p3_non_mersenne_arbitrary`).  Small enough for brute-force + `dimod.ExactSolver`. |
| `test_oracle.py` | The headline tests.  For each solver, builds the BQM and finds its **exact** ground state with `dimod.ExactSolver`, then asserts that the recovered assignment matches the brute-force optimum of the *original* problem. |
| `test_cost_and_validity.py` | Property tests for `calculate_solution_cost` / `is_valid_solution` against an independent re-implementation of Paper 1's definitions. |
| `test_generators.py` | Generator feasibility, JSON round-trip, and the "no Mersenne rounding" regression test. |
| `test_harness.py` | Phase-5 result-schema smoke test (asserts every result entry has `k_safety_violations`, `capacity_overruns`, absolute/relative optimality gap, and — for S2/S3 — calibrated `lambda_1`/`lambda_2`). |
| `test_json_roundtrip.py` | Test-case JSON round-trip. |

## Why ExactSolver, not the annealer

The oracle tests use `dimod.ExactSolver`, which enumerates every state
of the BQM, **not** `PathIntegralAnnealingSampler`.  That's deliberate:

* If the QUBO's ground state has cost ≠ true optimum, the *encoding*
  is wrong.  No amount of sweeps will save you.
* `ExactSolver` is deterministic, so the tests are not flaky.
* It's only viable on small instances (≤ ~20 binary variables) — which
  is exactly what the fixtures provide.

The original S2 implementation had its QUBO ground state at cost 28
when the true optimum was 11.  An ExactSolver oracle finds that
discrepancy in milliseconds; running the annealer for a million sweeps
would not.

## What a failure means

When `test_s1_ground_state_matches_brute_force` or
`test_s2_ground_state_matches_brute_force` fails on a small case, the
diagnosis is unambiguous: the solver's `build_bqm()` is producing a
QUBO whose lowest-energy state does not encode the original problem.
Don't chase sampler hyper-parameters; fix the BQM.

For S3 the contract is softer: `test_s3_ground_state_is_near_optimum`
either passes strict equality or calls `pytest.skip` with a pointer to
the docstring.  The skip is *not* a regression — it documents a
structural property of the redundant W+A encoding.  If that skip ever
disappears (i.e. someone makes S3 strictly optimal on the tight
cases), that's a real improvement to celebrate.

## Adding a new oracle case

Add a fixture in `conftest.py` (keep `|P| · |N| ≤ ~16` so ExactSolver
remains fast), then parametrise the oracle tests with the new fixture
name.  The minimum useful case-set per solver is one loose, one tight,
and one non-Mersenne capacity.

## Coverage

These tests cover the encoding contracts.  They do **not** cover:

* Long-form benchmark performance (that's `result_bank/`).
* Hardware-specific behaviour (no QPU in CI).
* Notebook content under `result_analysis/`.

The first is intentional — encoding tests are fast and deterministic;
benchmark numbers are slow and noisy.  Keep them separate.
