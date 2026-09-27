#!/usr/bin/env bash
# setup.sh — Clone dependencies and build the HLS benchmark instances.
#
# Run once from the repo root before running any experiments:
#   bash setup.sh
#
# What it does:
#   1. Clones Chrysalis-HLS (Apache-2.0 bug specs)
#   2. Clones CHStone via patmos-hls (individual program copyrights; not redistributed here)
#   3. Runs inject_bugs.py to generate benchmarks/hls/  (41 executable instances)
#
# Prerequisites:
#   python3 >= 3.8, gcc
#   pip install openai   (for the repair scripts)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Cloning Chrysalis-HLS ==="
if [ ! -d "Chrysalis-HLS" ]; then
    git clone --depth 1 https://github.com/hls-edu/Chrysalis-HLS.git
else
    echo "  Already present."
fi

echo ""
echo "=== Cloning CHStone (via patmos-hls) ==="
if [ ! -d "patmos_hls" ]; then
    git clone --depth 1 https://github.com/t-crest/patmos-hls.git patmos_hls
else
    echo "  Already present."
fi

echo ""
echo "=== Building HLS benchmark instances ==="
CHRYSALIS_DIR="$SCRIPT_DIR/Chrysalis-HLS/HLS_Bug_Dataset/CHStone" \
CHSTONE_DIR="$SCRIPT_DIR/patmos_hls/benchmarks/CHStone" \
python3 scripts/inject_bugs.py

echo ""
echo "Setup complete."
echo "  HLS instances: benchmarks/hls/benchmark_meta.json"
echo ""
echo "Next step:"
echo "  export OPENAI_API_KEY=sk-..."
echo "  python3 scripts/run_hls_repair.py --n_runs 5 --output results/hls_results.json"
