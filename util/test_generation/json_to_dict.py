import json

def json_to_test_case(json_path):
    with open(json_path, "r") as f:
        data = json.load(f)

    # Fix request keys
    requests = {}

    for key, value in data["requests"].items():
        p, n = key[1:-1].split(", ")
        requests[(p, n)] = value

    # Return values in expected format
    return data["nodes"], data["partitions"], data["k_safety"], requests, data["comm_costs"]