"""
run_rtl_repair.py — RTL LLM-based bug repair pipeline.

For each Verilog instance in benchmark_meta.json:
  1. Read the buggy .v file
  2. Call GPT-4o N times to get N candidate patches
  3. Validate each patch by comparing iVerilog simulation output to golden trace
  4. Record results with checkpointing

Usage:
  export OPENAI_API_KEY=sk-...
  cd ~/iccd2026
  python3 scripts/run_rtl_repair.py --meta benchmarks/rtl/benchmark_meta.json \
      --output results/rtl_results.json --n_runs 5
"""

import json
import os
import argparse
import subprocess
import tempfile
import time
import re

import openai

client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

RTL_SYSTEM_PROMPT = (
    "You are an expert RTL hardware designer with deep knowledge of Verilog. "
    "You will be given a buggy Verilog source file. "
    "The file contains exactly one bug. Your task is to identify and fix the bug. "
    "Return ONLY the complete corrected Verilog source file. "
    "Do not include any explanation, markdown formatting, or code fences. "
    "Return raw Verilog code only."
)


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def call_llm(buggy_code: str, temperature: float = 0.8) -> str:
    user_prompt = (
        "The following Verilog file contains exactly one bug. "
        "Fix it and return the complete corrected file.\n\n"
        f"Buggy Verilog:\n{buggy_code}"
    )
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": RTL_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=4096,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"  API error attempt {attempt + 1}: {e}")
            time.sleep(5)
    return ""


def clean_response(response: str) -> str:
    response = response.strip()
    response = re.sub(r'^```(?:verilog|v)?\n?', '', response)
    response = re.sub(r'\n?```$', '', response)
    return response.strip()


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------

def clean_trace(trace: str) -> str:
    """Remove path-dependent and VCD-info lines."""
    lines = []
    for line in trace.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("/"):
            continue
        if "finish called" in stripped.lower():
            continue
        if "vcd info" in stripped.lower():
            continue
        lines.append(stripped)
    return "\n".join(lines)


def validate_patch(patch_code: str, instance_meta: dict, timeout: int = 30) -> dict:
    result = {"compiles": False, "passes": False, "timeout": False, "error": None}

    with tempfile.TemporaryDirectory() as tmpdir:
        patch_path = os.path.join(tmpdir, "patch.v")
        with open(patch_path, "w") as f:
            f.write(patch_code)

        binary = os.path.join(tmpdir, "sim")
        compile_cmd = [
            "iverilog", "-o", binary, patch_path, instance_meta["testbench"]
        ]

        try:
            compile_result = subprocess.run(
                compile_cmd, capture_output=True, text=True, timeout=30
            )
            if compile_result.returncode != 0:
                result["error"] = f"compile_fail: {compile_result.stderr[:150]}"
                return result
            result["compiles"] = True

            run_result = subprocess.run(
                ["vvp", binary],
                capture_output=True,
                text=True,
                cwd=tmpdir,
                timeout=timeout,
            )
            patch_trace = clean_trace(run_result.stdout)
            golden = clean_trace(instance_meta["golden_trace"])

            if patch_trace.strip() == golden.strip():
                result["passes"] = True
            else:
                result["error"] = "trace_mismatch"

        except subprocess.TimeoutExpired:
            result["timeout"] = True
            result["error"] = "timeout"
        except Exception as e:
            result["error"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_instance(instance_meta: dict, n_runs: int = 5) -> dict:
    print(f"\n[{instance_meta['name']}] benchmark={instance_meta['benchmark']}")

    with open(instance_meta["buggy_file"]) as f:
        buggy_code = f.read()

    patches = []
    for i in range(n_runs):
        print(f"    LLM call {i + 1}/{n_runs}...", end=" ", flush=True)
        response = call_llm(buggy_code)
        patch = clean_response(response)
        patches.append(patch)
        print("done")
        time.sleep(1)

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
        "project": instance_meta["project"],
        "benchmark": instance_meta["benchmark"],
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
    benchmark_filter: str = None,
):
    with open(benchmark_meta_path) as f:
        instances = json.load(f)

    if benchmark_filter:
        instances = [i for i in instances if i["benchmark"] == benchmark_filter]

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
                    "benchmark": inst["benchmark"],
                    "error": str(e),
                    "n_pass": 0,
                    "repair_success_rate": 0,
                }
            )

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

    by_bench: dict = {}
    for r in valid:
        b = r.get("benchmark", "unknown")
        by_bench.setdefault(b, []).append(r["repair_success_rate"])
    for b, rates in sorted(by_bench.items()):
        print(f"  {b}: {sum(rates)/len(rates):.3f} ({len(rates)} instances)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run GPT-4o LLM repair on the RTL benchmark"
    )
    parser.add_argument(
        "--meta",
        default="benchmarks/rtl/benchmark_meta.json",
        help="Path to benchmark_meta.json",
    )
    parser.add_argument(
        "--output", default="results/rtl_results.json", help="Output JSON path"
    )
    parser.add_argument("--n_runs", type=int, default=5, help="Patches per instance")
    parser.add_argument(
        "--start_from", type=int, default=0, help="Resume from instance index"
    )
    parser.add_argument(
        "--benchmark",
        default=None,
        help="Filter: cirfix or assignment4v",
    )
    args = parser.parse_args()

    os.makedirs("results", exist_ok=True)
    run_all(args.meta, args.output, args.n_runs, args.start_from, args.benchmark)
