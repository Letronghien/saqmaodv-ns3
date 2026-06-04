#!/usr/bin/env python3
"""
QSAQMAODV fix-v2 — three hooks for the Queue-State-Aware Controller:

(A) Per-packet Q-update in RouteOutput:
    Passes live energy fraction AND local queue occupancy into the 4-term reward.
    This is the primary mechanism that makes routing queue-state-aware at runtime.

(B) RERR-triggered epsilon bump (§4.2):
    Call m_qtable.OnRouteError() from RecvError.

(C) Negative Q-update on RERR for the failed route.
"""
import os, shutil, sys

NS3 = os.environ.get("NS3_DIR", os.path.expanduser("~/workspace/ns-allinone-3.40/ns-3.40"))
CC = os.path.join(NS3, "src/qsaqmaodv/model/qsaqmaodv-routing-protocol.cc")

if not os.path.exists(CC):
    print(f"ERROR: {CC} not found"); sys.exit(1)

shutil.copy(CC, CC + ".bak-qsfixv2")
with open(CC) as f: c = f.read()
orig = c

# (A) Per-packet Q-update in RouteOutput
# Inserted right after epsilon-greedy selection (injected by 2.3b).
if "// QSAQMAODV-FIX-V2: per-packet" not in c:
    anchor = "m_qtable.SelectEpsilonGreedy(rt, chosenRt, &m_routingTable);"
    if anchor in c:
        inject = (
            anchor
            + "\n        // QSAQMAODV-FIX-V2: per-packet QS-Q-update with 4-term reward.\n"
            + "        {\n"
            + "            RoutingTableEntry nbrCheck;\n"
            + "            bool fresh = m_routingTable.LookupRoute(chosenRt.GetNextHop(), nbrCheck)\n"
            + "                         && nbrCheck.GetFlag() == VALID\n"
            + "                         && nbrCheck.GetLifeTime() > Seconds(0);\n"
            + "            double ack    = fresh ? 1.0 : 0.0;\n"
            + "            double delayS = fresh ? 0.005 : 1.0;\n"
            + "            double eFrac  = GetEnergyFraction();\n"
            + "            double qOcc   = GetQueueOccupancy();\n"
            + "            m_qtable.UpdateQValueOrCreate(chosenRt, ack, delayS, eFrac, qOcc);\n"
            + "        }"
        )
        c = c.replace(anchor, inject, 1)
        print("  [RouteOutput] + per-packet QS Q-update (energy + queue)")
    else:
        print("  ! [RouteOutput] epsilon-greedy anchor missing (2.3.b not applied?)")

# (B) + (C) RERR hook: epsilon bump + negative Q-update
if "// QSAQMAODV-FIX-V2: RERR epsilon bump" not in c:
    # Try both indentation variants
    patterns = [
        "    m_routingTable.SetEntryState(un.first, INVALID);",
        "        m_routingTable.SetEntryState(un.first, INVALID);",
    ]
    for p in patterns:
        if p in c:
            new_p = (
                p
                + "\n    // QSAQMAODV-FIX-V2: RERR epsilon bump (§4.2) + penalty Q-update.\n"
                + "    m_qtable.OnRouteError();\n"
                + "    m_qtable.UpdateQValue(un.first, src, /*ack=*/0.0,\n"
                + "                          /*delaySec=*/5.0,\n"
                + "                          GetEnergyFraction(), GetQueueOccupancy());\n"
            )
            c = c.replace(p, new_p, 1)
            print("  [RecvError] + epsilon bump + penalty Q-update")
            break
    else:
        print("  [RecvError] no anchor matched (RecvError may have different structure)")

if c != orig:
    with open(CC, "w") as f: f.write(c)
    print("Done.")
else:
    print("(no changes written)")
