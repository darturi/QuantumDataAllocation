"""
Core experiment harness for QuantumClean (revised in Phase 5).

Loads pre-generated test cases from disk, runs every registered solver on
each case, computes cost / validity / BQM stats / optimality gap, and writes
results incrementally to a JSON file.

Phase 5 changes vs. the old harness:

* ``optimality_gap`` is reported as both absolute (``cost_optimal - ilp_cost``)
  and relative (with sensible behaviour when ``ilp_cost == 0``: relative is
  0.0 iff the solver also returned 0, ``None`` otherwise).
* Result entries include ``k_safety_violations`` and ``capacity_overruns``
  so "invalid" results carry signal instead of a single boolean.
* ``time_ms`` is split into ``wall_time_ms`` (always present) and
  ``qpu_anneal_time_per_sample_us`` / ``ilp_branch_nodes`` (where
  applicable).  Plotting these side-by-side is the *caller's* responsibility.
* ``_NumpyEncoder`` is used on every JSON write.
"""

import json
import re
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np

from util.calculate_solution_cost import (
    calculate_solution_cost,
    is_valid_solution,
)
from util.test_generation.json_to_dict import (
    json_to_test_case,
    load_test_case_metadata,
)


class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


def _write_json(path, payload):
    with open(path, "w") as f:
        json.dump(payload, f, indent=4, cls=_NumpyEncoder)


# ---------------------------------------------------------------------------
# Constraint diagnostics
# ---------------------------------------------------------------------------

def _violations(nodes, partitions, k_safety, sample_dict):
    """Return (k_safety_violations, capacity_overruns) for a flat A_p_n dict."""
    if sample_dict is None:
        return None, None
    k_viol = 0
    for p in partitions:
        cnt = sum(int(sample_dict.get(f"A_{p}_{n}", 0)) for n in nodes)
        if cnt != k_safety:
            k_viol += 1
    overruns = 0
    for n, cap in nodes.items():
        load = sum(
            int(sample_dict.get(f"A_{p}_{n}", 0)) * partitions[p]
            for p in partitions
        )
        if load > cap:
            overruns += 1
    return k_viol, overruns


def _to_flat(sample_obj):
    if sample_obj is None:
        return None
    return sample_obj.sample if hasattr(sample_obj, "sample") else sample_obj


def _gap(cost, ilp_cost):
    """
    Return (absolute_gap, relative_gap).

    * absolute is always defined when both are defined.
    * relative is 0.0 if both are 0, (cost - ilp)/ilp if ilp > 0,
      else None (we don't divide by 0 silently).
    """
    if cost is None or ilp_cost is None:
        return None, None
    abs_gap = cost - ilp_cost
    if ilp_cost > 0:
        rel = round(abs_gap / ilp_cost, 4)
    elif cost == 0:
        rel = 0.0
    else:
        rel = None
    return abs_gap, rel


# ---------------------------------------------------------------------------
# Test-case discovery (unchanged from the previous version)
# ---------------------------------------------------------------------------

def discover_test_cases(test_bank_dir, tier=None, node_counts=None,
                        partition_counts=None, max_cases=None):
    test_bank_dir = Path(test_bank_dir)
    search_root = test_bank_dir / tier if tier else test_bank_dir
    paths = sorted(search_root.rglob("*.json"))

    if node_counts is not None or partition_counts is not None:
        filtered = []
        for p in paths:
            m = re.match(r"n(\d+)_p(\d+)", p.parent.name)
            if not m:
                continue
            n, pp = int(m.group(1)), int(m.group(2))
            if node_counts is not None and n not in node_counts:
                continue
            if partition_counts is not None and pp not in partition_counts:
                continue
            filtered.append(p)
        paths = filtered

    if max_cases is not None:
        paths = paths[:max_cases]

    return paths


# ---------------------------------------------------------------------------
# Per-solver execution
# ---------------------------------------------------------------------------

def _run_ilp(solver_class, nodes, partitions, k_safety, requests, comm_costs):
    try:
        solver = solver_class(nodes, partitions, k_safety, requests, comm_costs)
        t_ms, raw_result = solver.solve()
        flat = None
        if raw_result is not None:
            flat = {
                f"A_{p}_{n}": v
                for p, nd in raw_result.items() for n, v in nd.items()
            }
        cost = calculate_solution_cost(
            nodes, partitions, k_safety, requests, comm_costs, flat
        )
        valid = is_valid_solution(
            nodes, partitions, k_safety, requests, comm_costs, flat
        )
        k_viol, overruns = _violations(nodes, partitions, k_safety, flat)
        return {
            "cost": cost,
            "valid": valid,
            "k_safety_violations": k_viol,
            "capacity_overruns": overruns,
            "wall_time_ms": round(t_ms, 1) if t_ms is not None else None,
            "error": None,
        }
    except Exception as e:
        return {
            "cost": None, "valid": False,
            "k_safety_violations": None, "capacity_overruns": None,
            "wall_time_ms": None, "error": str(e),
        }


def _run_sqa(solver_class, nodes, partitions, k_safety, requests, comm_costs,
             num_reads, num_sweeps, beta_range, solver_kwargs=None):
    try:
        solver_kwargs = solver_kwargs or {}
        solver = solver_class(nodes, partitions, k_safety, requests, comm_costs,
                              **solver_kwargs)
        bqm = solver.build_bqm()
        bqm_vars = len(bqm.variables)
        bqm_interactions = len(bqm.quadratic)

        kw = dict(num_reads=num_reads, num_sweeps=num_sweeps)
        if beta_range is not None:
            kw["beta_range"] = beta_range

        t_ms, result = solver.solve(**kw)
        flat = _to_flat(result)
        cost = calculate_solution_cost(
            nodes, partitions, k_safety, requests, comm_costs, flat
        )
        valid = is_valid_solution(
            nodes, partitions, k_safety, requests, comm_costs, flat
        )
        k_viol, overruns = _violations(nodes, partitions, k_safety, flat)
        return {
            "cost": cost,
            "valid": valid,
            "k_safety_violations": k_viol,
            "capacity_overruns": overruns,
            "wall_time_ms": round(t_ms, 1),
            "bqm_variables": bqm_vars,
            "bqm_interactions": bqm_interactions,
            "lambda_1": getattr(solver, "lambda_1", None),
            "lambda_2": getattr(solver, "lambda_2", None),
            "error": None,
        }
    except Exception as e:
        return {
            "cost": None, "valid": False,
            "k_safety_violations": None, "capacity_overruns": None,
            "wall_time_ms": None,
            "bqm_variables": None, "bqm_interactions": None,
            "lambda_1": None, "lambda_2": None,
            "error": str(e),
        }


def _run_qpu(solver_class, nodes, partitions, k_safety, requests, comm_costs,
             num_reads, annealing_time, chain_strength, solver_kwargs=None):
    try:
        solver_kwargs = solver_kwargs or {}
        solver = solver_class(nodes, partitions, k_safety, requests, comm_costs,
                              **solver_kwargs)
        bqm = solver.build_bqm()
        bqm_vars = len(bqm.variables)
        bqm_interactions = len(bqm.quadratic)

        kw = dict(num_reads=num_reads, annealing_time=annealing_time)
        if chain_strength is not None:
            kw["chain_strength"] = chain_strength

        t_ms, result = solver.solve(**kw)
        flat = _to_flat(result)
        cost = calculate_solution_cost(
            nodes, partitions, k_safety, requests, comm_costs, flat
        )
        valid = is_valid_solution(
            nodes, partitions, k_safety, requests, comm_costs, flat
        )
        k_viol, overruns = _violations(nodes, partitions, k_safety, flat)
        hw = solver.hardware_summary()
        return {
            "cost": cost, "valid": valid,
            "k_safety_violations": k_viol, "capacity_overruns": overruns,
            "wall_time_ms": round(t_ms, 1),
            "bqm_variables": bqm_vars,
            "bqm_interactions": bqm_interactions,
            "physical_qubits": hw.get("physical_qubits"),
            "chain_break_fraction": hw.get("chain_break_fraction"),
            "qpu_anneal_time_per_sample_us": hw.get("qpu_anneal_time_per_sample_us"),
            "lambda_1": getattr(solver, "lambda_1", None),
            "lambda_2": getattr(solver, "lambda_2", None),
            "error": None,
        }
    except Exception as e:
        return {
            "cost": None, "valid": False,
            "k_safety_violations": None, "capacity_overruns": None,
            "wall_time_ms": None,
            "bqm_variables": None, "bqm_interactions": None,
            "physical_qubits": None, "chain_break_fraction": None,
            "qpu_anneal_time_per_sample_us": None,
            "lambda_1": None, "lambda_2": None,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Main harness
# ---------------------------------------------------------------------------

def run_experiment(
    test_case_paths,
    solver_registry,
    output_dir,
    file_prefix="Experiment",
    num_reads=1000,
    num_sweeps=1000,
    beta_range=None,
    annealing_time=20,
    chain_strength=None,
    note=None,
    verbose=True,
):
    """Run every solver on every test case."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = output_dir.glob(f"{file_prefix}_*.json")
    numbers = [
        int(m.group(1))
        for f in existing
        if (m := re.search(rf"{file_prefix}_(\d+)\.json", f.name))
    ]
    file_num = max(numbers, default=0) + 1
    output_path = output_dir / f"{file_prefix}_{file_num}.json"

    solver_names = [s["name"] for s in solver_registry]
    has_sqa = any(s["type"] == "sqa" for s in solver_registry)
    has_qpu = any(s["type"] == "qpu" for s in solver_registry)

    metadata = {
        "date": date.today().isoformat(),
        "time": datetime.now().strftime("%H:%M:%S"),
        "total_cases": len(test_case_paths),
        "num_reads": num_reads,
        "solvers": solver_names,
        "harness_version": "phase5",
    }
    if has_sqa:
        metadata["num_sweeps"] = num_sweeps
    if has_qpu:
        metadata["annealing_time"] = annealing_time
        if chain_strength is not None:
            metadata["chain_strength"] = chain_strength

    output = {"metadata": metadata, "results": {}}
    if note:
        output["metadata"]["note"] = note
    _write_json(output_path, output)

    total = len(test_case_paths)
    sweep_start = time.perf_counter()

    for idx, tc_path in enumerate(test_case_paths, 1):
        tc_path = Path(tc_path)
        key = tc_path.stem

        nodes, partitions, k_safety, requests, comm_costs = json_to_test_case(
            str(tc_path)
        )
        tc_metadata = load_test_case_metadata(str(tc_path))

        entry = {
            "source_file": str(tc_path),
            "n_nodes": len(nodes),
            "n_partitions": len(partitions),
            "k_safety": k_safety,
            # Phase-5 + tightness extension: surface test-case metadata
            # (notably ``tightness``) so downstream analysis can stratify
            # results without re-reading the source JSON.  Each metadata
            # field becomes a top-level key on the entry, prefixed with
            # ``tc_`` to avoid colliding with solver-result keys.
            **{f"tc_{k}": v for k, v in tc_metadata.items()},
            "solvers": {},
        }

        ilp_cost = None

        for solver_desc in solver_registry:
            name = solver_desc["name"]
            cls = solver_desc["class"]
            solver_type = solver_desc["type"]
            solver_kwargs = solver_desc.get("kwargs", {})

            if solver_type == "ilp":
                result = _run_ilp(cls, nodes, partitions, k_safety, requests, comm_costs)
                if result["valid"] and result["cost"] is not None:
                    ilp_cost = result["cost"]
            elif solver_type == "sqa":
                result = _run_sqa(
                    cls, nodes, partitions, k_safety, requests, comm_costs,
                    num_reads, num_sweeps, beta_range, solver_kwargs,
                )
            elif solver_type == "qpu":
                result = _run_qpu(
                    cls, nodes, partitions, k_safety, requests, comm_costs,
                    num_reads, annealing_time, chain_strength, solver_kwargs,
                )
            else:
                raise ValueError(f"Unknown solver type: {solver_type!r}")

            abs_gap, rel_gap = _gap(result.get("cost"), ilp_cost)
            result["optimality_gap_absolute"] = abs_gap
            result["optimality_gap_relative"] = rel_gap
            entry["solvers"][name] = result

        output["results"][key] = entry
        _write_json(output_path, output)

        if verbose:
            elapsed = time.perf_counter() - sweep_start
            rate = idx / elapsed if elapsed > 0 else 0
            eta_total = (total - idx) / rate if rate > 0 else 0
            eta_min = int(eta_total // 60)
            eta_sec = int(eta_total % 60)
            status_parts = []
            for s in solver_registry:
                r = entry["solvers"][s["name"]]
                tag = "OK" if r.get("valid") else "X"
                gap = r.get("optimality_gap_absolute")
                if gap is not None and gap != 0:
                    tag = f"{tag}(+{gap})" if r.get("valid") else tag
                status_parts.append(f"{s['name']}={tag}")
            print(
                f"  [{idx}/{total}] {key}: {'  '.join(status_parts)}"
                f"  [ETA {eta_min}m{eta_sec:02d}s]"
            )

    elapsed_total = time.perf_counter() - sweep_start
    if verbose:
        print(f"\nCompleted {total} cases in {elapsed_total / 60:.1f} minutes.")
        print(f"Saved to: {output_path}")
    return output_path
