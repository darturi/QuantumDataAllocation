"""
Generate **paired** test cases: for each random seed, produce one
arbitrary-partition test case (for S1) and one unit-partition test
case (for S1 + S2), where the two share request frequencies and
communication costs.

This controls for those parameters and isolates the effect of the
partition-size change alone -- useful for ablation experiments that
compare S1's slack-variable encoding under uniform vs variable sizes.

After Phase 4, both generators use the ``tightness`` parameter
(``0.0`` loose .. ``1.0`` tight) and verify feasibility with an ILP
probe.  The previous ``capacity_factor`` argument is gone.
"""

import json
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
    arbitrary_tightness=0.5,
    unit_tightness=0.7,
):
    """
    Generate a matched pair (variable-size, unit-partition).

    Both test cases use the same RNG seed for request frequencies and
    communication costs, so those parameters are identical.  Partition
    sizes and node capacities are formulation-specific.

    Tightness is exposed as two separate parameters because the
    arbitrary-partition case can be intrinsically infeasible at very
    high tightness (bin-packing); a sensible default is to use a
    slightly looser arbitrary case than unit case.

    Returns:
        (var_tc, unit_tc) -- two dicts in standard test-case JSON format.
    """
    var_tc = generate_test_case(
        n_nodes, n_partitions,
        k_safety=k_safety,
        seed=seed,
        size_range=size_range,
        req_range=req_range,
        cost_range=cost_range,
        tightness=arbitrary_tightness,
    )

    unit_tc = generate_unit_test_case(
        n_nodes, n_partitions,
        k_safety=k_safety,
        seed=seed,
        req_range=req_range,
        cost_range=cost_range,
        tightness=unit_tightness,
    )

    # Overwrite unit_tc's requests/comm_costs with the variable_tc values.
    # The two generators draw partition sizes first, which shifts the
    # RNG state by different amounts for the two cases; copying the
    # values directly guarantees the pair shares those exact inputs.
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

    For each index ``i`` two files are written:

        n-{n}_p-{p}_{i}_var.json    -- variable-size test case
        n-{n}_p-{p}_{i}_unit.json   -- unit-partition test case

    Returns:
        list[tuple[Path, Path]] -- (var_path, unit_path) per pair.
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
