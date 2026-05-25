"""
Property tests for calculate_solution_cost and is_valid_solution.

These are written against the *definitions* from Paper 1, independent of
the QUBO formulation.  Any solver result must round-trip cleanly.
"""

from hypothesis import HealthCheck, given, settings, strategies as st

from util.brute_force import brute_force_solve
from util.calculate_solution_cost import (
    calculate_solution_cost,
    is_valid_solution,
)


def _reference_cost(nodes, partitions, k_safety, requests, comm_costs, assignment):
    """Independent re-implementation of Paper 1's cost formula (Eq. 5)."""
    total = 0
    for p in partitions:
        for n in nodes:
            r = requests.get((p, n), 0)
            a = assignment.get(f"A_{p}_{n}", 0)
            total += r * comm_costs[p] * (1 - a)
    return total


def _reference_valid(nodes, partitions, k_safety, assignment):
    """Independent re-implementation of Paper 1's constraints."""
    for p in partitions:
        cnt = sum(assignment.get(f"A_{p}_{n}", 0) for n in nodes)
        if cnt != k_safety:
            return False
    for n, cap in nodes.items():
        load = sum(
            assignment.get(f"A_{p}_{n}", 0) * partitions[p] for p in partitions
        )
        if load > cap:
            return False
    return True


def test_cost_matches_reference_on_curated_case(case_n3p3_loose):
    nodes, partitions, k_safety, requests, comm_costs = case_n3p3_loose
    bf_cost, bf_assign = brute_force_solve(
        nodes, partitions, k_safety, requests, comm_costs
    )
    cost = calculate_solution_cost(
        nodes, partitions, k_safety, requests, comm_costs, bf_assign
    )
    ref = _reference_cost(
        nodes, partitions, k_safety, requests, comm_costs, bf_assign
    )
    assert cost == ref == bf_cost


@given(
    bits=st.lists(st.integers(0, 1), min_size=9, max_size=9),
)
@settings(max_examples=64, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_validity_matches_reference_under_random_assignments(case_n3p3_loose_factory, bits):
    """For 3x3 random assignments, validity check agrees with reference."""
    tc = case_n3p3_loose_factory()
    nodes, partitions, k_safety, requests, comm_costs = tc

    parts = list(partitions.keys())
    ns = list(nodes.keys())
    assignment = {
        f"A_{p}_{n}": bits[i * 3 + j]
        for i, p in enumerate(parts) for j, n in enumerate(ns)
    }

    assert (
        is_valid_solution(
            nodes, partitions, k_safety, requests, comm_costs, assignment
        )
        == _reference_valid(nodes, partitions, k_safety, assignment)
    )


import pytest


@pytest.fixture
def case_n3p3_loose_factory(case_n3p3_loose):
    """Allow hypothesis to re-draw the same case (factory fixture)."""
    def _make():
        return case_n3p3_loose
    return _make
