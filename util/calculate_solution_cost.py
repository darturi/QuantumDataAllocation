def calculate_solution_cost(nodes, partitions, k_safety, requests, comm_costs, solution):
    """
    Calculate the total communication cost of a solution.

    Cost = sum over all (p, n): r_pn * c_p * (1 - A_pn)
    i.e., the sum of (request_rate * comm_cost) for every (partition, node) pair
    where the partition is NOT stored on that node.

    Args:
        nodes:       {node_id: capacity}
        partitions:  {partition_id: size}
        k_safety:    int
        requests:    {(partition_id, node_id): count}  — as returned by json_to_test_case
        comm_costs:  {partition_id: cost}
        solution:    dimod SampleView (sampleset.first) with a .sample dict,
                     or a plain dict of {"A_{p}_{n}": 0|1, ...}

    Returns:
        Total communication cost (int or float).
    """
    if solution is None:
        return None

    sample = solution.sample if hasattr(solution, 'sample') else solution

    total_cost = 0
    for p in partitions:
        c_p = comm_costs[p]
        for n in nodes:
            a_pn = int(sample.get(f'A_{p}_{n}', 0))
            r_pn = requests.get((p, n), 0)
            total_cost += r_pn * c_p * (1 - a_pn)

    return total_cost


def is_valid_solution(nodes, partitions, k_safety, requests, comm_costs, solution):
    """
    Check whether a solution satisfies all problem constraints.

    Constraints checked:
        1. k-Safety:  each partition is stored on exactly k_safety nodes
        2. Capacity:  total size of partitions stored on each node <= that node's capacity

    Args:
        nodes, partitions, k_safety, requests, comm_costs: as returned by json_to_test_case
        solution: dimod SampleView (sampleset.first) or plain dict {"A_{p}_{n}": 0|1, ...}

    Returns:
        True if all constraints are satisfied, False otherwise (including if solution is None).
    """
    if solution is None:
        return False

    sample = solution.sample if hasattr(solution, 'sample') else solution

    # 1. k-Safety: each partition must be on exactly k_safety nodes
    for p in partitions:
        count = sum(int(sample.get(f'A_{p}_{n}', 0)) for n in nodes)
        if count != k_safety:
            return False

    # 2. Capacity: total partition sizes on each node must not exceed its capacity
    for n, capacity in nodes.items():
        used = sum(int(sample.get(f'A_{p}_{n}', 0)) * size for p, size in partitions.items())
        if used > capacity:
            return False

    return True


def solutions_equal(solution_a, solution_b):
    """
    Check whether two solutions allocate data in the same way.

    Only assignment variables (A_{p}_{n}) are compared — slack variables
    introduced by the QUBO formulation are ignored.

    Args:
        solution_a, solution_b: dimod SampleView (sampleset.first) or
                                plain dict {"A_{p}_{n}": 0|1, ...}

    Returns:
        True if both solutions assign every partition to the same set of nodes,
        False otherwise (including if either solution is None).
    """
    if solution_a is None or solution_b is None:
        return False

    sample_a = solution_a.sample if hasattr(solution_a, 'sample') else solution_a
    sample_b = solution_b.sample if hasattr(solution_b, 'sample') else solution_b

    a_vars_a = {k: v for k, v in sample_a.items() if k.startswith('A_')}
    a_vars_b = {k: v for k, v in sample_b.items() if k.startswith('A_')}

    return a_vars_a == a_vars_b