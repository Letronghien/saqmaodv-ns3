#!/bin/bash
# Setup QSAQMAODV (Queue-State-Aware Self-Adaptive Q-learning Multipath AODV)
# Run AFTER setup-from-scratch.sh has completed successfully.
#
# Usage:
#   bash scripts/setup/setup-qsaqmaodv.sh
#
# Or with explicit NS3_DIR:
#   NS3_DIR=/path/to/ns-3.40 bash scripts/setup/setup-qsaqmaodv.sh

set -e

# ===== Locate NS3_DIR =====
if [ -z "${NS3_DIR:-}" ]; then
    for cand in \
        "$HOME/ns-allinone-3.40/ns-3.40" \
        "$HOME/ns-3-allinone/ns-3.40" \
        "$HOME/workspace/ns-allinone-3.40/ns-3.40" \
        "$HOME/ns-3.40"; do
        if [ -d "$cand" ] && [ -f "$cand/ns3" ] && [ -d "$cand/src/aodv" ]; then
            NS3_DIR="$cand"
            break
        fi
    done
fi
if [ -z "${NS3_DIR:-}" ]; then
    echo "ERROR: ns-3.40 not found. Set NS3_DIR manually."
    exit 1
fi

PKG_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(cd "$PKG_DIR/../.." && pwd)
export NS3_DIR PROJECT_ROOT

echo "========================================"
echo "  Setup QSAQMAODV"
echo "========================================"
echo "NS3_DIR:      $NS3_DIR"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo ""

# ===== Guard: require QMAODV to be installed first =====
if [ ! -d "$NS3_DIR/src/qmaodv" ]; then
    echo "ERROR: src/qmaodv not found."
    echo "  Run setup-from-scratch.sh first."
    exit 1
fi

# ===== Step 1: Backup existing QSAQMAODV if any =====
echo "[1/6] Backup existing qsaqmaodv (if any)..."
TS=$(date +%Y%m%d-%H%M%S)
BAK="$HOME/ns3-backup-qsaqmaodv-${TS}"
mkdir -p "$BAK"
if [ -d "$NS3_DIR/src/qsaqmaodv" ]; then
    mv "$NS3_DIR/src/qsaqmaodv" "$BAK/"
    echo "  Backed up src/qsaqmaodv → $BAK"
fi

# ===== Step 2: Create QSAQMAODV skeleton (clone from AODV) =====
echo ""
echo "[2/6] Create QSAQMAODV skeleton (clone src/aodv -> src/qsaqmaodv)..."
cd "$NS3_DIR"
SRC=src/aodv
DST=src/qsaqmaodv
cp -r "$SRC" "$DST"
cd "$DST"

# Rename files: aodv -> qsaqmaodv
find . -depth -name "aodv*" | while read -r f; do
    new=$(echo "$f" | sed 's|/aodv|/qsaqmaodv|; s|^aodv|qsaqmaodv|')
    [ "$f" != "$new" ] && mv "$f" "$new"
done

# Replace text in files
find . -type f \( -name "*.h" -o -name "*.cc" -o -name "CMakeLists.txt" \) -print0 | \
    xargs -0 sed -i \
        -e 's/aodv/qsaqmaodv/g' \
        -e 's/Aodv/Qsaqmaodv/g' \
        -e 's/AODV/QSAQMAODV/g'

cd "$NS3_DIR"
echo "  Created src/qsaqmaodv/"

# ===== Step 3: Copy qsaqmaodv-qtable files + update CMakeLists =====
echo ""
echo "[3/6] Copy qsaqmaodv-qtable.{h,cc} + update CMakeLists..."

# Copy qtable files
cp "$PROJECT_ROOT/files/qsaqmaodv-qtable.h"  "$NS3_DIR/src/qsaqmaodv/model/"
cp "$PROJECT_ROOT/files/qsaqmaodv-qtable.cc" "$NS3_DIR/src/qsaqmaodv/model/"
echo "  Copied qsaqmaodv-qtable.{h,cc}"

CM="$NS3_DIR/src/qsaqmaodv/CMakeLists.txt"

# Add qtable source files
if ! grep -q "qsaqmaodv-qtable" "$CM"; then
    sed -i "s|model/qsaqmaodv-rtable.cc|model/qsaqmaodv-rtable.cc\n    model/qsaqmaodv-qtable.cc|" "$CM"
    sed -i "s|model/qsaqmaodv-rtable.h|model/qsaqmaodv-rtable.h\n    model/qsaqmaodv-qtable.h|" "$CM"
    echo "  Added qtable to CMakeLists"
fi

# Add energy + wifi dependencies (needed for GetEnergyFraction + GetQueueOccupancy)
if ! grep -q "libenergy" "$CM"; then
    sed -i 's|libcore|libcore\n  libenergy|' "$CM" 2>/dev/null || true
    echo "  Added libenergy dependency"
fi
if ! grep -q "libwifi" "$CM"; then
    sed -i 's|libcore|libcore\n  libwifi|' "$CM" 2>/dev/null || true
    echo "  Added libwifi dependency"
fi

# ===== Step 4: Apply QSAQMAODV patches =====
echo ""
echo "[4/6] Apply QSAQMAODV patches..."
for p in \
    apply-qsaqmaodv-2.3a.py \
    apply-qsaqmaodv-2.3b.py \
    apply-qsaqmaodv-2.3c.py \
    apply-qsaqmaodv-2.3d.py \
    apply-qsaqmaodv-fix-v2.py; do
    echo "  $p"
    python3 "$PROJECT_ROOT/scripts/patches/$p"
done

# ===== Step 5: Fix ns-3.40 energy namespace =====
# ns-3.40 keeps energy types in ns3:: directly (not ns3::energy::)
echo ""
echo "[5/6] Fix ns-3.40 energy namespace in qsaqmaodv-routing-protocol.cc..."
QSRP="$NS3_DIR/src/qsaqmaodv/model/qsaqmaodv-routing-protocol.cc"
if [ -d "$NS3_DIR/src/energy" ] && \
   ! grep -q "namespace energy" "$NS3_DIR/src/energy/model/basic-energy-source.h" 2>/dev/null; then
    echo "  ns-3.40 detected — stripping energy:: namespace qualifier"
    sed -i 's/ns3::energy::/ns3::/g' "$QSRP"
    sed -i 's/Ptr<EnergySourceContainer>/Ptr<ns3::EnergySourceContainer>/g' "$QSRP" 2>/dev/null || true
    sed -i 's/Ptr<BasicEnergySource>/Ptr<ns3::BasicEnergySource>/g' "$QSRP" 2>/dev/null || true
else
    echo "  ns-3.42+ detected — no namespace fix needed"
fi

# ===== Step 6: Rebuild =====
echo ""
echo "[6/6] Rebuild ns-3..."
cd "$NS3_DIR"
./ns3 build 2>&1 | tail -15

# Verify executable
EXEC=$(find build -maxdepth 2 -name "*fanet-sim*" -executable -type f 2>/dev/null | head -1)
if [ -z "$EXEC" ]; then
    echo "ERROR: build failed — fanet-sim not found"
    exit 1
fi

echo ""
echo "========================================"
echo "  Build OK"
echo "========================================"
echo ""
echo "Smoke test (AODV / PMAODV / QMAODV / QSAQMAODV):"
"$EXEC" --protocol=AODV      --numNodes=5 --simTime=10 --csvFile=/tmp/qs_smoke.csv 2>&1 | tail -1
"$EXEC" --protocol=PMAODV    --numNodes=5 --simTime=10 --maxPaths=3 --csvFile=/tmp/qs_smoke.csv 2>&1 | tail -1
"$EXEC" --protocol=QMAODV    --numNodes=5 --simTime=10 --maxPaths=3 --csvFile=/tmp/qs_smoke.csv 2>&1 | tail -1
"$EXEC" --protocol=QSAQMAODV --numNodes=5 --simTime=10 --maxPaths=3 --csvFile=/tmp/qs_smoke.csv 2>&1 | tail -1

echo ""
echo "All 4 protocols OK."
echo "Next: bash scripts/run/run-paper-experiments.sh"
