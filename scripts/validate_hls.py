"""
validate_hls.py — Execution-based oracle for HLS patch validation.

Given an LLM patch and benchmark metadata, this module:
  1. Copies the buggy source directory to a temp location
  2. Replaces the target file with the LLM-generated patch
  3. Compiles via the benchmark's entry file with gcc -O0
  4. Runs the binary and checks the exit code (0 = pass, non-zero = fail)
"""

import subprocess
import os
import shutil
import tempfile


def validate_patch(patch_code: str, instance_meta: dict, timeout: int = 10) -> dict:
    """
    Returns:
        {
            "compiles": bool,
            "passes": bool,
            "timeout": bool,
            "error": str | None,
        }
    """
    result = {
        "compiles": False,
        "passes": False,
        "timeout": False,
        "error": None,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy the full buggy directory so all includes/helpers are present
        shutil.copytree(instance_meta["buggy_dir"], tmpdir, dirs_exist_ok=True)

        # Replace the target file with the LLM patch
        target_path = os.path.join(tmpdir, instance_meta["target_file"])
        with open(target_path, "w") as f:
            f.write(patch_code)

        # Compile via the single entry file (which #includes the rest)
        entry_path = os.path.join(tmpdir, instance_meta["entry_file"])
        binary = os.path.join(tmpdir, "test_binary")
        compile_result = subprocess.run(
            ["gcc", "-O0", "-o", binary, entry_path, "-lm"],
            capture_output=True,
            timeout=30,
        )

        if compile_result.returncode != 0:
            result["error"] = (
                f"compile_fail: {compile_result.stderr.decode()[:150]}"
            )
            return result

        result["compiles"] = True

        # Run and check exit code
        try:
            run_result = subprocess.run(
                [binary], capture_output=True, timeout=timeout
            )
            if run_result.returncode == 0:
                result["passes"] = True
            else:
                result["error"] = f"test_fail: exit {run_result.returncode}"
        except subprocess.TimeoutExpired:
            result["timeout"] = True
            result["error"] = "timeout"

    return result
