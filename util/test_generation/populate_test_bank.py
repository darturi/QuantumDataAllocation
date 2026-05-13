"""
Populate the QuantumClean test bank.

Generates matched unit-partition and arbitrary-partition test cases across
two tiers of problem sizes.  Both formulations share the same parameter
grids and base seeds so that results are directly comparable.

Tier 1: matches the existing grid_sweep parameter range for
        apples-to-apples comparison with earlier experiments.
Tier 2: extended range to stress-test solvers and show where
        optimised formulations excel.

Output structure:
    test_bank/
        unit_partition/
            tier1/n{N}_p{P}/   — 10 JSON files each
            tier2/n{N}_p{P}/
        arbitrary_partition/
            tier1/n{N}_p{P}/
            tier2/n{N}_p{P}/

Usage:
    python -m util.test_generation.populate_test_bank
"""

from pathlib import Path

from util.test_generation.generate_test_case import generate_batch
from util.test_generation.generate_unit_test_case import generate_unit_batch

TEST_BANK = Path(__file__).resolve().parent.parent.parent / "test_bank"

# ---------- parameter grids ----------

TIER1_NODES      = [2, 3, 5, 7, 9]
TIER1_PARTITIONS = [3, 4, 8, 12, 18, 26, 36, 50]

TIER2_NODES      = [2, 3, 5, 7, 9, 12, 15]
TIER2_PARTITIONS = [3, 8, 18, 36, 50, 75, 100]

CASES_PER_COMBO = 10


# ---------- helpers ----------

def _populate_tier(
    tier_name,
    node_counts,
    partition_counts,
    base_seed,
):
    """Generate both unit and arbitrary cases for a single tier."""
    unit_dir = TEST_BANK / "unit_partition" / tier_name
    arb_dir  = TEST_BANK / "arbitrary_partition" / tier_name

    unit_total = 0
    arb_total  = 0

    for n_nodes in node_counts:
        for n_parts in partition_counts:
            seed = base_seed + n_nodes * 1000 + n_parts

            # Unit-partition cases
            unit_out = unit_dir / f"n{n_nodes}_p{n_parts}"
            paths = generate_unit_batch(
                n_nodes, n_parts, CASES_PER_COMBO, unit_out,
                k_safety=2, base_seed=seed, capacity_factor=1.3,
            )
            unit_total += len(paths)
            print(f"  [unit]      {len(paths)} cases -> {unit_out}")

            # Arbitrary-partition cases (same seed for comparability)
            arb_out = arb_dir / f"n{n_nodes}_p{n_parts}"
            paths = generate_batch(
                n_nodes, n_parts, CASES_PER_COMBO, arb_out,
                k_safety=2, base_seed=seed, capacity_factor=1.5,
            )
            arb_total += len(paths)
            print(f"  [arbitrary] {len(paths)} cases -> {arb_out}")

    return unit_total, arb_total


# ---------- main ----------

def main():
    print("=== Tier 1 ===")
    t1_unit, t1_arb = _populate_tier(
        "tier1", TIER1_NODES, TIER1_PARTITIONS, base_seed=1000,
    )
    print(f"\nTier 1: {t1_unit} unit + {t1_arb} arbitrary = {t1_unit + t1_arb}")

    print("\n=== Tier 2 ===")
    t2_unit, t2_arb = _populate_tier(
        "tier2", TIER2_NODES, TIER2_PARTITIONS, base_seed=2000,
    )
    print(f"\nTier 2: {t2_unit} unit + {t2_arb} arbitrary = {t2_unit + t2_arb}")

    grand = t1_unit + t1_arb + t2_unit + t2_arb
    print(f"\n=== Done: {grand} total test cases generated ===")


if __name__ == "__main__":
    main()
