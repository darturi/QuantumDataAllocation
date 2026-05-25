"""
Test-case JSON loader.

Two entry points:

* ``json_to_test_case(path)`` returns the 5-tuple that every solver
  constructor expects.  Stable contract -- do not extend.

* ``load_test_case_metadata(path)`` returns a dict of any
  non-input fields the test-case JSON happens to carry (notably
  ``tightness``).  The experiment harness uses this to record
  test-bank metadata alongside each result.
"""

import json

# Fields that are *inputs* to the solver.  Anything else found in a
# test-case JSON is treated as metadata and surfaced via
# ``load_test_case_metadata``.
_INPUT_FIELDS = frozenset(
    {"nodes", "partitions", "k_safety", "requests", "comm_costs"}
)


def json_to_test_case(json_path):
    """Return ``(nodes, partitions, k_safety, requests, comm_costs)``."""
    with open(json_path, "r") as f:
        data = json.load(f)

    requests = {}
    for key, value in data["requests"].items():
        p, n = key[1:-1].split(", ")
        requests[(p, n)] = value

    return data["nodes"], data["partitions"], data["k_safety"], requests, data["comm_costs"]


def load_test_case_metadata(json_path):
    """
    Return a dict of every top-level field in the test-case JSON that
    is *not* a solver input.

    Currently this surfaces ``tightness`` (added in Phase 4) and any
    other future top-level metadata.  Old test-case JSONs that don't
    carry these fields just return an empty dict.

    The harness merges this dict into each per-case result entry so
    downstream analysis can group results by tightness, partition-size
    regime, etc., without re-reading the test-case files.
    """
    with open(json_path, "r") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if k not in _INPUT_FIELDS}
