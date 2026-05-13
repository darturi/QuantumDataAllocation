"""
Generate the unit-partition test case banks (Tier 1 + Tier 2).

Tier 1: matches the existing grid_sweep parameter range for
        apples-to-apples comparison.
Tier 2: extended range to show where optimised formulations excel.

Usage:
    python -m TESTS.generate_test_banks
"""

from pathlib import Path
from util.test_generation.generate_unit_test_case import generate_unit_batch

BASE_DIR = Path(__file__).resolve().parent.parent.parent / "test_bank"

def generate_tier1(base_seed=1000):
    """Tier 1 — comparable range to existing grid_sweep."""
    node_counts = [2, 3, 5, 7, 9]
    partition_counts = [3, 4, 8, 12, 18, 26, 36, 50]
    z = 10  # cases per combo

    tier_dir = BASE_DIR / "tier1"
    total = 0

    for n_nodes in node_counts:
        for n_partitions in partition_counts:
            out_dir = tier_dir / f"n{n_nodes}_p{n_partitions}"
            seed = base_seed + n_nodes * 1000 + n_partitions
            paths = generate_unit_batch(
                n_nodes, n_partitions, z, out_dir,
                k_safety=2, base_seed=seed, capacity_factor=1.3,
            )
            total += len(paths)
            print(f"  Generated {len(paths)} cases in {out_dir}")

    print(f"\nTier 1 total: {total} test cases")
    return total


def generate_tier2(base_seed=2000):
    """Tier 2 — extended range."""
    node_counts = [2, 3, 5, 7, 9, 12, 15]
    partition_counts = [3, 8, 18, 36, 50, 75, 100]
    z = 10

    tier_dir = BASE_DIR / "tier2"
    total = 0

    for n_nodes in node_counts:
        for n_partitions in partition_counts:
            out_dir = tier_dir / f"n{n_nodes}_p{n_partitions}"
            seed = base_seed + n_nodes * 1000 + n_partitions
            paths = generate_unit_batch(
                n_nodes, n_partitions, z, out_dir,
                k_safety=2, base_seed=seed, capacity_factor=1.3,
            )
            total += len(paths)
            print(f"  Generated {len(paths)} cases in {out_dir}")

    print(f"\nTier 2 total: {total} test cases")
    return total


if __name__ == "__main__":
    print("=== Generating Tier 1 test cases ===")
    t1 = generate_tier1()

    print("\n=== Generating Tier 2 test cases ===")
    t2 = generate_tier2()

    print(f"\n=== Done: {t1 + t2} total test cases generated ===")
