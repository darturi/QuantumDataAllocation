"""
JSON round-trip integrity for the test bank.

Writing a test case and reading it back must preserve every field exactly.
"""

import json
from pathlib import Path

from util.test_generation.json_to_dict import json_to_test_case


def test_json_roundtrip_preserves_requests(tmp_path):
    tc = {
        "nodes": {"n1": 7, "n2": 3},
        "partitions": {"p1": 2, "p2": 1},
        "k_safety": 1,
        "requests": {
            "(p1, n1)": 9,
            "(p1, n2)": 1,
            "(p2, n1)": 0,
            "(p2, n2)": 5,
        },
        "comm_costs": {"p1": 4, "p2": 2},
    }

    path = tmp_path / "case.json"
    path.write_text(json.dumps(tc))
    nodes, parts, k, reqs, costs = json_to_test_case(str(path))

    assert nodes == tc["nodes"]
    assert parts == tc["partitions"]
    assert k == tc["k_safety"]
    assert costs == tc["comm_costs"]
    assert reqs == {
        ("p1", "n1"): 9,
        ("p1", "n2"): 1,
        ("p2", "n1"): 0,
        ("p2", "n2"): 5,
    }
