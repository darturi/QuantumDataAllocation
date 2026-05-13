import json
import random
from pathlib import Path


def _round_up_to_mersenne(c: int) -> int:
    """Return the smallest Mersenne number (2^k - 1) >= c."""
    k = c.bit_length()
    return (1 << k) - 1


def generate_unit_test_case(
    n_nodes,
    n_partitions,
    k_safety=2,
    seed=None,
    req_range=(0, 10),
    cost_range=(1, 10),
    capacity_factor=1.3,
):
    """
    Generate a random, feasible test case with **all partition sizes = 1**.

    Capacities represent the maximum number of partitions a node can hold
    (not bytes).  Capacities are always Mersenne numbers (2^k - 1) so that
    all four solvers (S0–S3) work with identical problem inputs.

    Both ``nodes`` and ``nodes_raw`` are stored for backward compatibility
    but contain the same Mersenne-rounded values.

    Args:
        n_nodes:          number of storage nodes
        n_partitions:     number of data partitions
        k_safety:         replication factor (each partition stored on exactly k nodes)
        seed:             random seed for reproducibility (None = non-deterministic)
        req_range:        (min, max) for per-(partition, node) request frequencies
        cost_range:       (min, max) for per-partition communication costs
        capacity_factor:  random multiplier applied to the minimum node capacity.
                          Must be >= 1.0.  Lower values (e.g. 1.1-1.3) produce
                          tighter, harder problems where the storage constraint
                          is more likely to bind.

    Returns:
        dict in the standard test case JSON format.  ``nodes`` and ``nodes_raw``
        contain identical Mersenne-number capacities.

    Raises:
        ValueError: if k_safety > n_nodes or capacity_factor < 1.0.
    """
    if k_safety > n_nodes:
        raise ValueError(f"k_safety ({k_safety}) cannot exceed n_nodes ({n_nodes})")
    if capacity_factor < 1.0:
        raise ValueError(f"capacity_factor must be >= 1.0, got {capacity_factor}")

    rng = random.Random(seed)

    # 1. Partition sizes — all 1
    sizes = [1] * n_partitions

    # 2. Node capacities (measured in partition count)
    # Minimum per-node capacity so total capacity >= k * n_partitions (feasibility).
    min_cap = -(-k_safety * n_partitions // n_nodes)   # ceiling division

    # Each node must hold at least 1 partition.
    min_cap = max(min_cap, 1)

    caps = []
    for _ in range(n_nodes):
        raw_cap = int(min_cap * rng.uniform(1.0, capacity_factor))
        raw_cap = max(raw_cap, min_cap)
        # Round up to Mersenne so all solvers see the same capacity.
        caps.append(_round_up_to_mersenne(raw_cap))

    # 3. Request frequencies — one entry per (partition, node) pair
    requests = {
        f'(p{pi}, n{ni})': rng.randint(*req_range)
        for pi in range(1, n_partitions + 1)
        for ni in range(1, n_nodes + 1)
    }

    # 4. Communication costs — one per partition
    comm_costs = {
        f'p{pi}': rng.randint(*cost_range)
        for pi in range(1, n_partitions + 1)
    }

    return {
        "nodes":      {f'n{ni}': cap for ni, cap in enumerate(caps, 1)},
        "nodes_raw":  {f'n{ni}': cap for ni, cap in enumerate(caps, 1)},
        "partitions": {f'p{pi}': sz  for pi, sz  in enumerate(sizes, 1)},
        "k_safety":   k_safety,
        "requests":   requests,
        "comm_costs": comm_costs,
    }


def generate_unit_batch(
    n_nodes,
    n_partitions,
    count,
    output_dir,
    k_safety=2,
    base_seed=None,
    **kwargs,
):
    """
    Generate ``count`` unit-partition test cases and save them as JSON files.

    Files are named ``n-{n_nodes}_p-{n_partitions}_{i}.json`` and written to
    *output_dir* (created if it does not exist).

    Args:
        n_nodes:      number of storage nodes
        n_partitions: number of data partitions
        count:        number of test cases to generate
        output_dir:   destination directory (str or Path)
        k_safety:     replication factor
        base_seed:    if provided, test case i uses seed base_seed + i
        **kwargs:     forwarded to generate_unit_test_case

    Returns:
        list[Path]: paths of the written files, in order.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for i in range(1, count + 1):
        seed = None if base_seed is None else base_seed + i
        tc = generate_unit_test_case(
            n_nodes, n_partitions, k_safety=k_safety, seed=seed, **kwargs
        )
        fpath = output_dir / f"n-{n_nodes}_p-{n_partitions}_{i}.json"
        fpath.write_text(json.dumps(tc, indent=4))
        paths.append(fpath)

    return paths
