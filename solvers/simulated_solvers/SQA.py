import time
import dimod
import pandas as pd
from dwave.samplers import PathIntegralAnnealingSampler
from util.solver_base import SolverBase


class SQASolver(SolverBase):
    def __init__(self, nodes, partitions, k_safety, requests, comm_costs):
        SolverBase.__init__(self, nodes, partitions, k_safety, requests, comm_costs)

    def build_bqm(self):
        """Build and return the BinaryQuadraticModel without solving.

        Useful for qubit result_analysis and for subclasses that share the solve loop
        but override the BQM construction.
        """
        bqm = dimod.BinaryQuadraticModel(dimod.BINARY)

        # 1. Define Variables
        # A_pn: partition p assigned to node n
        A = {(p, n): f'A_{p}_{n}' for p in self.partitions for n in self.nodes}

        # S_in: binary slack variables encoding the storage capacity constraint as a QUBO equality.
        # Uses chunks {1, 2, 4, ..., 2^(k-1)} which sum to exactly 2^k - 1.
        # REQUIREMENT: capacity must be a Mersenne number (2^k - 1: e.g. 7, 15, 31, 63, 127).
        # If capacity is arbitrary, the chunks can sum beyond capacity and Q_S will not
        # penalise storage overflows.
        S = {}
        for n, capacity in self.nodes.items():
            # Using powers of 2 for chunks up to capacity
            num_chunks = capacity.bit_length()
            for j in range(num_chunks):
                chunk_val = 2 ** j
                if chunk_val <= capacity:
                    S[(n, chunk_val)] = f'S_{n}_{chunk_val}'

        # 2. Penalty Weight (h)
        # h must be greater than max processing costs
        h = sum(self.requests[p, n] * self.comm_costs[p] for p in self.partitions for n in self.nodes) + 1

        # 3. Component: k-Safety Constraints (Q_R)
        # Target: sum(A_pn) == k for each partition
        for p in self.partitions:
            k_safety_expr = [(A[p, n], 1) for n in self.nodes]
            bqm.add_linear_equality_constraint(k_safety_expr, constant=-self.k_safety, lagrange_multiplier=h)

        # 4. Component: Storage Constraints (Q_S)
        # Target: sum(A_pn * size) == sum(S_in * i)
        for n, capacity in self.nodes.items():
            storage_expr = []
            # Add partition assignments
            for p in self.partitions:
                storage_expr.append((A[p, n], self.partitions[p]))
            # Subtract storage chunks (slack variables)
            for (node_id, chunk_val), var_name in S.items():
                if node_id == n:
                    storage_expr.append((var_name, -chunk_val))

            bqm.add_linear_equality_constraint(storage_expr, constant=0, lagrange_multiplier=h)

        # 5. Component: Processing Costs (Q_C)
        # Minimize: sum(r_pn * c_p * (1 - A_pn))
        for p in self.partitions:
            for n in self.nodes:
                # -r_pn * c_p * A_pn (minimizing this is maximizing local storage)
                bqm.add_variable(A[p, n], -self.requests[p, n] * self.comm_costs[p])

        return bqm

    def solve(self, num_reads=1000, num_sweeps=1000, beta_range=None):
        bqm = self.build_bqm()

        # Solve using Simulated Quantum Annealing (Path Integral Monte Carlo)
        sampler = PathIntegralAnnealingSampler()

        sample_kwargs = dict(
            num_reads=num_reads,
            num_sweeps=num_sweeps,
        )
        if beta_range is not None:
            sample_kwargs['beta_range'] = beta_range

        start = time.perf_counter()
        sampleset = sampler.sample(bqm, **sample_kwargs)
        end = time.perf_counter()

        time_taken = (end - start) * 1000

        self.time_taken = time_taken
        self.result = sampleset.first

        return time_taken, sampleset.first

    def format_answer(self, result=None):
        sample_obj = result if result is not None else self.result
        if sample_obj is None:
            print("No valid solution found.")
            return

        # Extract the sample from the result object
        best_sample = sample_obj.sample

        # Create a structured Matrix (using a Pandas DataFrame for visibility)
        allocation_data = []
        for p in self.partitions:
            row = {'Partition': p}
            for n in self.nodes:
                # Access the dictionary-labeled variable in the result
                # i.e., result['A_p1_n1']
                var_name = f'A_{p}_{n}'
                row[n] = best_sample[var_name]
            allocation_data.append(row)

        matrix_df = pd.DataFrame(allocation_data).set_index('Partition')
        print("--- Data Allocation Matrix ---")
        print(matrix_df)
