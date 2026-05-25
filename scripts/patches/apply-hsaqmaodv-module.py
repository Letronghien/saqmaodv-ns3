#!/usr/bin/env python3
"""
apply-hsaqmaodv-module.py
=========================
Wires H-SAQMAODV (3-mode hybrid Q-switching) into the existing SAQMAODV
NS-3 module.  Run AFTER the full SAQMAODV patch chain (2.2 through fix-v2).

What this script does
---------------------
1. Copies hsaqmaodv-qtable.{h,cc} from FILES_DIR → src/saqmaodv/model/
2. Adds them to src/saqmaodv/CMakeLists.txt (if not already there)
3. Patches saqmaodv-routing-protocol.h:
     - Adds  #include "hsaqmaodv-qtable.h"
     - Replaces  saqmaodv::QTable m_qtable  with  hsaqmaodv::QTable m_qtable
     - Adds new member variables:  m_useHybrid, m_tviHigh, m_tviLow
     - Declares  SetHybridMode(), SetTVIThresholds(), GetCurrentTVIMode()
4. Patches saqmaodv-routing-protocol.cc:
     - Registers three NS-3 attributes: UseHybrid, TVIHigh, TVILow
     - Pushes threshold config in Start()
     - Wraps SelectEpsilonGreedy() call → SelectHybridRoute() when UseHybrid=true

Usage
-----
    # From the project root (e.g. ~/hsaqmaodv-ns3 or ~/paper1-hsaqmaodv):
    export NS3_DIR=$HOME/ns-allinone-3.40/ns-3.40
    python3 scripts/patches/apply-hsaqmaodv-module.py

    # Override files directory:
    FILES_DIR=/path/to/files python3 scripts/patches/apply-hsaqmaodv-module.py
"""
import os, re, shutil, sys

# ---------------------------------------------------------------------------
# Paths — auto-derived; override via env vars
# ---------------------------------------------------------------------------
# Project root = two levels above this script (scripts/patches/<script>)
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", ".."))

NS3_DIR   = os.environ.get("NS3_DIR",
                os.path.expanduser("~/ns-allinone-3.40/ns-3.40"))
FILES_DIR = os.environ.get("FILES_DIR",
                os.path.join(_PROJECT_ROOT, "files"))

H_SRC  = os.path.join(FILES_DIR, "hsaqmaodv-qtable.h")
CC_SRC = os.path.join(FILES_DIR, "hsaqmaodv-qtable.cc")

SAQ_MODEL = os.path.join(NS3_DIR, "src", "saqmaodv", "model")
H_DST  = os.path.join(SAQ_MODEL, "hsaqmaodv-qtable.h")
CC_DST = os.path.join(SAQ_MODEL, "hsaqmaodv-qtable.cc")
CMAKE  = os.path.join(NS3_DIR, "src", "saqmaodv", "CMakeLists.txt")
PROTO_H  = os.path.join(SAQ_MODEL, "saqmaodv-routing-protocol.h")
PROTO_CC = os.path.join(SAQ_MODEL, "saqmaodv-routing-protocol.cc")

# ---------------------------------------------------------------------------
def backup(p):
    bp = p + ".bak-hsaq-module"
    if not os.path.exists(bp):
        shutil.copy(p, bp)
        print(f"  backup -> {os.path.basename(bp)}")

# ---------------------------------------------------------------------------
def step1_copy_files():
    print("=== 1. Copy hsaqmaodv-qtable.{h,cc} ===")
    for src, dst in [(H_SRC, H_DST), (CC_SRC, CC_DST)]:
        if not os.path.exists(src):
            print(f"ERROR: {src} not found")
            print(f"  Hint: set FILES_DIR env var or check the files/ directory")
            sys.exit(1)
        shutil.copy(src, dst)
        print(f"  Copied {os.path.basename(src)} -> src/saqmaodv/model/")

# ---------------------------------------------------------------------------
def step2_cmake():
    print("\n=== 2. Update CMakeLists.txt ===")
    with open(CMAKE) as f: c = f.read()
    changed = False
    if "hsaqmaodv-qtable.cc" not in c:
        c = c.replace("model/saqmaodv-qtable.cc",
                      "model/saqmaodv-qtable.cc\n    model/hsaqmaodv-qtable.cc", 1)
        changed = True; print("  + model/hsaqmaodv-qtable.cc")
    if "hsaqmaodv-qtable.h" not in c:
        c = c.replace("model/saqmaodv-qtable.h",
                      "model/saqmaodv-qtable.h\n    model/hsaqmaodv-qtable.h", 1)
        changed = True; print("  + model/hsaqmaodv-qtable.h")
    if changed:
        backup(CMAKE)
        with open(CMAKE, "w") as f: f.write(c)
    else:
        print("  Already up-to-date.")

# ---------------------------------------------------------------------------
def step3_header():
    print("\n=== 3. Patch saqmaodv-routing-protocol.h ===")
    with open(PROTO_H) as f: c = f.read()
    orig = c

    # 3a. Include hsaqmaodv-qtable.h
    if "hsaqmaodv-qtable.h" not in c:
        c = c.replace('#include "saqmaodv-qtable.h"',
                      '#include "saqmaodv-qtable.h"\n#include "hsaqmaodv-qtable.h"', 1)
        print("  + #include hsaqmaodv-qtable.h")

    # 3b. Replace QTable member type (saqmaodv::QTable -> hsaqmaodv::QTable)
    # The base saqmaodv class declares:  QTable m_qtable;  (within saqmaodv ns)
    # After the include above the compiler sees hsaqmaodv::QTable.
    # We rename just the m_qtable declaration so we don't touch every usage.
    if "hsaqmaodv::QTable m_qtable" not in c:
        # Match "QTable m_qtable" that is NOT already qualified
        c = re.sub(r'\bQTable\s+(m_qtable\s*;)',
                   r'hsaqmaodv::QTable \1', c, count=1)
        print("  + Changed m_qtable type -> hsaqmaodv::QTable")

    # 3c. Add new private members (UseHybrid flag + TVI thresholds)
    if "m_useHybrid" not in c:
        c = re.sub(
            r'(hsaqmaodv::QTable\s+m_qtable\s*;)',
            r'\1\n'
            r'  /// H-SAQMAODV: enable 3-mode hybrid switching\n'
            r'  bool   m_useHybrid{false};\n'
            r'  double m_tviHigh{3.0};\n'
            r'  double m_tviLow{1.0};',
            c, count=1)
        print("  + m_useHybrid, m_tviHigh, m_tviLow members")

    # 3d. Declare new public methods
    if "SetHybridMode" not in c:
        m = re.compile(r'(void\s+SetSAAdaptiveParams\s*\([^)]*\)\s*;)').search(c)
        if m:
            inject = ("\n"
                "  /// H-SAQMAODV: enable/disable 3-mode switching\n"
                "  void SetHybridMode(bool enable);\n"
                "  bool GetHybridMode() const;\n"
                "  void SetTVIThresholds(double tviHigh, double tviLow);\n"
                "  /// Return current topology mode name (BYPASS/EXPLORE/GREEDY) for logging\n"
                "  std::string GetCurrentTVIMode() const;\n")
            c = c[:m.end(1)] + inject + c[m.end(1):]
            print("  + Declared SetHybridMode, SetTVIThresholds, GetCurrentTVIMode")
        else:
            print("  ! WARN: could not find SetSAAdaptiveParams anchor; skipping method decls")

    if c != orig:
        backup(PROTO_H)
        with open(PROTO_H, "w") as f: f.write(c)
    else:
        print("  Already up-to-date.")

# ---------------------------------------------------------------------------
def step4_impl():
    print("\n=== 4. Patch saqmaodv-routing-protocol.cc ===")
    with open(PROTO_CC) as f: c = f.read()
    orig = c

    # 4a. Add std::string include (for GetCurrentTVIMode)
    if '<string>' not in c:
        for anc in ['#include "ns3/log.h"', '#include "ns3/double.h"']:
            if anc in c:
                c = c.replace(anc, '#include <string>\n' + anc, 1)
                print("  + #include <string>"); break

    # 4b. Register 3 new NS-3 attributes
    if '"UseHybrid"' not in c:
        m = re.compile(r'("PeriodicAdaptInterval"[^)]*\))').search(c)
        if m:
            inject = ("\n            "
                '.AddAttribute("UseHybrid",\n'
                '                          "Enable 3-mode topology-aware Q-switching (H-SAQMAODV)",\n'
                "                          BooleanValue(false),\n"
                "                          MakeBooleanAccessor(&RoutingProtocol::SetHybridMode,\n"
                "                                              &RoutingProtocol::GetHybridMode),\n"
                "                          MakeBooleanChecker())\n"
                "            "
                '.AddAttribute("TVIHigh",\n'
                '                          "TVI upper threshold: above -> MODE_BYPASS",\n'
                "                          DoubleValue(3.0),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_tviHigh),\n"
                "                          MakeDoubleChecker<double>(0.0))\n"
                "            "
                '.AddAttribute("TVILow",\n'
                '                          "TVI lower threshold: below -> MODE_GREEDY",\n'
                "                          DoubleValue(1.0),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_tviLow),\n"
                "                          MakeDoubleChecker<double>(0.0))"
            )
            c = c[:m.end(1)] + inject + c[m.end(1):]
            print("  + 3 attributes: UseHybrid, TVIHigh, TVILow")
        else:
            print("  ! WARN: PeriodicAdaptInterval anchor not found; skipping attributes")

    # 4c. Push TVI config in Start() — right after the existing Q-table init block
    if "m_qtable.SetTVIThresholds" not in c:
        m = re.compile(
            r'(m_periodicAdaptEvent\s*=\s*\n?\s*Simulator::Schedule\(m_periodicAdaptInterval[^;]*;)',
            re.DOTALL).search(c)
        if m:
            inject = ("\n  // H-SAQMAODV: push TVI thresholds into hybrid Q-table\n"
                "  if (m_useHybrid)\n"
                "    {\n"
                "      m_qtable.SetTVIThresholds(m_tviHigh, m_tviLow);\n"
                "    }\n")
            c = c[:m.end(1)] + inject + c[m.end(1):]
            print("  + TVI threshold push in Start()")
        else:
            print("  ! WARN: Simulator::Schedule anchor not found; add manually in Start()")

    # 4d. Append method definitions at end of file (before closing namespaces)
    if "RoutingProtocol::SetHybridMode" not in c:
        # Find the last namespace closing brace pair
        defs = (
            "\n"
            "void\n"
            "RoutingProtocol::SetHybridMode(bool enable)\n"
            "{\n"
            "  m_useHybrid = enable;\n"
            "}\n"
            "\n"
            "bool\n"
            "RoutingProtocol::GetHybridMode() const\n"
            "{\n"
            "  return m_useHybrid;\n"
            "}\n"
            "\n"
            "void\n"
            "RoutingProtocol::SetTVIThresholds(double tviHigh, double tviLow)\n"
            "{\n"
            "  m_tviHigh = tviHigh;\n"
            "  m_tviLow  = tviLow;\n"
            "  m_qtable.SetTVIThresholds(tviHigh, tviLow);\n"
            "}\n"
            "\n"
            "std::string\n"
            "RoutingProtocol::GetCurrentTVIMode() const\n"
            "{\n"
            "  return m_useHybrid ? m_qtable.GetModeName() : std::string(\"EXPLORE\");\n"
            "}\n"
        )
        # Insert before the last "} // namespace saqmaodv"
        marker = "} // namespace saqmaodv"
        idx = c.rfind(marker)
        if idx >= 0:
            c = c[:idx] + defs + c[idx:]
            print("  + Appended SetHybridMode / SetTVIThresholds / GetCurrentTVIMode")
        else:
            c += "\nnamespace ns3\n{\nnamespace saqmaodv\n{\n" + defs + "\n} // namespace saqmaodv\n} // namespace ns3\n"
            print("  + Appended method defs (namespace wrapper added)")

    # 4e. Replace SelectEpsilonGreedy call with hybrid dispatch
    # Pattern: m_qtable.SelectEpsilonGreedy(primary, selected, ...)
    if "SelectHybridRoute" not in c:
        c = re.sub(
            r'm_qtable\.SelectEpsilonGreedy\(',
            'HYBRID_SELECT(',
            c)
        # Now add the macro-like inline at the top of the cc (after includes)
        dispatch = (
            "\n"
            "// H-SAQMAODV: inline helper — calls SelectHybridRoute when UseHybrid=true,\n"
            "//             otherwise falls back to standard SelectEpsilonGreedy.\n"
            "#define HYBRID_SELECT(...) \\\n"
            "    (m_useHybrid ? m_qtable.SelectHybridRoute(__VA_ARGS__) \\\n"
            "                 : m_qtable.SelectEpsilonGreedy(__VA_ARGS__))\n"
        )
        # Insert after last #include
        last_inc = 0
        for m2 in re.finditer(r'^#include\b.*$', c, re.M):
            last_inc = m2.end()
        if last_inc:
            c = c[:last_inc] + dispatch + c[last_inc:]
            print("  + SelectEpsilonGreedy -> HYBRID_SELECT macro")
        else:
            print("  ! WARN: could not insert HYBRID_SELECT macro; patch manually")

    if c != orig:
        backup(PROTO_CC)
        with open(PROTO_CC, "w") as f: f.write(c)
    else:
        print("  Already up-to-date.")

# ---------------------------------------------------------------------------
def main():
    print("=" * 62)
    print("  apply-hsaqmaodv-module.py")
    print("  NS3_DIR  :", NS3_DIR)
    print("  FILES_DIR:", FILES_DIR)
    print("=" * 62, "\n")

    if not os.path.isdir(SAQ_MODEL):
        print(f"ERROR: {SAQ_MODEL} not found.")
        print("  Make sure SAQMAODV is installed and NS3_DIR is correct.")
        sys.exit(1)

    step1_copy_files()
    step2_cmake()
    step3_header()
    step4_impl()

    print("\n" + "=" * 62)
    print("  Done. Next: python3 scripts/patches/apply-hsaqmaodv-fanet.py")
    print("  Then rebuild:  cd $NS3_DIR && ./ns3 build")
    print("=" * 62)


if __name__ == "__main__":
    main()
