"""
Run the arbitrary-partition benchmark experiment.

Discovers test cases from test_bank/arbitrary_partition/, registers the
ILP baseline plus the SQA solvers that handle variable partition sizes,
and writes results to result_bank/.

After the Phase-2 refactor, both S1 (binary slack) and S2 (calibrated
unbalanced penalty) support arbitrary partition sizes -- size_p shows up
in the storage encoding as the coefficient of A_{p,n} rather than as a
unit count.  Both are in the default registry.

S3 (SQA_DW) is deliberately excluded -- see
``run_unit_partition_experiment.py`` for the rationale -- and is
opt-in via ``SOLVER_REGISTRY_SIM_WITH_S3``.
"""

from pathlib import Path

from solvers.ILP import ILPSolver
from solvers.simulated_solvers.SQA import SQASolver
from solvers.simulated_solvers.SQA_SF import SQASlackFreeSolver
from solvers.simulated_solvers.SQA_DW import SQADomainWallSolver
from util.experiment_execution.run_experiment import (
    discover_test_cases,
    run_experiment,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEST_BANK    = PROJECT_ROOT / "test_bank" / "arbitrary_partition"
RESULT_DIR_SIM = PROJECT_ROOT / "result_bank" / "simulated_solver_results"
RESULT_DIR_HW  = PROJECT_ROOT / "result_bank" / "quantum_hardware_results"

SOLVER_REGISTRY_SIM = [
    {"name": "ILP",    "class": ILPSolver,             "type": "ilp"},
    {"name": "SQA",    "class": SQASolver,             "type": "sqa"},
    {"name": "SQA_SF", "class": SQASlackFreeSolver,    "type": "sqa"},
]

# Opt-in registry that includes S3.  See SQA_DW.py for the documented
# rationale; this exists so the negative finding remains reproducible.
SOLVER_REGISTRY_SIM_WITH_S3 = SOLVER_REGISTRY_SIM + [
    {"name": "SQA_DW", "class": SQADomainWallSolver, "type": "sqa"},
]


def _get_hw_registry(include_s3=False):
    """Hardware solver registry.

    Deferred to avoid ImportError when dwave-system is not installed.
    """
    from solvers.quantum_hardware_solvers.SQA_HW import SQAHardwareSolver
    from solvers.quantum_hardware_solvers.SQA_SF_HW import SQASFHardwareSolver

    registry = [
        {"name": "SQA_HW",    "class": SQAHardwareSolver,    "type": "qpu"},
        {"name": "SQA_SF_HW", "class": SQASFHardwareSolver,  "type": "qpu"},
    ]
    if include_s3:
        from solvers.quantum_hardware_solvers.SQA_DW_HW import SQADWHardwareSolver
        registry.append(
            {"name": "SQA_DW_HW", "class": SQADWHardwareSolver, "type": "qpu"},
        )
    return registry


def run_arbitrary_experiment(
    tier=None,
    node_counts=None,
    partition_counts=None,
    max_cases=None,
    num_reads=1000,
    num_sweeps=1000,
    beta_range=None,
    hardware=False,
    annealing_time=20,
    chain_strength=None,
    extra_registry=None,
    include_s3=False,
):
    """Run the arbitrary-partition experiment.

    See ``run_unit_partition_experiment.run_unit_experiment`` for argument
    semantics.  The two runners share a structure; the only difference is
    which test-bank subdirectory they read from.
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

    if hardware:
        registry = [SOLVER_REGISTRY_SIM[0]] + _get_hw_registry(include_s3=include_s3)
        result_dir = RESULT_DIR_HW
        prefix = "ArbitraryExperiment_HW"
        note = "Arbitrary-partition benchmark (D-Wave QPU): variable partition sizes."
    else:
        registry = extra_registry if extra_registry is not None else SOLVER_REGISTRY_SIM
        result_dir = RESULT_DIR_SIM
        prefix = "ArbitraryExperiment"
        note = "Arbitrary-partition benchmark: variable partition sizes."

    print(f"Found {len(paths)} arbitrary-partition test cases.")

    return run_experiment(
        test_case_paths=paths,
        solver_registry=registry,
        output_dir=result_dir,
        file_prefix=prefix,
        num_reads=num_reads,
        num_sweeps=num_sweeps,
        beta_range=beta_range,
        annealing_time=annealing_time,
        chain_strength=chain_strength,
        note=note,
    )


if __name__ == "__main__":
    # See run_unit_partition_experiment.py for the rationale behind
    # these sampler defaults.  Bump for tier 2 or the full grid.
    run_arbitrary_experiment(
        tier="tier1",
        num_reads=200,
        num_sweeps=500,
    )
