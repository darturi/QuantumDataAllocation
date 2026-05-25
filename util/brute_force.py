"""
Reference brute-force solver for the data-allocation problem.

Used as an oracle in unit tests. Enumerates every {0,1}-assignment of
``A_{p,n}`` variables, filters to feasible assignments (k-safety + capacity),
and returns the one with minimum communication cost.

This is intentionally simple, slow, and easy to audit — its purpose is to
ground the QUBO-based solvers in an indisputable truth.
"""

from itertools import product
from typing import Optional


def brute_force_solve(nodes, partitions, k_safety, requests, comm_costs):
    """
    Find the global optimum by exhaustive enumeration.

    Returns a tuple ``(cost, assignment_dict)`` where ``assignment_dict``
    is a dict ``{"A_{p}_{n}": 0|1}``.  Returns ``(None, None)`` if no
    feasible assignment exists.

    Only viable for small instances — runtime is ``O(2^(|P|*|N|))``.
    """
    part_list = list(partitions.keys())
    node_list = list(nodes.keys())
    n_vars = len(part_list) * len(node_list)

    if n_vars > 24:
        raise ValueError(
            f"brute_force_solve refuses to enumerate {2**n_vars} states; "
            f"use it only on instances with |P|*|N| <= 24."
        )

    best_cost: Optional[int] = None
    best_assignment: Optional[dict] = None

    for bits in product((0, 1), repeat=n_vars):
        assignment = {
            f"A_{p}_{n}": bits[i * len(node_list) + j]
            for i, p in enumerate(part_list)
            for j, n in enumerate(node_list)
        }

        # k-safety: each partition stored on exactly k nodes
        ok = True
        for p in part_list:
            if sum(assignment[f"A_{p}_{n}"] for n in node_list) != k_safety:
                ok = False
                break
        if not ok:
            continue

        # Capacity: total size of partitions on a node <= node capacity
        for n in node_list:
            used = sum(
                assignment[f"A_{p}_{n}"] * partitions[p] for p in part_list
            )
            if used > nodes[n]:
                ok = False
                break
        if not ok:
            continue

        # Cost: requests * comm_cost * (1 - assigned)
        cost = sum(
            requests[p, n] * comm_costs[p] * (1 - assignment[f"A_{p}_{n}"])
            for p in part_list
            for n in node_list
        )

        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_assignment = assignment

    return best_cost, best_assignment
