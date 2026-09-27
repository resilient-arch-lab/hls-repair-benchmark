"""
run_hls_repair.py — HLS LLM-based bug repair pipeline.

For each instance in benchmark_meta.json:
  1. Read the buggy target file
  2. Call GPT-4o N times to get N candidate patches
  3. Validate each patch with the CHStone execution oracle
  4. Record results with checkpointing (saves after every instance)

Usage:
  export OPENAI_API_KEY=sk-...
  cd ~/iccd2026
  python3 scripts/run_hls_repair.py --meta benchmarks/hls/benchmark_meta.json \
      --output results/hls_results.json --n_runs 5
"""

import json
import os
import argparse

from llm_client import get_n_patches
from validate_hls import validate_patch


def run_instance(instance_meta: dict, n_runs: int = 5) -> dict:
    print(f"\n[{instance_meta['name']}] bug_type={instance_meta['bug_type']}")

    buggy_file_path = os.path.join(
        instance_meta["buggy_dir"], instance_meta["target_file"]
    )
    with open(buggy_file_path) as f:
        buggy_code = f.read()

    patches = get_n_patches(buggy_code, n=n_runs)

    patch_results = []
    n_compile = 0
    n_pass = 0

    for i, patch in enumerate(patches):
        val = validate_patch(patch, instance_meta)
        if val["compiles"]:
            n_compile += 1
        if val["passes"]:
            n_pass += 1
        patch_results.append(
            {
                "patch": patch,
                "compiles": val["compiles"],
                "passes": val["passes"],
                "timeout": val["timeout"],
                "error": val["error"],
            }
        )
        status = (
            "PASS" if val["passes"] else ("TIMEOUT" if val["timeout"] else "FAIL")
        )
        print(f"    Run {i + 1}: {status}")

    distinct = len(set(r["patch"] for r in patch_results))

    result = {
        "name": instance_meta["name"],
        "function": instance_meta["function"],
        "benchmark": instance_meta["benchmark"],
        "bug_type": instance_meta["bug_type"],
        "n_runs": n_runs,
        "n_compile": n_compile,
        "n_pass": n_pass,
        "distinct_patches": distinct,
        "repair_success_rate": n_pass / n_runs,
        "compile_rate": n_compile / n_runs,
        "solution_multiplicity": distinct / n_runs,
        "patch_results": patch_results,
    }

    print(f"  Result: {n_pass}/{n_runs} pass | {distinct} distinct patches")
    return result


def run_all(
    benchmark_meta_path: str,
    output_path: str,
    n_runs: int = 5,
    start_from: int = 0,
    bug_type_filter: str = None,
):
    with open(benchmark_meta_path) as f:
        instances = json.load(f)

    if bug_type_filter:
        instances = [i for i in instances if i["bug_type"] == bug_type_filter]

    instances = instances[start_from:]

    results = []
    if os.path.exists(output_path):
        with open(output_path) as f:
            results = json.load(f)
        print(f"Resuming from {len(results)} existing results")

    print(f"Running {len(instances)} instances, {n_runs} LLM calls each")
    print(f"Estimated API calls: {len(instances) * n_runs}")

    for i, inst in enumerate(instances):
        print(f"\n--- Instance {i + 1 + start_from}/{len(instances) + start_from} ---")
        try:
            result = run_instance(inst, n_runs=n_runs)
            results.append(result)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append(
                {
                    "name": inst["name"],
                    "bug_type": inst["bug_type"],
                    "error": str(e),
                    "n_pass": 0,
                    "repair_success_rate": 0,
                }
            )

        # Checkpoint: save after every instance
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  Saved to {output_path}")

    print("\n=== SUMMARY ===")
    valid = [r for r in results if "repair_success_rate" in r]
    avg_rate = (
        sum(r["repair_success_rate"] for r in valid) / len(valid) if valid else 0
    )
    print(f"Total instances: {len(valid)}")
    print(f"Avg repair success rate: {avg_rate:.3f}")

    by_type: dict = {}
    for r in valid:
        bt = r.get("bug_type", "unknown")
        by_type.setdefault(bt, []).append(r["repair_success_rate"])
    for bt, rates in sorted(by_type.items()):
        print(f"  {bt}: {sum(rates)/len(rates):.3f} ({len(rates)} instances)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run GPT-4o LLM repair on the HLS benchmark"
    )
    parser.add_argument(
        "--meta",
        default="benchmarks/hls/benchmark_meta.json",
        help="Path to benchmark_meta.json",
    )
    parser.add_argument(
        "--output", default="results/hls_results.json", help="Output JSON path"
    )
    parser.add_argument("--n_runs", type=int, default=5, help="Patches per instance")
    parser.add_argument(
        "--start_from", type=int, default=0, help="Resume from instance index"
    )
    parser.add_argument(
        "--bug_type", default=None, help="Filter to one bug type (e.g. OOB)"
    )
    args = parser.parse_args()

    os.makedirs("results", exist_ok=True)
    run_all(args.meta, args.output, args.n_runs, args.start_from, args.bug_type)
