"""
Shared pytest fixtures and helpers.

A "case" is a minimal-but-non-trivial problem instance:
 - small enough for brute_force_solve and dimod.ExactSolver,
 - rich enough that the optimal placement is non-uniform across nodes,
 - covering both Mersenne and non-Mersenne capacities.
"""

import pytest


def _tc(nodes, partitions, k_safety, requests, comm_costs):
    """Build a test-case tuple from named fields."""
    return nodes, partitions, k_safety, requests, comm_costs


# ----- Hand-curated cases --------------------------------------------------

@pytest.fixture
def case_n3p3_loose():
    """3 nodes, 3 unit partitions, capacity 3 (non-binding)."""
    return _tc(
        nodes={"n1": 3, "n2": 3, "n3": 3},
        partitions={"p1": 1, "p2": 1, "p3": 1},
        k_safety=2,
        requests={
            ("p1", "n1"): 9, ("p1", "n2"): 1, ("p1", "n3"): 2,
            ("p2", "n1"): 4, ("p2", "n2"): 0, ("p2", "n3"): 9,
            ("p3", "n1"): 9, ("p3", "n2"): 1, ("p3", "n3"): 2,
        },
        comm_costs={"p1": 6, "p2": 3, "p3": 5},
    )


@pytest.fixture
def case_n3p4_tight():
    """3 nodes, 4 unit partitions, capacity 3 (tight: k*|P|/|N| = 8/3 ≈ 2.67)."""
    return _tc(
        nodes={"n1": 3, "n2": 3, "n3": 3},
        partitions={"p1": 1, "p2": 1, "p3": 1, "p4": 1},
        k_safety=2,
        requests={
            ("p1", "n1"): 5, ("p1", "n2"): 0, ("p1", "n3"): 0,
            ("p2", "n1"): 0, ("p2", "n2"): 7, ("p2", "n3"): 0,
            ("p3", "n1"): 0, ("p3", "n2"): 0, ("p3", "n3"): 9,
            ("p4", "n1"): 3, ("p4", "n2"): 3, ("p4", "n3"): 3,
        },
        comm_costs={"p1": 2, "p2": 4, "p3": 6, "p4": 1},
    )


@pytest.fixture
def case_n2p3_non_mersenne_arbitrary():
    """2 nodes, capacity 5 (NOT Mersenne), variable-size partitions."""
    return _tc(
        nodes={"n1": 5, "n2": 5},
        partitions={"p1": 2, "p2": 3, "p3": 1},
        k_safety=1,
        requests={
            ("p1", "n1"): 10, ("p1", "n2"): 1,
            ("p2", "n1"): 0,  ("p2", "n2"): 8,
            ("p3", "n1"): 4,  ("p3", "n2"): 4,
        },
        comm_costs={"p1": 3, "p2": 5, "p3": 2},
    )


@pytest.fixture
def case_n3p3_non_mersenne_unit():
    """3 nodes, capacity 2 (NOT Mersenne) — exposes S1's chunk-decomposition bug."""
    return _tc(
        nodes={"n1": 2, "n2": 2, "n3": 2},
        partitions={"p1": 1, "p2": 1, "p3": 1},
        k_safety=2,
        requests={
            ("p1", "n1"): 8, ("p1", "n2"): 1, ("p1", "n3"): 0,
            ("p2", "n1"): 0, ("p2", "n2"): 9, ("p2", "n3"): 0,
            ("p3", "n1"): 2, ("p3", "n2"): 2, ("p3", "n3"): 5,
        },
        comm_costs={"p1": 4, "p2": 5, "p3": 3},
    )


# A registry used by parametrised tests below
ALL_UNIT_CASES = [
    "case_n3p3_loose",
    "case_n3p4_tight",
    "case_n3p3_non_mersenne_unit",
]
