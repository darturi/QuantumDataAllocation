"""
Run the arbitrary-partition benchmark experiment.

Discovers test cases from test_bank/arbitrary_partition/, registers the
ILP baseline plus the base SQA solver (which supports variable partition
sizes), and writes results to result_bank/simulated_solver_results/.

The domain-wall and slack-free solvers are excluded here because they
require unit partition sizes.

Usage:
    python -m util.experiment_execution.run_arbitrary_partition_experiment

Options can be adjusted in the __main__ block or by importing and
calling run_arbitrary_experiment() directly.
"""

from pathlib import Path

from solvers.ILP import ILPSolver
from solvers.simulated_solvers.SQA import SQASolver
from util.experiment_execution.run_experiment import (
    discover_test_cases,
    run_experiment,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEST_BANK    = PROJECT_ROOT / "test_bank" / "arbitrary_partition"
RESULT_DIR   = PROJECT_ROOT / "result_bank" / "simulated_solver_results"

SOLVER_REGISTRY = [
    {"name": "ILP", "class": ILPSolver, "type": "ilp"},
    {"name": "SQA", "class": SQASolver,  "type": "sqa"},
]


def run_arbitrary_experiment(
    tier=None,
    node_counts=None,
    partition_counts=None,
    max_cases=None,
    num_reads=1000,
    num_sweeps=1000,
    beta_range=None,
):
    """
    Run the arbitrary-partition experiment.

    Args:
        tier:             "tier1", "tier2", or None (both tiers).
        node_counts:      optional filter, e.g. [2, 3, 5].
        partition_counts: optional filter, e.g. [3, 8, 18].
        max_cases:        cap total number of test cases (useful for quick checks).
        num_reads:        SQA num_reads.
        num_sweeps:       SQA num_sweeps.
        beta_range:       SQA beta_range.

    Returns:
        Path to the results JSON file.
    """
    paths = discover_test_cases(
        TEST_BANK,
        tier=tier,
        node_counts=node_counts,
        partition_counts=partition_counts,
        max_cases=max_cases,
    )

    if not paths:
        print("No test cases found. Run populate_test_bank.py first.")
        return None

    print(f"Found {len(paths)} arbitrary-partition test cases.")

    return run_experiment(
        test_case_paths=paths,
        solver_registry=SOLVER_REGISTRY,
        output_dir=RESULT_DIR,
        file_prefix="ArbitraryExperiment",
        num_reads=num_reads,
        num_sweeps=num_sweeps,
        beta_range=beta_range,
        note="Arbitrary-partition benchmark: variable partition sizes.",
    )


if __name__ == "__main__":
    run_arbitrary_experiment(
        tier="tier1",
        num_reads=1000,
        num_sweeps=1000,
    )
