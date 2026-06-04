#!/usr/bin/env python3
"""
QSAQMAODV Phase 2.3.d — RecvReply hooks:
  (1) Store alternate forward route in QS-Q-table
  (2) Apply positive Q-update with adaptive (alpha_t, w_t) + queue occupancy
  (3) Record SeqNo update event — drives alpha_t adaptation (§4.3)
"""
import os, shutil, sys

NS3 = os.environ.get("NS3_DIR", os.path.expanduser("~/workspace/ns-allinone-3.40/ns-3.40"))
CC = os.path.join(NS3, "src/qsaqmaodv/model/qsaqmaodv-routing-protocol.cc")

if not os.path.exists(CC):
    print(f"ERROR: {CC} not found"); sys.exit(1)

shutil.copy(CC, CC + ".bak-qs23d")
with open(CC) as f: c = f.read()

if "QSAQMAODV: QS-Q-update on RREP" in c:
    print("Already applied"); sys.exit(0)

old = """    else
    {
        // The forward route for this destination is created if it does not already exist.
        NS_LOG_LOGIC("add new route");
        m_routingTable.AddRoute(newEntry);
    }
    // Acknowledge receipt of the RREP by sending a RREP-ACK message back"""

new = """    else
    {
        // The forward route for this destination is created if it does not already exist.
        NS_LOG_LOGIC("add new route");
        m_routingTable.AddRoute(newEntry);
    }

    // QSAQMAODV: QS-Q-update on RREP + SeqNo tracking.
    {
        // (1) Record destination SeqNo update -> drives alpha_t adaptation (§4.3)
        m_qtable.RecordSeqNoUpdate();
        // (2) Positive Q-update: ACK=1, delay=5ms, energy=current, queue=current.
        //     Queue occupancy on RREP is typically low (discovery phase); pass live value.
        double eFrac = GetEnergyFraction();
        double qOcc  = GetQueueOccupancy();
        m_qtable.UpdateQValueOrCreate(newEntry, /*ack=*/1.0, /*delaySec=*/0.005,
                                      eFrac, qOcc);
    }

    // Acknowledge receipt of the RREP by sending a RREP-ACK message back"""

if old not in c:
    print("ERROR: RecvReply anchor not found"); sys.exit(1)

c = c.replace(old, new, 1)
with open(CC, "w") as f: f.write(c)
print("Patched: QS-Q-update + SeqNo tracking on RREP.")
