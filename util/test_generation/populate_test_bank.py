"""
Populate the QuantumClean test bank.

Two grids are defined:

* ``LEAN_*`` (default) -- a deliberately small grid that's enough to
  rank S1 vs S2 with paired comparisons at three tightness levels.
  Generates ~180 cases per (tier, formulation), 720 total.
* ``FULL_*`` (opt-in) -- the original dense grid.  Generates ~5,340
  cases total.  Use only when you need tight error bars per cell or
  fine-grained scaling curves.

Run with the lean grid (default):

    python -m util.test_generation.populate_test_bank

Run with the full grid (much slower downstream):

    python -m util.test_generation.populate_test_bank --full

See ``REMEDIATION_PLAN.md`` and the run output for the rationale behind
the lean defaults.

Directory layout:

    test_bank/
        unit_partition/
            tier1/n{N}_p{P}/t{30,70,100}/   ← CASES_PER_COMBO files each
            tier2/...
        arbitrary_partition/
            tier1/n{N}_p{P}/t{30,70,90}/
            tier2/...
"""

import sys
from pathlib import Path

from util.test_generation.generate_test_case import generate_batch
from util.test_generation.generate_unit_test_case import generate_unit_batch

TEST_BANK = Path(__file__).resolve().parent.parent.parent / "test_bank"

# ---------- LEAN grid (default) ----------
#
# Rationale:
#   * Drop N=2 (no encoding signal -- only one valid placement per partition).
#   * Drop N=7 (interpolates between 5 and 9; no new boundary information).
#   * Keep log-spaced P values; drop interpolating P values that don't
#     change the regime.
#   * 5 paired cases per cell is enough for the paired sign test and
#     paired t-test at the effect sizes we've already observed.

LEAN_TIER1_NODES        = [3, 5, 9]
LEAN_TIER1_PARTITIONS   = [4, 12, 26, 50]
LEAN_TIER2_NODES        = [5, 9, 15]
LEAN_TIER2_PARTITIONS   = [18, 50, 100]
LEAN_CASES_PER_COMBO    = 5

# ---------- FULL grid (opt-in) ----------
#
# Original dense grid.  Generates ~5,340 cases.  Hours-to-days to run
# against ILP + S1 + S2 at the default sampler budget.

FULL_TIER1_NODES        = [2, 3, 5, 7, 9]
FULL_TIER1_PARTITIONS   = [3, 4, 8, 12, 18, 26, 36, 50]
FULL_TIER2_NODES        = [2, 3, 5, 7, 9, 12, 15]
FULL_TIER2_PARTITIONS   = [3, 8, 18, 36, 50, 75, 100]
FULL_CASES_PER_COMBO    = 10

# ---------- Tightness levels (same for both grids) ----------
#
# 3 levels is the minimum that covers loose / moderate / tight regimes.
# Cutting tightness would forfeit the main reason the test-bank reform
# happened in Phase 4.
UNIT_TIGHTNESS_LEVELS      = [0.3, 0.7, 1.0]
ARBITRARY_TIGHTNESS_LEVELS = [0.3, 0.7, 0.9]


# ---------- helpers ----------

def _populate_tier(tier_name, node_counts, partition_counts, cases_per_combo, base_seed):
    """Generate both unit and arbitrary cases for a single tier."""
    unit_dir = TEST_BANK / "unit_partition" / tier_name
    arb_dir  = TEST_BANK / "arbitrary_partition" / tier_name

    unit_total = 0
    arb_total  = 0

    for n_nodes in node_counts:
        for n_parts in partition_counts:
            for tightness in UNIT_TIGHTNESS_LEVELS:
                seed = base_seed + n_nodes * 1000 + n_parts + int(tightness * 1_000_000)
                unit_out = unit_dir / f"n{n_nodes}_p{n_parts}" / f"t{int(tightness*100)}"
                paths = generate_unit_batch(
                    n_nodes, n_parts, cases_per_combo, unit_out,
                    k_safety=2, base_seed=seed, tightness=tightness,
                )
                unit_total += len(paths)
                print(f"  [unit  t={tightness:.1f}] {len(paths)} cases -> {unit_out}")

            for tightness in ARBITRARY_TIGHTNESS_LEVELS:
                seed = base_seed + n_nodes * 1000 + n_parts + int(tightness * 1_000_000)
                arb_out = arb_dir / f"n{n_nodes}_p{n_parts}" / f"t{int(tightness*100)}"
                paths = generate_batch(
                    n_nodes, n_parts, cases_per_combo, arb_out,
                    k_safety=2, base_seed=seed, tightness=tightness,
                )
                arb_total += len(paths)
                print(f"  [arb   t={tightness:.1f}] {len(paths)} cases -> {arb_out}")

    return unit_total, arb_total


# ---------- main ----------

def main(use_full_grid=False):
    if use_full_grid:
        print("=== FULL grid (this will take a while downstream) ===\n")
        tier1_nodes = FULL_TIER1_NODES
        tier1_parts = FULL_TIER1_PARTITIONS
        tier2_nodes = FULL_TIER2_NODES
        tier2_parts = FULL_TIER2_PARTITIONS
        cases_per_combo = FULL_CASES_PER_COMBO
    else:
        print("=== LEAN grid (default) ===\n")
        tier1_nodes = LEAN_TIER1_NODES
        tier1_parts = LEAN_TIER1_PARTITIONS
        tier2_nodes = LEAN_TIER2_NODES
        tier2_parts = LEAN_TIER2_PARTITIONS
        cases_per_combo = LEAN_CASES_PER_COMBO

    print("=== Tier 1 ===")
    t1_unit, t1_arb = _populate_tier(
        "tier1", tier1_nodes, tier1_parts, cases_per_combo, base_seed=1000,
    )
    print(f"\nTier 1: {t1_unit} unit + {t1_arb} arbitrary = {t1_unit + t1_arb}")

    print("\n=== Tier 2 ===")
    t2_unit, t2_arb = _populate_tier(
        "tier2", tier2_nodes, tier2_parts, cases_per_combo, base_seed=2000,
    )
    print(f"\nTier 2: {t2_unit} unit + {t2_arb} arbitrary = {t2_unit + t2_arb}")

    grand = t1_unit + t1_arb + t2_unit + t2_arb
    print(f"\n=== Done: {grand} total test cases generated ===")


if __name__ == "__main__":
    use_full = "--full" in sys.argv[1:]
    main(use_full_grid=use_full)
