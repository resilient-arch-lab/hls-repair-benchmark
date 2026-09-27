"""
build_rtl_meta.py — Build the RTL executable bug-repair benchmark.

Collects Verilog bug instances from CirFix and Assignment4V datasets,
verifies each using iVerilog simulation, and saves metadata + golden traces
to benchmark_meta.json.

Usage:
  python3 build_rtl_meta.py

Prerequisites (adjust paths below or set env vars):
  CIRFIX_DIR  — path to cirfix-fpga/benchmarks/cirfix
  A4V_DIR     — path to cirfix-fpga/benchmarks/Assignment4V
"""

import json
import os
import subprocess
import tempfile
import glob

CIRFIX_DIR = os.environ.get(
    "CIRFIX_DIR",
    os.path.expanduser(
        "~/srepair/cirfix-fpga-mut/cirfix-fpga/benchmarks/cirfix"
    ),
)
A4V_DIR = os.environ.get(
    "A4V_DIR",
    os.path.expanduser(
        "~/srepair/cirfix-fpga-mut/cirfix-fpga/benchmarks/Assignment4V"
    ),
)
OUTPUT_DIR = os.path.expanduser("~/iccd2026/benchmarks/rtl")


def clean_trace(trace: str) -> str:
    """Remove path-dependent and VCD-info lines from simulation output."""
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


def get_golden_trace(design_v, testbench_v, all_files=None, timeout=30):
    """Simulate design_v + testbench_v with iVerilog; return cleaned stdout."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy all files from the design directory so $dumpfile works
        if all_files:
            for src in all_files:
                dst = os.path.join(tmpdir, os.path.basename(src))
                import shutil
                shutil.copy2(src, dst)

        binary = os.path.join(tmpdir, "sim")
        cmd = ["iverilog", "-o", binary, design_v, testbench_v]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            return None, f"compile_fail: {result.stderr.decode()[:100]}"

        run = subprocess.run(
            ["vvp", binary],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            timeout=timeout,
        )
        return clean_trace(run.stdout), None


def build_cirfix_instances():
    instances = []
    for project in sorted(os.listdir(CIRFIX_DIR)):
        project_dir = os.path.join(CIRFIX_DIR, project)
        if not os.path.isdir(project_dir):
            continue

        testbenches = glob.glob(os.path.join(project_dir, "*_tb*.v"))
        if not testbenches:
            print(f"  SKIP {project}: no testbench")
            continue
        testbench = testbenches[0]

        correct_v = os.path.join(project_dir, f"{project}.v")
        if not os.path.exists(correct_v):
            print(f"  SKIP {project}: no correct design ({project}.v)")
            continue

        buggy_files = glob.glob(os.path.join(project_dir, "*buggy*.v"))
        if not buggy_files:
            print(f"  SKIP {project}: no buggy files")
            continue

        all_project_files = glob.glob(os.path.join(project_dir, "*.v"))
        golden_trace, err = get_golden_trace(
            correct_v, testbench, all_files=all_project_files
        )
        if golden_trace is None:
            print(f"  SKIP {project}: correct version fails ({err})")
            continue

        for buggy_v in sorted(buggy_files):
            buggy_trace, err = get_golden_trace(
                buggy_v, testbench, all_files=all_project_files
            )
            if buggy_trace is None:
                print(f"  SKIP {os.path.basename(buggy_v)}: compile fail")
                continue
            if buggy_trace.strip() == golden_trace.strip():
                print(f"  SKIP {os.path.basename(buggy_v)}: bug not detected")
                continue

            instance_name = os.path.basename(buggy_v).replace(".v", "")
            meta = {
                "name": instance_name,
                "project": project,
                "benchmark": "cirfix",
                "buggy_file": buggy_v,
                "correct_file": correct_v,
                "testbench": testbench,
                "golden_trace": golden_trace,
            }
            instances.append(meta)
            print(f"  OK: {instance_name}")

    return instances


def build_a4v_instances():
    instances = []
    for design in sorted(os.listdir(A4V_DIR)):
        design_dir = os.path.join(A4V_DIR, design)
        if not os.path.isdir(design_dir) or design.startswith("_"):
            continue

        for variant in sorted(os.listdir(design_dir)):
            variant_dir = os.path.join(design_dir, variant)
            if not os.path.isdir(variant_dir):
                continue

            buggy_dir = os.path.join(variant_dir, "buggy")
            fixed_dir = os.path.join(variant_dir, "fixed")
            if not os.path.exists(buggy_dir) or not os.path.exists(fixed_dir):
                continue

            buggy_files = glob.glob(os.path.join(buggy_dir, "*.v"))
            buggy_v = [f for f in buggy_files if "_tb" not in f]
            tb_files = [f for f in buggy_files if "_tb" in f]

            if not buggy_v or not tb_files:
                print(f"  SKIP {design}/{variant}: missing files")
                continue

            buggy_v = buggy_v[0]
            testbench = tb_files[0]

            fixed_files = glob.glob(os.path.join(fixed_dir, "*.v"))
            correct_v = [f for f in fixed_files if "_tb" not in f]
            if not correct_v:
                continue
            correct_v = correct_v[0]

            golden_trace, err = get_golden_trace(correct_v, testbench)
            if golden_trace is None:
                print(f"  SKIP {design}/{variant}: correct fails ({err})")
                continue

            buggy_trace, err = get_golden_trace(buggy_v, testbench)
            if buggy_trace is None:
                print(f"  SKIP {design}/{variant}: buggy compile fail")
                continue
            if buggy_trace.strip() == golden_trace.strip():
                print(f"  SKIP {design}/{variant}: bug not detected")
                continue

            instance_name = f"{design}_{variant}"
            meta = {
                "name": instance_name,
                "project": design,
                "benchmark": "assignment4v",
                "buggy_file": buggy_v,
                "correct_file": correct_v,
                "testbench": testbench,
                "golden_trace": golden_trace,
            }
            instances.append(meta)
            print(f"  OK: {instance_name}")

    return instances


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=== CirFix Benchmarks ===")
    cirfix = build_cirfix_instances()

    print("\n=== Assignment4V Benchmarks ===")
    a4v = build_a4v_instances()

    all_instances = cirfix + a4v

    output_path = os.path.join(OUTPUT_DIR, "benchmark_meta.json")
    with open(output_path, "w") as f:
        json.dump(all_instances, f, indent=2)

    print(f"\n=== SUMMARY ===")
    print(f"CirFix instances:      {len(cirfix)}")
    print(f"Assignment4V instances:{len(a4v)}")
    print(f"Total:                 {len(all_instances)}")
    print(f"Saved to {output_path}")
