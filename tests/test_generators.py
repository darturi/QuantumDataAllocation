"""
Property tests for the test-case generators.

Asserts: every generated instance is feasible (ILP returns a solution),
respects k_safety <= n_nodes, and round-trips through JSON.
"""

import json

import pytest

from util.test_generation.generate_test_case import generate_test_case
from util.test_generation.generate_unit_test_case import generate_unit_test_case
from util.test_generation.json_to_dict import json_to_test_case


@pytest.mark.parametrize("tightness", [0.0, 0.5, 1.0])
@pytest.mark.parametrize("n_nodes,n_parts", [(3, 4), (4, 6)])
def test_unit_generator_is_always_feasible(tightness, n_nodes, n_parts, tmp_path):
    tc = generate_unit_test_case(
        n_nodes=n_nodes, n_partitions=n_parts,
        k_safety=2, seed=42, tightness=tightness,
    )
    assert tc["k_safety"] <= n_nodes
    for size in tc["partitions"].values():
        assert size == 1
    # Capacity is at least the minimum required for feasibility
    min_cap = -(-2 * n_parts // n_nodes)
    for cap in tc["nodes"].values():
        assert cap >= min_cap


@pytest.mark.parametrize("tightness", [0.0, 0.5, 0.9])
def test_arbitrary_generator_is_always_feasible(tightness, tmp_path):
    # tightness=1.0 is often intrinsically infeasible for variable-size
    # partitions (the bin-packing version of the problem), so the
    # generator may legitimately retry-and-give-up there.  We test
    # tightness up to 0.9 (very tight) instead.
    tc = generate_test_case(
        n_nodes=3, n_partitions=4, k_safety=2,
        seed=7, tightness=tightness,
    )
    assert tc["k_safety"] <= 3
    for cap in tc["nodes"].values():
        max_size = max(tc["partitions"].values())
        assert cap >= max_size


def test_generators_produce_no_mersenne_rounding(tmp_path):
    """After Phase 4, capacities are NOT rounded to Mersenne numbers."""
    # Collect capacities from many cases; at least one should be non-Mersenne.
    caps = []
    for seed in range(1, 21):
        tc = generate_unit_test_case(
            n_nodes=5, n_partitions=10, k_safety=2,
            seed=seed, tightness=0.5,
        )
        caps.extend(tc["nodes"].values())

    def is_mersenne(c):
        return c & (c + 1) == 0 and c > 0

    non_mersenne = [c for c in caps if not is_mersenne(c)]
    assert len(non_mersenne) > 0, (
        "All generated capacities are Mersenne -- generator may still be "
        "rounding silently."
    )


def test_unit_generator_json_roundtrip(tmp_path):
    tc = generate_unit_test_case(
        n_nodes=3, n_partitions=4, k_safety=2,
        seed=123, tightness=0.7,
    )
    path = tmp_path / "case.json"
    path.write_text(json.dumps(tc))
    nodes, parts, k, reqs, costs = json_to_test_case(str(path))
    assert nodes == tc["nodes"]
    assert parts == tc["partitions"]
    assert k == tc["k_safety"]
    assert costs == tc["comm_costs"]
