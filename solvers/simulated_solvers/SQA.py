"""
S1 — SQA baseline solver.

Faithful implementation of Paper 1 (Trummer 2025): QUBO formulation with
binary slack variables S_{i,n} encoding the storage inequality
    sum_p A_{p,n} * size_p  <=  C_n
as an exact equality
    sum_p A_{p,n} * size_p  ==  sum_i i * S_{i,n}.

To encode every value in 0..C_n exactly, we use a binary expansion of
C_n: chunks {1, 2, 4, ..., 2^J} where 2^(J+1) - 1 <= C_n, plus a residual
chunk of value (C_n - (2^(J+1) - 1)) if C_n is not Mersenne. The chunk
values sum to exactly C_n, so the slack variables can represent any
storage usage in [0, C_n] -- no over-loose constraint, no Mersenne
requirement.
"""

import time

import dimod
import pandas as pd
from dwave.samplers import PathIntegralAnnealingSampler

from util.solver_base import SolverBase


def _binary_chunks(capacity):
    """
    Return chunk values whose sum equals ``capacity``.

    Uses the standard binary expansion (1, 2, 4, ...) up to the largest
    power of two whose cumulative sum does not exceed ``capacity``, then
    appends a single residual chunk for the remainder. The resulting
    chunks let a sum of selected chunks represent every integer in
    [0, capacity] exactly.

    Examples:
        capacity=7  -> [1, 2, 4]           (Mersenne; no residual)
        capacity=10 -> [1, 2, 4, 3]        (3 residual after 1+2+4=7)
        capacity=1  -> [1]
        capacity=0  -> []
    """
    if capacity < 0:
        raise ValueError(f"capacity must be non-negative, got {capacity}")
    chunks = []
    cumulative = 0
    j = 0
    while cumulative + (1 << j) <= capacity:
        chunks.append(1 << j)
        cumulative += 1 << j
        j += 1
    residual = capacity - cumulative
    if residual > 0:
        chunks.append(residual)
    assert sum(chunks) == capacity, (
        f"chunk decomposition broken: {chunks} sums to {sum(chunks)}, "
        f"expected {capacity}"
    )
    return chunks


class SQASolver(SolverBase):
    def __init__(self, nodes, partitions, k_safety, requests, comm_costs):
        SolverBase.__init__(self, nodes, partitions, k_safety, requests, comm_costs)

    def build_bqm(self):
        """Build and return the BinaryQuadraticModel without solving."""
        bqm = dimod.BinaryQuadraticModel(dimod.BINARY)

        # 1. Define Variables
        # A_pn: partition p assigned to node n
        A = {(p, n): f"A_{p}_{n}" for p in self.partitions for n in self.nodes}

        # S_{n,c}: binary slack variables; each S has a chunk value c.
        #   Variable name uses the chunk *index* (0, 1, 2, ...) so that
        #   two chunks with the same value (impossible here, but defensive)
        #   would not collide.
        S = {}                          # (n, chunk_index) -> var_name
        chunks_by_node = {}             # n -> [chunk_values]
        for n, capacity in self.nodes.items():
            chunks = _binary_chunks(int(capacity))
            chunks_by_node[n] = chunks
            for idx, val in enumerate(chunks):
                S[(n, idx)] = f"S_{n}_{idx}"

        # 2. Penalty weight (Paper 1, Eq. 9): h > sum(r_pn * c_p) suffices.
        h = sum(
            self.requests[p, n] * self.comm_costs[p]
            for p in self.partitions for n in self.nodes
        ) + 1

        # 3. Q_R: k-safety constraints
        for p in self.partitions:
            k_safety_expr = [(A[p, n], 1) for n in self.nodes]
            bqm.add_linear_equality_constraint(
                k_safety_expr,
                constant=-self.k_safety,
                lagrange_multiplier=h,
            )

        # 4. Q_S: storage constraint as equality
        #    sum_p A_pn * size_p  ==  sum_i chunk_i * S_{n,i}
        for n, _capacity in self.nodes.items():
            storage_expr = []
            for p in self.partitions:
                storage_expr.append((A[p, n], int(self.partitions[p])))
            for idx, val in enumerate(chunks_by_node[n]):
                storage_expr.append((S[(n, idx)], -int(val)))
            bqm.add_linear_equality_constraint(
                storage_expr, constant=0, lagrange_multiplier=h
            )

        # 5. Q_C: processing costs (Paper 1, Eq. 5; constants dropped)
        for p in self.partitions:
            for n in self.nodes:
                bqm.add_variable(
                    A[p, n], -self.requests[p, n] * self.comm_costs[p]
                )

        return bqm

    def solve(self, num_reads=1000, num_sweeps=1000, beta_range=None):
        bqm = self.build_bqm()
        sampler = PathIntegralAnnealingSampler()
        sample_kwargs = dict(num_reads=num_reads, num_sweeps=num_sweeps)
        if beta_range is not None:
            sample_kwargs["beta_range"] = beta_range

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

        best_sample = sample_obj.sample
        allocation_data = []
        for p in self.partitions:
            row = {"Partition": p}
            for n in self.nodes:
                row[n] = best_sample[f"A_{p}_{n}"]
            allocation_data.append(row)

        matrix_df = pd.DataFrame(allocation_data).set_index("Partition")
        print("--- Data Allocation Matrix ---")
        print(matrix_df)
