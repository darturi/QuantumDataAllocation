"""
Generate **paired** test cases: for each random seed, produce both a
variable-size test case (for S0) and a unit-partition test case (for S1–S3).

The two test cases share the same node count, partition count, request
frequencies, and communication costs — only partition sizes and node
capacities differ.  This controls for all other variables and isolates the
effect of the formulation change.
"""

import json
import random
from pathlib import Path

from util.test_generation.generate_test_case import generate_test_case
from util.test_generation.generate_unit_test_case import generate_unit_test_case


def generate_paired_test_case(
    n_nodes,
    n_partitions,
    k_safety=2,
    seed=None,
    size_range=(5, 20),
    req_range=(0, 10),
    cost_range=(1, 10),
    capacity_factor=1.5,
    unit_capacity_factor=1.3,
):
    """
    Generate a matched pair of test cases (variable-size and unit-partition).

    Both test cases use the same random seed for request frequencies and
    communication costs so those parameters are identical.  Partition sizes
    and node capacities are formulation-specific.

    Args:
        n_nodes:              number of storage nodes
        n_partitions:         number of data partitions
        k_safety:             replication factor
        seed:                 random seed (None = non-deterministic)
        size_range:           (min, max) partition sizes for the variable-size case
        req_range:            (min, max) request frequencies
        cost_range:           (min, max) communication costs
        capacity_factor:      capacity multiplier for variable-size case
        unit_capacity_factor: capacity multiplier for unit-partition case

    Returns:
        (variable_tc, unit_tc) — two dicts in standard test case format.
    """
    # Generate variable-size test case
    var_tc = generate_test_case(
        n_nodes, n_partitions,
        k_safety=k_safety,
        seed=seed,
        size_range=size_range,
        req_range=req_range,
        cost_range=cost_range,
        capacity_factor=capacity_factor,
    )

    # Generate unit test case with the same seed so requests/costs match
    unit_tc = generate_unit_test_case(
        n_nodes, n_partitions,
        k_safety=k_safety,
        seed=seed,
        req_range=req_range,
        cost_range=cost_range,
        capacity_factor=unit_capacity_factor,
    )

    # Overwrite unit_tc requests and comm_costs with the variable_tc values
    # to guarantee they are identical (the generators use the seed in the
    # same order for requests/costs, but sizes consume RNG calls first in
    # the variable case, shifting the sequence).
    unit_tc["requests"] = var_tc["requests"]
    unit_tc["comm_costs"] = var_tc["comm_costs"]

    return var_tc, unit_tc


def generate_paired_batch(
    n_nodes,
    n_partitions,
    count,
    output_dir,
    k_safety=2,
    base_seed=None,
    **kwargs,
):
    """
    Generate ``count`` paired test cases and save them as JSON files.

    For each index *i*, two files are written:

    * ``n-{n}_p-{p}_{i}_var.json``   — variable-size test case
    * ``n-{n}_p-{p}_{i}_unit.json``  — unit-partition test case

    Args:
        n_nodes, n_partitions, count, k_safety, base_seed:
            Same as generate_paired_test_case.
        output_dir: destination directory (str or Path)
        **kwargs:   forwarded to generate_paired_test_case

    Returns:
        list[tuple[Path, Path]]: (var_path, unit_path) for each pair.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pairs = []
    for i in range(1, count + 1):
        seed = None if base_seed is None else base_seed + i
        var_tc, unit_tc = generate_paired_test_case(
            n_nodes, n_partitions,
            k_safety=k_safety,
            seed=seed,
            **kwargs,
        )

        prefix = f"n-{n_nodes}_p-{n_partitions}_{i}"
        var_path = output_dir / f"{prefix}_var.json"
        unit_path = output_dir / f"{prefix}_unit.json"

        var_path.write_text(json.dumps(var_tc, indent=4))
        unit_path.write_text(json.dumps(unit_tc, indent=4))

        pairs.append((var_path, unit_path))

    return pairs
