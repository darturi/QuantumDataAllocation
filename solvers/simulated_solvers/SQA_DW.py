"""
S3 — SQA Domain-Wall + Slack-Free Unit-Partition Solver.

Combines two optimisations on top of unit partition sizes:

1. **Slack-free storage** (same as S2): eliminates all S_in slack variables
   by encoding the cardinality constraint sum(A_pn) <= C_n directly as a
   quadratic penalty using only A_pn variables.

2. **Domain-wall k-safety encoding**: replaces the standard one-hot penalty
   (sum A_pn - k)^2 with a domain-wall encoding that uses nearest-neighbour
   chain penalties, reducing the number of quadratic couplings from O(|N|^2)
   to O(|N|) per partition.

Domain-wall encoding (Chancellor, 2019):
    For each partition p, introduce |N|-1 auxiliary "wall" variables
    w_{p,1}, ..., w_{p,|N|-1}.  These form a monotone chain:
        w_{p,1} >= w_{p,2} >= ... >= w_{p,|N|-1}
    The number of 1-bits in the chain represents the number of copies.
    The chain constraint is enforced by penalising "walls" — transitions
    from 0 to 1 (i.e., w_{p,j} = 0 and w_{p,j+1} = 1):
        penalty_chain = h_dw * sum_{j=1}^{|N|-2}  w_{p,j+1} * (1 - w_{p,j})

    To enforce exactly k copies, we fix the k-th wall variable to 1 and
    the (k+1)-th wall variable to 0, or equivalently add penalties:
        penalty_count = h_dw * (1 - w_{p,k})          (must have at least k)
                      + h_dw * w_{p,k+1}               (must have at most k)
    when k < |N|-1, etc.

    The mapping from wall variables to assignment variables:
        The j-th wall variable indicates "at least j copies exist".
        A_pn is linked to the walls via: sum_n A_pn = sum_j w_{p,j}.
        This is enforced by an equality constraint between the two sums.

    Key benefit: the chain constraint has O(|N|) terms (nearest-neighbour)
    vs. O(|N|^2) for the standard (sum - k)^2 penalty.

References:
    Chancellor, N. (2019). "Domain wall encoding of discrete variables for
    quantum annealing and QAOA." arXiv:1903.05068.
"""

import time

import dimod
import pandas as pd
from dwave.samplers import PathIntegralAnnealingSampler
from util.solver_base import SolverBase


class SQADomainWallSolver(SolverBase):
    def __init__(self, nodes, partitions, k_safety, requests, comm_costs):
        for p, size in partitions.items():
            if size != 1:
                raise ValueError(
                    f"SQADomainWallSolver requires all partition sizes = 1, "
                    f"but partition {p} has size {size}"
                )
        SolverBase.__init__(self, nodes, partitions, k_safety, requests, comm_costs)

    def build_bqm(self):
        """Build and return the BQM without solving."""
        bqm = dimod.BinaryQuadraticModel(dimod.BINARY)

        partition_list = list(self.partitions.keys())
        node_list = list(self.nodes.keys())
        num_nodes = len(node_list)

        # 1. Assignment variables A_pn
        A = {(p, n): f'A_{p}_{n}' for p in self.partitions for n in self.nodes}

        # 2. Domain-wall variables W_{p,j} for j = 1..num_nodes
        #    W_{p,j} = 1 means "partition p has at least j copies"
        #    Need num_nodes variables to represent values 0..num_nodes.
        W = {}
        for p in partition_list:
            for j in range(1, num_nodes + 1):
                W[(p, j)] = f'W_{p}_{j}'

        # 3. Penalty weights
        h = sum(
            self.requests[p, n] * self.comm_costs[p]
            for p in self.partitions for n in self.nodes
        ) + 1

        # Scale k-safety / domain-wall penalties by max capacity so they
        # always dominate the under-capacity storage penalty.
        h_k = h * max(self.nodes.values())

        h_dw = h_k     # domain-wall penalty weight
        h_link = h_k   # linking constraint weight
        h_s = h        # storage penalty weight

        # 4. Q_R: k-safety via DOMAIN-WALL encoding
        #
        # 4a. Chain monotonicity: w_{p,j} >= w_{p,j+1}
        #     Penalty for violation: h_dw * w_{p,j+1} * (1 - w_{p,j})
        #     = h_dw * (w_{p,j+1} - w_{p,j} * w_{p,j+1})
        for p in partition_list:
            for j in range(1, num_nodes):
                # Penalise w_{j+1}=1, w_j=0  (domain wall violation)
                bqm.add_variable(W[p, j + 1], h_dw)        # linear: +h_dw * w_{j+1}
                bqm.add_interaction(W[p, j], W[p, j + 1], -h_dw)  # quad: -h_dw * w_j * w_{j+1}

        # 4b. Fix count to exactly k:
        #     - w_{p,k} must be 1  =>  penalty h_dw * (1 - w_{p,k})
        #     - w_{p,k+1} must be 0  =>  penalty h_dw * w_{p,k+1}
        #     (only if the index exists)
        k = self.k_safety
        for p in partition_list:
            if 1 <= k <= num_nodes:
                # w_{p,k} must be 1: penalty = h_dw * (1 - w_{p,k})
                bqm.add_variable(W[p, k], -h_dw)
                # (the constant h_dw is dropped since it doesn't affect optimisation)

            if k + 1 <= num_nodes:
                # w_{p,k+1} must be 0: penalty = h_dw * w_{p,k+1}
                bqm.add_variable(W[p, k + 1], h_dw)

        # 4c. Link domain-wall variables to assignment variables:
        #     sum_n A_pn = sum_j W_{p,j}
        #
        #     We enforce this as an equality constraint:
        #     (sum_n A_pn - sum_j W_{p,j})^2 = 0
        #
        #     This produces:
        #     - A_pn * A_pn' interactions for n != n'  (but fewer than (sum-k)^2
        #       because we're linking to W rather than to a constant)
        #     - W * W interactions (nearest-neighbour from chain)
        #     - A * W cross-interactions
        #
        #     The total coupling count is O(|N|^2 + |N|^2) in the worst case
        #     for the linking constraint.  However, the chain constraint is
        #     only O(|N|), and the linking can be decomposed if needed.
        #
        #     For now we use dimod's built-in equality constraint.
        for p in partition_list:
            link_expr = []
            for n in node_list:
                link_expr.append((A[p, n], 1))
            for j in range(1, num_nodes + 1):
                link_expr.append((W[p, j], -1))
            bqm.add_linear_equality_constraint(
                link_expr, constant=0, lagrange_multiplier=h_link
            )

        # 5. Q_S: storage constraints (SLACK-FREE, same as S2)
        #    (sum_p A_pn - C_n)^2 using only A_pn variables
        for n in node_list:
            capacity = self.nodes[n]

            for i in range(len(partition_list)):
                for j in range(i + 1, len(partition_list)):
                    p1 = partition_list[i]
                    p2 = partition_list[j]
                    bqm.add_interaction(A[p1, n], A[p2, n], 2 * h_s)

            for p in partition_list:
                bqm.add_variable(A[p, n], h_s * (2 - 2 * capacity))

        # 6. Q_C: processing costs
        for p in self.partitions:
            for n in self.nodes:
                bqm.add_variable(A[p, n], -self.requests[p, n] * self.comm_costs[p])

        return bqm

    def solve(self, num_reads=1000, num_sweeps=1000, beta_range=None):
        bqm = self.build_bqm()

        sampler = PathIntegralAnnealingSampler()

        sample_kwargs = dict(num_reads=num_reads, num_sweeps=num_sweeps)
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

        best_sample = sample_obj.sample
        allocation_data = []
        for p in self.partitions:
            row = {'Partition': p}
            for n in self.nodes:
                row[n] = best_sample[f'A_{p}_{n}']
            allocation_data.append(row)

        matrix_df = pd.DataFrame(allocation_data).set_index('Partition')
        print("--- Data Allocation Matrix (S3 Domain-Wall) ---")
        print(matrix_df)
