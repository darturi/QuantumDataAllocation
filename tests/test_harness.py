"""
Smoke test for the experiment harness.

Builds 2 test cases, runs ILP + S1 + S2 on each, and asserts the result
file has the expected structure (violation counts, dual gaps, lambdas).
"""

import json
from pathlib import Path

import pytest

from solvers.ILP import ILPSolver
from solvers.simulated_solvers.SQA import SQASolver
from solvers.simulated_solvers.SQA_SF import SQASlackFreeSolver
from util.experiment_execution.run_experiment import run_experiment
from util.test_generation.generate_unit_test_case import generate_unit_test_case


def test_harness_produces_phase5_result_fields(tmp_path):
    tcs = []
    tightnesses = [0.3, 0.9]
    for i, tightness in enumerate(tightnesses):
        tc = generate_unit_test_case(
            n_nodes=3, n_partitions=4, k_safety=2,
            seed=100 + i, tightness=tightness,
        )
        path = tmp_path / f"tc{i}.json"
        path.write_text(json.dumps(tc))
        tcs.append(path)

    registry = [
        {"name": "ILP", "class": ILPSolver, "type": "ilp"},
        {"name": "SQA", "class": SQASolver, "type": "sqa"},
        {"name": "SQA_SF", "class": SQASlackFreeSolver, "type": "sqa"},
    ]

    out = run_experiment(
        test_case_paths=tcs,
        solver_registry=registry,
        output_dir=tmp_path,
        file_prefix="Smoke",
        num_reads=50,
        num_sweeps=50,
        verbose=False,
    )
    data = json.loads(Path(out).read_text())

    # Metadata version stamp
    assert data["metadata"]["harness_version"] == "phase5"

    # Each result has the new fields
    observed_tightnesses = []
    for key, entry in data["results"].items():
        for name in ["ILP", "SQA", "SQA_SF"]:
            r = entry["solvers"][name]
            assert "k_safety_violations" in r
            assert "capacity_overruns" in r
            assert "optimality_gap_absolute" in r
            assert "optimality_gap_relative" in r
            assert "wall_time_ms" in r
        # S2 carries calibrated lambdas
        assert entry["solvers"]["SQA_SF"]["lambda_1"] is not None
        assert entry["solvers"]["SQA_SF"]["lambda_2"] is not None
        # Tightness is surfaced from the test-case JSON
        assert "tc_tightness" in entry, (
            "Expected 'tc_tightness' on each result entry so downstream "
            "analysis can stratify by storage-constraint tightness."
        )
        observed_tightnesses.append(entry["tc_tightness"])

    # Both tightness levels propagated through correctly
    assert sorted(observed_tightnesses) == sorted([0.3, 0.9])
