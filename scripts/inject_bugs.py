"""
inject_bugs.py — Build the HLS executable bug-repair benchmark.

Combines Chrysalis-HLS bug specs with CHStone self-checking programs to
produce instances where:
  - buggy/  : CHStone source with one injected bug (oracle fails, exit != 0)
  - correct/: original CHStone source                (oracle passes, exit == 0)

Outputs benchmark_meta.json to OUTPUT_DIR.

Usage:
  python3 inject_bugs.py

Prerequisites (set paths below or via env vars):
  CHRYSALIS_DIR  — path to Chrysalis-HLS/HLS_Bug_Dataset/CHStone
  CHSTONE_DIR    — path to patmos_hls/benchmarks/CHStone (or any CHStone clone)
"""

import json
import os
import shutil
import subprocess
import glob

CHRYSALIS_DIR = os.environ.get(
    "CHRYSALIS_DIR",
    os.path.expanduser("~/Chrysalis-HLS/HLS_Bug_Dataset/CHStone")
)
CHSTONE_DIR = os.environ.get(
    "CHSTONE_DIR",
    os.path.expanduser("~/patmos_hls/benchmarks/CHStone")
)
OUTPUT_DIR = os.environ.get(
    "OUTPUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "benchmarks", "hls")
)

# Each CHStone benchmark compiles via a single entry .c file that #includes the rest.
# Compiling all *.c files directly causes duplicate-symbol errors.
BENCH_ENTRY_FILE = {
    "aes":      "aes.c",
    "adpcm":    "adpcm.c",
    "blowfish": "blowfish.c",
    "gsm":      "gsm.c",
    "sha":      "sha.c",
    "dfadd":    "dfadd.c",
    "dfmul":    "dfmul.c",
    "dfdiv":    "dfdiv.c",
    "dfsin":    "dfsin.c",
    "mips":     "mips.c",
    "motion":   "motion.c",
}

# Map Chrysalis function names → CHStone benchmark subdirectory
FUNC_TO_BENCHMARK = {
    "AddRoundKey": "aes",
    "AddRoundKey_InversMixColumn": "aes",
    "ByteSub_ShiftRow": "aes",
    "KeySchedule": "aes",
    "MixColumn_AddRoundKey": "aes",
    "SubByte": "aes",
    "InversShiftRow_ByteSub": "aes",
    "aes_main": "aes",
    "BF_set_key": "blowfish",
    "blowfish_main": "blowfish",
    "adpcm_main": "adpcm",
    "encode": "adpcm",
    "decode": "adpcm",
    "buf_getb": "adpcm",
    "buf_getv": "adpcm",
    "filtep": "adpcm",
    "filtez": "adpcm",
    "logsch": "adpcm",
    "logscl": "adpcm",
    "scalel": "adpcm",
    "uppol1": "adpcm",
    "uppol2": "adpcm",
    "upzero": "adpcm",
    "quantl": "adpcm",
    "sha_transform": "sha",
    "sha_update": "sha",
    "sha_final": "sha",
    "sha_init": "sha",
    "sha_stream": "sha",
    "Gsm_LPC_Analysis": "gsm",
    "Reflection_coefficients": "gsm",
    "gsm_abs": "gsm",
    "gsm_add": "gsm",
    "gsm_div": "gsm",
    "gsm_mult": "gsm",
    "gsm_mult_r": "gsm",
    "addFloat64Sigs": "dfadd",
    "subFloat64Sigs": "dfadd",
    "normalizeRoundAndPackFloat64": "dfadd",
    "roundAndPackFloat64": "dfadd",
    "packFloat64": "dfadd",
    "float64_add": "dfadd",
    "float64_abs": "dfadd",
    "ullong_to_double": "dfadd",
    "abs": "dfadd",
}

TARGET_BUG_TYPES = ["OOB", "INIT", "SHFT", "INF", "USE", "MLU", "ZERO", "BUF"]


def compile_and_run(bench_dir, bench_name):
    entry = BENCH_ENTRY_FILE.get(bench_name)
    if entry is None:
        return None, "unknown_bench", f"No entry file for {bench_name}"
    entry_path = os.path.join(bench_dir, entry)
    if not os.path.exists(entry_path):
        return None, "entry_missing", f"{entry} not found"
    binary = os.path.join(bench_dir, "test_binary")
    result = subprocess.run(
        ["gcc", "-O0", "-o", binary, entry_path, "-lm"],
        capture_output=True, timeout=30
    )
    if result.returncode != 0:
        return None, "compile_fail", result.stderr.decode()[:200]
    try:
        run_result = subprocess.run([binary], capture_output=True, timeout=10)
        return run_result.returncode, "ok", ""
    except subprocess.TimeoutExpired:
        # INF-type bugs cause infinite loops — detected as bug (non-zero exit)
        return -1, "timeout", "timeout (INF bug detected)"


def find_file_containing(chstone_bench_dir, code_line):
    first_line = code_line.strip().split('\n')[0].strip()
    for fpath in glob.glob(os.path.join(chstone_bench_dir, "*.c")):
        with open(fpath) as f:
            if first_line in f.read():
                return fpath
    return None


def inject_bug(source_path, original_code, faulty_code):
    with open(source_path) as f:
        content = f.read()
    orig_stripped = original_code.strip()
    if orig_stripped not in content:
        return False
    new_content = content.replace(orig_stripped, faulty_code.strip(), 1)
    with open(source_path, 'w') as f:
        f.write(new_content)
    return True


def create_instances(max_per_bug_type=7):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    instances = []
    counts = {bt: 0 for bt in TARGET_BUG_TYPES}
    skips = []

    for func_name in sorted(os.listdir(CHRYSALIS_DIR)):
        if func_name not in FUNC_TO_BENCHMARK:
            continue
        bench_name = FUNC_TO_BENCHMARK[func_name]
        chstone_bench_dir = os.path.join(CHSTONE_DIR, bench_name)
        bugs_dir = os.path.join(CHRYSALIS_DIR, func_name, "Bugs")
        if not os.path.exists(bugs_dir):
            continue

        for bug_file in sorted(os.listdir(bugs_dir)):
            if not bug_file.endswith(".txt"):
                continue
            with open(os.path.join(bugs_dir, bug_file)) as f:
                spec = json.load(f)
            if spec["Error Size"] != 1:
                continue
            bug_type = spec["Error Specification"][0]["Error Type"]
            if bug_type not in TARGET_BUG_TYPES:
                continue
            if counts[bug_type] >= max_per_bug_type:
                continue

            original_code = spec["Error Specification"][0]["Original Code"]
            faulty_code   = spec["Error Specification"][0]["Faulty Code"]
            instance_name = f"{func_name}_{bug_type}"
            inst_dir = os.path.join(OUTPUT_DIR, instance_name)

            if os.path.exists(inst_dir):
                shutil.rmtree(inst_dir)

            # Verify correct version passes
            correct_dir = os.path.join(inst_dir, "correct")
            shutil.copytree(chstone_bench_dir, correct_dir)
            rc, reason, err = compile_and_run(correct_dir, bench_name)
            if rc != 0:
                skips.append(f"{instance_name}: correct fails ({reason}: {err})")
                shutil.rmtree(inst_dir)
                continue

            # Find which file to patch
            target_file = find_file_containing(chstone_bench_dir, original_code)
            if target_file is None:
                skips.append(f"{instance_name}: original code not found")
                shutil.rmtree(inst_dir)
                continue

            # Create buggy dir and inject
            buggy_dir = os.path.join(inst_dir, "buggy")
            shutil.copytree(chstone_bench_dir, buggy_dir)
            buggy_target = os.path.join(buggy_dir, os.path.basename(target_file))
            if not inject_bug(buggy_target, original_code, faulty_code):
                skips.append(f"{instance_name}: injection failed")
                shutil.rmtree(inst_dir)
                continue

            # Verify buggy version fails
            rc, reason, err = compile_and_run(buggy_dir, bench_name)
            if rc is None:
                skips.append(f"{instance_name}: buggy compile fail: {err}")
                shutil.rmtree(inst_dir)
                continue
            if rc == 0:
                skips.append(f"{instance_name}: bug not detected by oracle")
                shutil.rmtree(inst_dir)
                continue

            # Save metadata
            meta = {
                "name": instance_name,
                "function": func_name,
                "benchmark": bench_name,
                "bug_type": bug_type,
                "buggy_dir": buggy_dir,
                "correct_dir": correct_dir,
                "entry_file": BENCH_ENTRY_FILE[bench_name],
                "target_file": os.path.basename(target_file),
                "original_code": original_code,
                "faulty_code": faulty_code,
            }
            with open(os.path.join(inst_dir, "meta.json"), 'w') as f:
                json.dump(meta, f, indent=2)

            instances.append(meta)
            counts[bug_type] += 1
            print(f"  OK: {instance_name} [{bug_type}]")

    with open(os.path.join(OUTPUT_DIR, "benchmark_meta.json"), 'w') as f:
        json.dump(instances, f, indent=2)

    print(f"\n=== RESULTS ===")
    print(f"Total instances: {len(instances)}")
    for bt, n in counts.items():
        print(f"  {bt}: {n}")
    print(f"\nSkipped: {len(skips)}")
    for s in skips[:20]:
        print(f"  - {s}")
    if len(skips) > 20:
        print(f"  ... and {len(skips)-20} more")


if __name__ == "__main__":
    create_instances(max_per_bug_type=7)
