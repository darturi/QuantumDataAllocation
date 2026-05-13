from abc import abstractmethod, ABC


class SolverBase(ABC):
    def __init__(self, nodes, partitions, k_safety, requests, comm_costs):
        self.nodes = nodes
        self.partitions = partitions
        self.k_safety = k_safety
        self.requests = requests
        self.comm_costs = comm_costs
        self.result = None
        self.time_taken = -1

    @abstractmethod
    def solve(self):
        pass

    @abstractmethod
    def format_answer(self, result):
        pass