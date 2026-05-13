import time
import pulp
import pandas as pd
from util.solver_base import SolverBase

class ILPSolver(SolverBase):
    def __init__(self, nodes, partitions, k_safety, requests, comm_costs):
        SolverBase.__init__(self, nodes, partitions, k_safety, requests, comm_costs)

    def solve(self):
        # 1. Initialize the Model
        # We want to Minimize processing costs
        prob = pulp.LpProblem("Data_Allocation_Optimization", pulp.LpMinimize)

        # 2. Define Decision Variables
        # A_pn: 1 if partition p is assigned to node n, else 0
        # Note: We do NOT need slack variables (S_in) for classical ILP
        A = pulp.LpVariable.dicts("Assign",
                                  ((p, n) for p in self.partitions for n in self.nodes),
                                  cat='Binary')

        # 3. Define Objective Function
        # Minimize: sum(r_pn * c_p * (1 - A_pn))
        # This represents the cost of fetching data remotely
        total_cost = []
        for p in self.partitions:
            for n in self.nodes:
                # Cost is incurred if A[p,n] is 0 (1 - A is 1)
                cost_factor = self.requests.get((p, n), 0) * self.comm_costs[p]
                total_cost.append(cost_factor * (1 - A[p, n]))

        prob += pulp.lpSum(total_cost)

        # 4. Constraint: k-Safety
        # Each partition must be stored on exactly k nodes
        for p in self.partitions:
            prob += pulp.lpSum([A[p, n] for n in self.nodes]) == self.k_safety, f"Safety_{p}"

        # 5. Constraint: Storage Capacity
        # The sum of partition sizes on a node must not exceed its capacity
        # ILP handles inequalities (<=) natively, unlike QUBO
        for n, capacity in self.nodes.items():
            prob += pulp.lpSum([A[p, n] * self.partitions[p] for p in self.partitions]) <= capacity, f"Capacity_{n}"

        # 6. Solve
        # Uses standard Branch and Bound algorithms (CBC Solver is default)
        start = time.perf_counter()
        prob.solve(pulp.PULP_CBC_CMD(msg=0))
        end = time.perf_counter()

        time_taken = (end - start) * 1000

        # 7. Check Status
        status = pulp.LpStatus[prob.status]
        print(f"Classical Solver Status: {status}")

        if status != 'Optimal':
            return time_taken, None

        # 8. Extract Results
        result_matrix = {}
        for p in self.partitions:
            result_matrix[p] = {}
            for n in self.nodes:
                result_matrix[p][n] = int(A[p, n].varValue)

        self.result = result_matrix
        self.time_taken = time_taken

        return time_taken, result_matrix

    def format_answer(self, result=None):
        data = result if result is not None else self.result
        if data:
            df = pd.DataFrame.from_dict(data, orient='index')
            print("\n--- Classical Allocation Matrix ---")
            print(df)
        else:
            print("No valid solution found.")
