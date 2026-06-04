#!/usr/bin/env python3
"""QSAQMAODV Phase 2.3.c — RecvRequest stores alternate reverse from duplicate RREQ."""
import os, shutil, sys

NS3 = os.environ.get("NS3_DIR", os.path.expanduser("~/workspace/ns-allinone-3.40/ns-3.40"))
CC = os.path.join(NS3, "src/qsaqmaodv/model/qsaqmaodv-routing-protocol.cc")

if not os.path.exists(CC):
    print(f"ERROR: {CC} not found"); sys.exit(1)

shutil.copy(CC, CC + ".bak-qs23c")
with open(CC) as f: c = f.read()

if "QSAQMAODV: store alternate reverse route" in c:
    print("Already applied"); sys.exit(0)

old = """    if (m_rreqIdCache.IsDuplicate(origin, id))
    {
        NS_LOG_DEBUG("Ignoring RREQ due to duplicate");
        return;
    }"""

new = """    if (m_rreqIdCache.IsDuplicate(origin, id))
    {
        // QSAQMAODV: store alternate reverse route from duplicate RREQ (multipath).
        if (!m_qtable.IsFull(origin))
        {
            uint8_t altHop = rreqHeader.GetHopCount() + 1;
            Ptr<NetDevice> dev =
                m_ipv4->GetNetDevice(m_ipv4->GetInterfaceForAddress(receiver));
            RoutingTableEntry alt(
                /*dev=*/dev, /*dst=*/origin, /*vSeqNo=*/true,
                /*seqNo=*/rreqHeader.GetOriginSeqno(),
                /*iface=*/m_ipv4->GetAddress(m_ipv4->GetInterfaceForAddress(receiver), 0),
                /*hops=*/altHop, /*nextHop=*/src,
                /*lifetime=*/m_activeRouteTimeout);
            alt.SetFlag(VALID);
            m_qtable.AddRoute(alt);
        }
        return;
    }"""

if old not in c:
    print("ERROR: RecvRequest duplicate anchor not found"); sys.exit(1)

c = c.replace(old, new, 1)
with open(CC, "w") as f: f.write(c)
print("Patched: alternate reverse route stored on duplicate RREQ.")
