#!/usr/bin/env python3
"""
apply-hsaqmaodv-fanet.py
========================
Patches src/fanet-sim.cc to add HSAQMAODV as a selectable protocol.

What this script adds
---------------------
* "--protocol HSAQMAODV" option in CommandLine help string
* Two new cmd args: --hsaTVIHigh (default 3.0), --hsaTVILow (default 1.0)
* Protocol banner print for HSAQMAODV
* Routing setup block: uses SaqmaodvHelper with UseHybrid=true + TVI attributes
* maxPaths / CSV accounting includes HSAQMAODV alongside SAQMAODV

FIX vs previous version
------------------------
* ANCHOR corrected: uses '#include "ns3/saqmaodv-module.h"'
  (old script used 'ns3/saqmaodv-helper.h' which does not exist in fanet-sim.cc)

Usage
-----
    export NS3_DIR=$HOME/ns-allinone-3.40/ns-3.40
    FANET_SIM=$NS3_DIR/scratch/fanet-sim.cc   # default
    python3 scripts/patches/apply-hsaqmaodv-fanet.py
"""
import os, re, shutil, sys

_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", ".."))

NS3_DIR   = os.environ.get("NS3_DIR", os.path.expanduser("~/ns-allinone-3.40/ns-3.40"))
FANET_SIM = os.environ.get("FANET_SIM", os.path.join(NS3_DIR, "scratch", "fanet-sim.cc"))

# ---- If not in scratch, check project src/ ----
if not os.path.exists(FANET_SIM):
    alt = os.path.join(_PROJECT_ROOT, "src", "fanet-sim.cc")
    if os.path.exists(alt):
        FANET_SIM = alt

def backup(p):
    bp = p + ".bak-hsaq-fanet"
    if not os.path.exists(bp):
        shutil.copy(p, bp)
        print(f"  backup -> {os.path.basename(bp)}")


def patch(c):
    changed = []

    # ------------------------------------------------------------------
    # 1. Extend the protocol help string in cmd.AddValue("protocol", ...)
    # ------------------------------------------------------------------
    OLD_PROTO_HELP = '"Routing protocol (AODV|DSDV|DSR|PMAODV|AOMDV|QMAODV|SAQMAODV)"'
    NEW_PROTO_HELP = '"Routing protocol (AODV|DSDV|DSR|PMAODV|AOMDV|QMAODV|SAQMAODV|HSAQMAODV)"'
    if "HSAQMAODV" not in c:
        c = c.replace(OLD_PROTO_HELP, NEW_PROTO_HELP, 1)
        changed.append("protocol help string")

    # ------------------------------------------------------------------
    # 2. Declare TVI parameter variables (after saAdaptPeriod declaration)
    # ------------------------------------------------------------------
    if "hsaTVIHigh" not in c:
        anchor = "double      saAdaptPeriod = 10.0;"
        if anchor in c:
            inject = (
                "\n"
                "  // H-SAQMAODV TVI thresholds\n"
                "  double      hsaTVIHigh    = 3.0;      // TVI upper threshold -> MODE_BYPASS\n"
                "  double      hsaTVILow     = 1.0;      // TVI lower threshold -> MODE_GREEDY"
            )
            c = c.replace(anchor, anchor + inject, 1)
            changed.append("TVI variable declarations")
        else:
            print("  ! WARN: saAdaptPeriod anchor not found; TVI vars not added")

    # ------------------------------------------------------------------
    # 3. Register --hsaTVIHigh / --hsaTVILow command-line args
    # ------------------------------------------------------------------
    if '"hsaTVIHigh"' not in c:
        anchor = 'cmd.AddValue("saAdaptPeriod"'
        if anchor in c:
            # find end of that statement (;)
            idx = c.find(anchor)
            end = c.find(';', idx)
            inject = (
                "\n"
                '  cmd.AddValue("hsaTVIHigh",      "H-SAQMAODV TVI upper threshold (MODE_BYPASS above)", hsaTVIHigh);\n'
                '  cmd.AddValue("hsaTVILow",       "H-SAQMAODV TVI lower threshold (MODE_GREEDY below)", hsaTVILow);'
            )
            c = c[:end+1] + inject + c[end+1:]
            changed.append("cmd args hsaTVIHigh / hsaTVILow")
        else:
            print("  ! WARN: saAdaptPeriod cmd anchor not found")

    # ------------------------------------------------------------------
    # 4. Banner print for HSAQMAODV
    # ------------------------------------------------------------------
    if '"HSAQMAODV"' not in c:
        anchor = 'if (protocol == "SAQMAODV")'
        idx = c.find(anchor)
        if idx >= 0:
            # find end of that if-block (the closing std::cout << ...)
            end_semi = c.find(';', c.find('<<', idx + len(anchor)))
            inject = (
                "\n"
                '  if (protocol == "HSAQMAODV")\n'
                '    std::cout << "(TVIHigh=" << hsaTVIHigh << " TVILow=" << hsaTVILow\n'
                '              << " alpha0=" << saAlpha0 << " eps0=" << saEpsilon0 << ")";'
            )
            c = c[:end_semi+1] + inject + c[end_semi+1:]
            changed.append("HSAQMAODV banner print")

    # ------------------------------------------------------------------
    # 5. Routing setup block
    #    Anchor: line  } else /* SAQMAODV */ {
    #    We add:       } else if (protocol == "HSAQMAODV") {  ...  } else /* SAQMAODV */
    # ------------------------------------------------------------------
    if 'protocol == "HSAQMAODV"' not in c:
        anchor = '} else /* SAQMAODV */ {'
        if anchor in c:
            hsaq_block = (
                '} else if (protocol == "HSAQMAODV") {\n'
                '      // H-SAQMAODV: SaqmaodvHelper with UseHybrid=true + TVI attributes\n'
                '      SaqmaodvHelper hsaqmaodv;\n'
                '      hsaqmaodv.Set("MaxPaths",              UintegerValue(maxPaths));\n'
                '      hsaqmaodv.Set("Alpha0",                DoubleValue(saAlpha0));\n'
                '      hsaqmaodv.Set("Gamma",                 DoubleValue(saGamma));\n'
                '      hsaqmaodv.Set("Epsilon0",              DoubleValue(saEpsilon0));\n'
                '      hsaqmaodv.Set("RewardW1",              DoubleValue(saW1));\n'
                '      hsaqmaodv.Set("RewardW2",              DoubleValue(saW2));\n'
                '      hsaqmaodv.Set("RewardW3",              DoubleValue(saW3));\n'
                '      hsaqmaodv.Set("Lambda",                DoubleValue(saLambda));\n'
                '      hsaqmaodv.Set("SeqNoWindow",           TimeValue(Seconds(saSeqNoWin)));\n'
                '      hsaqmaodv.Set("LowEnergyThreshold",    DoubleValue(saLowEThresh));\n'
                '      hsaqmaodv.Set("PeriodicAdaptInterval", TimeValue(Seconds(saAdaptPeriod)));\n'
                '      hsaqmaodv.Set("UseHybrid",             BooleanValue(true));\n'
                '      hsaqmaodv.Set("TVIHigh",               DoubleValue(hsaTVIHigh));\n'
                '      hsaqmaodv.Set("TVILow",                DoubleValue(hsaTVILow));\n'
                '      internet.SetRoutingHelper(hsaqmaodv);\n'
                '    '
            )
            c = c.replace(anchor, hsaq_block + anchor, 1)
            changed.append("HSAQMAODV routing setup block")
        else:
            print("  ! WARN: SAQMAODV routing block anchor not found")

    # ------------------------------------------------------------------
    # 6. maxPaths condition lines (3 occurrences)
    # ------------------------------------------------------------------
    OLD_COND = '|| protocol == "SAQMAODV"'
    NEW_COND = '|| protocol == "SAQMAODV" || protocol == "HSAQMAODV"'
    if 'protocol == "HSAQMAODV"' not in c or OLD_COND in c:
        count = c.count(OLD_COND)
        if count:
            c = c.replace(OLD_COND, NEW_COND)
            changed.append(f"maxPaths/CSV conditions ({count} occurrences)")

    return c, changed


def main():
    print("=" * 62)
    print("  apply-hsaqmaodv-fanet.py")
    print("  NS3_DIR  :", NS3_DIR)
    print("  FANET_SIM:", FANET_SIM)
    print("=" * 62, "\n")

    if not os.path.exists(FANET_SIM):
        print(f"ERROR: {FANET_SIM} not found.")
        print("  Set FANET_SIM env var to the full path of fanet-sim.cc")
        sys.exit(1)

    with open(FANET_SIM) as f:
        c = f.read()

    c2, changed = patch(c)

    if not changed:
        print("Nothing to do — fanet-sim.cc already patched.")
        return

    backup(FANET_SIM)
    with open(FANET_SIM, "w") as f:
        f.write(c2)

    print("Patched:")
    for item in changed:
        print(f"  + {item}")
    print("\nDone. Rebuild with:  cd $NS3_DIR && ./ns3 build")
    print("Test:  ./ns3 run 'fanet-sim --protocol=HSAQMAODV --numNodes=10 --simTime=30'")


if __name__ == "__main__":
    main()
