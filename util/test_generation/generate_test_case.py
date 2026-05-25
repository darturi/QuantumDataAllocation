"""
Generate random feasible test cases with arbitrary (non-unit) partition sizes.

After the S1 baseline fix (Phase 1), capacities are NOT rounded to
Mersenne numbers any more.  Real-world capacities are arbitrary integers
and the QUBO encoding now handles them exactly.

Test cases are also stratified by *storage-constraint tightness*:

    tightness = 1.0  -> capacity is the minimum required for feasibility;
                       every storage constraint binds at the optimum.
    tightness = 0.0  -> capacity is double the minimum; storage rarely binds.

This lets downstream experiments isolate the effect of the storage
encoding from other variables.
"""

import json
import random
from pathlib import Path

from solvers.ILP import ILPSolver


def _draw_capacity(min_cap, tightness, rng):
    """
    Return an integer capacity sampled to satisfy the requested tightness.

    tightness=1.0 -> capacity == min_cap exactly.
    tightness=0.0 -> capacity in [1.5*min_cap, 2.0*min_cap].
    """
    if not 0.0 <= tightness <= 1.0:
        raise ValueError(f"tightness must be in [0, 1], got {tightness}")
    slack_factor = 1.0 + (1.0 - tightness)        # 1.0..2.0
    upper = max(min_cap, int(round(min_cap * slack_factor)))
    return rng.randint(min_cap, upper)


def generate_test_case(
    n_nodes,
    n_partitions,
    k_safety=2,
    seed=None,
    size_range=(5, 20),
    req_range=(0, 10),
    cost_range=(1, 10),
    tightness=0.5,
    feasibility_retries=20,
):
    """
    Generate a random, feasible test case with variable partition sizes.

    Args:
        n_nodes:               number of storage nodes
        n_partitions:          number of data partitions
        k_safety:              replication factor
        seed:                  random seed (None = non-deterministic)
        size_range:            (min, max) partition sizes (inclusive)
        req_range:             (min, max) per-(p, n) request frequencies
        cost_range:            (min, max) per-partition communication costs
        tightness:             0.0 (loose) .. 1.0 (tight) -- see module docstring
        feasibility_retries:   max attempts before raising RuntimeError

    Returns:
        dict in standard test-case JSON format.  Capacities are kept as
        whatever the random draw produced -- *no Mersenne rounding*.

    Raises:
        ValueError: k_safety > n_nodes.
        RuntimeError: could not produce a feasible instance in the retry budget.
    """
    if k_safety > n_nodes:
        raise ValueError(f"k_safety ({k_safety}) cannot exceed n_nodes ({n_nodes})")

    base_rng = random.Random(seed)

    for attempt in range(feasibility_retries):
        rng = random.Random(base_rng.random())

        sizes = [rng.randint(*size_range) for _ in range(n_partitions)]
        max_size = max(sizes)
        total_size = sum(sizes)

        # Minimum per-node capacity so total capacity >= k * total_size
        # (necessary feasibility condition for a uniform draw).
        min_cap = -(-k_safety * total_size // n_nodes)
        min_cap = max(min_cap, max_size)   # each node must hold the largest partition

        node_caps = [_draw_capacity(min_cap, tightness, rng) for _ in range(n_nodes)]

        requests = {
            f"(p{pi}, n{ni})": rng.randint(*req_range)
            for pi in range(1, n_partitions + 1)
            for ni in range(1, n_nodes + 1)
        }

        comm_costs = {
            f"p{pi}": rng.randint(*cost_range)
            for pi in range(1, n_partitions + 1)
        }

        tc = {
            "nodes":      {f"n{ni}": cap for ni, cap in enumerate(node_caps, 1)},
            "partitions": {f"p{pi}": sz for pi, sz in enumerate(sizes, 1)},
            "k_safety":   k_safety,
            "requests":   requests,
            "comm_costs": comm_costs,
            "tightness":  round(tightness, 3),
        }

        # Verify the instance is actually feasible with an ILP probe.
        if _is_feasible(tc):
            return tc

    raise RuntimeError(
        f"Could not generate a feasible instance after {feasibility_retries} "
        f"attempts (n_nodes={n_nodes}, n_partitions={n_partitions}, "
        f"k_safety={k_safety}, tightness={tightness})."
    )


def _is_feasible(tc):
    """Run an ILP feasibility probe (no objective) on the given test case."""
    requests = {
        tuple(k[1:-1].split(", ")): v
        for k, v in tc["requests"].items()
    }
    solver = ILPSolver(
        tc["nodes"], tc["partitions"], tc["k_safety"],
        requests, tc["comm_costs"],
    )
    _, result = solver.solve()
    return result is not None


def generate_batch(
    n_nodes,
    n_partitions,
    count,
    output_dir,
    k_safety=2,
    base_seed=None,
    **kwargs,
):
    """Generate `count` test cases and save them as JSON files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for i in range(1, count + 1):
        seed = None if base_seed is None else base_seed + i
        tc = generate_test_case(n_nodes, n_partitions, k_safety=k_safety, seed=seed, **kwargs)
        fpath = output_dir / f"n-{n_nodes}_p-{n_partitions}_{i}.json"
        fpath.write_text(json.dumps(tc, indent=4))
        paths.append(fpath)

    return paths
