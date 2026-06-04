#!/usr/bin/env python3
"""QSAQMAODV Phase 2.3.b — RouteOutput uses epsilon-greedy from QS-Q-Table."""
import os, shutil, sys

NS3 = os.environ.get("NS3_DIR", os.path.expanduser("~/workspace/ns-allinone-3.40/ns-3.40"))
CC = os.path.join(NS3, "src/qsaqmaodv/model/qsaqmaodv-routing-protocol.cc")

if not os.path.exists(CC):
    print(f"ERROR: {CC} not found"); sys.exit(1)

shutil.copy(CC, CC + ".bak-qs23b")
with open(CC) as f: c = f.read()

if "// QSAQMAODV: epsilon-greedy" in c:
    print("Already applied"); sys.exit(0)

old = """    if (m_routingTable.LookupValidRoute(dst, rt))
    {
        route = rt.GetRoute();
        NS_ASSERT(route);"""

new = """    if (m_routingTable.LookupValidRoute(dst, rt))
    {
        // QSAQMAODV: epsilon-greedy selection over primary + QS-Q-learned alternates.
        RoutingTableEntry chosenRt = rt;
        m_qtable.SelectEpsilonGreedy(rt, chosenRt, &m_routingTable);
        route = chosenRt.GetRoute();
        NS_ASSERT(route);"""

if old not in c:
    print("ERROR: RouteOutput anchor not found"); sys.exit(1)

c = c.replace(old, new, 1)
with open(CC, "w") as f: f.write(c)
print("Patched: epsilon-greedy in RouteOutput.")
