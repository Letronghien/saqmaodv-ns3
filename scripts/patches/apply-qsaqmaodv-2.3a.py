#!/usr/bin/env python3
"""
QSAQMAODV Phase 2.3.a — Wire Queue-State-Aware QTable into QsaqmaodvRoutingProtocol.

Adds to routing-protocol.h:
  - #include qsaqmaodv-qtable.h
  - QTable m_qtable + all hyper-parameter members (including w4, queue thresholds)
  - Public method declarations

Adds to routing-protocol.cc:
  - #include ns3/double.h + energy headers
  - 12 NS-3 Attributes (alpha0, gamma, epsilon0, w1-w4, lambda, seqNoWindow,
    lowEnergyThreshold, queueHighThreshold, queueLowThreshold, periodicAdaptInterval)
  - Start(): init qtable + schedule PeriodicAdaptiveTick
  - Method definitions: SetMaxPaths, GetEnergyFraction, GetQueueOccupancy,
    PeriodicAdaptiveTick
"""
import os, re, shutil, sys

NS3_DIR = os.environ.get("NS3_DIR", os.path.expanduser("~/workspace/ns-allinone-3.40/ns-3.40"))
H  = os.path.join(NS3_DIR, "src/qsaqmaodv/model/qsaqmaodv-routing-protocol.h")
CC = os.path.join(NS3_DIR, "src/qsaqmaodv/model/qsaqmaodv-routing-protocol.cc")


def backup(p):
    bp = p + ".bak-qs23a"
    if not os.path.exists(bp):
        shutil.copy(p, bp)
        print(f"  Backup: {bp}")


def patch_header():
    with open(H) as f: c = f.read()
    orig = c

    if "qsaqmaodv-qtable.h" not in c:
        c = c.replace('#include "qsaqmaodv-rtable.h"',
                      '#include "qsaqmaodv-rtable.h"\n#include "qsaqmaodv-qtable.h"', 1)
        print("  + #include qsaqmaodv-qtable.h")

    if "QTable m_qtable" not in c:
        c = re.sub(r"(RoutingTable\s+m_routingTable;)",
                   r"\1\n"
                   r"  /// QSAQMAODV: Queue-State-Aware Q-table\n"
                   r"  QTable m_qtable;\n"
                   r"  uint32_t m_maxPaths{3};\n"
                   r"  /// QSAQMAODV: initial Q-learning params\n"
                   r"  double m_alpha0{0.5};\n"
                   r"  double m_gamma{0.9};\n"
                   r"  double m_epsilon0{0.3};\n"
                   r"  /// QSAQMAODV: Normal-mode reward weights (sum=1)\n"
                   r"  double m_w1{0.40};\n"
                   r"  double m_w2{0.30};\n"
                   r"  double m_w3{0.10};\n"
                   r"  double m_w4{0.20};\n"
                   r"  /// QSAQMAODV: adaptive controller params\n"
                   r"  double m_lambda{0.1};\n"
                   r"  Time   m_seqNoWindow{Seconds(5.0)};\n"
                   r"  double m_lowEnergyThreshold{0.20};\n"
                   r"  double m_queueHighThreshold{0.70};\n"
                   r"  double m_queueLowThreshold{0.30};\n"
                   r"  Time   m_periodicAdaptInterval{Seconds(10.0)};\n"
                   r"  EventId m_periodicAdaptEvent;",
                   c, count=1)
        print("  + private members (m_qtable + all QS params)")

    if "SetMaxPaths" not in c:
        m = re.compile(r"(class\s+RoutingProtocol\b[^{]*\{.*?)(\n\s*private:)", re.DOTALL).search(c)
        if m:
            inject = (
                "\n"
                "  void SetMaxPaths(uint32_t mp);\n"
                "  uint32_t GetMaxPaths() const;\n"
                "  /// QSAQMAODV: periodic adaptation tick\n"
                "  void PeriodicAdaptiveTick();\n"
                "  /// QSAQMAODV: read residual energy fraction [0,1]\n"
                "  double GetEnergyFraction() const;\n"
                "  /// QSAQMAODV: read local interface queue occupancy [0,1]\n"
                "  double GetQueueOccupancy() const;\n"
            )
            c = c[: m.end(1)] + inject + c[m.end(1):]
            print("  + public decls")
        else:
            print("  ! WARN: class anchor not found"); return False

    if c != orig:
        with open(H, "w") as f: f.write(c)
    return True


def patch_impl():
    with open(CC) as f: c = f.read()
    orig = c

    # Headers
    if 'ns3/double.h' not in c:
        for anchor in ['#include "ns3/uinteger.h"', '#include "ns3/boolean.h"', '#include "ns3/log.h"']:
            if anchor in c:
                c = c.replace(anchor, anchor + '\n#include "ns3/double.h"', 1)
                print("  + #include ns3/double.h"); break

    if 'ns3/energy-source-container.h' not in c:
        for anchor in ['#include "ns3/double.h"', '#include "ns3/log.h"']:
            if anchor in c:
                c = c.replace(anchor,
                              anchor
                              + '\n#include "ns3/energy-source-container.h"'
                              + '\n#include "ns3/basic-energy-source.h"', 1)
                print("  + #include energy headers"); break

    if 'ns3/wifi-net-device.h' not in c:
        for anchor in ['#include "ns3/double.h"', '#include "ns3/log.h"']:
            if anchor in c:
                c = c.replace(anchor,
                              anchor
                              + '\n#include "ns3/wifi-net-device.h"'
                              + '\n#include "ns3/adhoc-wifi-mac.h"'
                              + '\n#include "ns3/qos-txop.h"'
                              + '\n#include "ns3/wifi-mac-queue.h"', 1)
                print("  + #include wifi queue headers"); break

    # Attributes
    if '"MaxPaths"' not in c:
        m = re.compile(r"(\.AddConstructor<RoutingProtocol>\(\))").search(c)
        if m:
            inject = ("\n            "
                '.AddAttribute("MaxPaths", "Maximum routes per destination",\n'
                "                          UintegerValue(3),\n"
                "                          MakeUintegerAccessor(&RoutingProtocol::SetMaxPaths,\n"
                "                                               &RoutingProtocol::GetMaxPaths),\n"
                "                          MakeUintegerChecker<uint32_t>(1))\n"
                "            "
                '.AddAttribute("Alpha0", "Initial Q-learning rate (adaptive)",\n'
                "                          DoubleValue(0.5),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_alpha0),\n"
                "                          MakeDoubleChecker<double>(0.0, 1.0))\n"
                "            "
                '.AddAttribute("Gamma", "Q-learning discount factor",\n'
                "                          DoubleValue(0.9),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_gamma),\n"
                "                          MakeDoubleChecker<double>(0.0, 1.0))\n"
                "            "
                '.AddAttribute("Epsilon0", "Initial epsilon (adaptive)",\n'
                "                          DoubleValue(0.3),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_epsilon0),\n"
                "                          MakeDoubleChecker<double>(0.0, 1.0))\n"
                "            "
                '.AddAttribute("RewardW1", "Normal-mode reward weight: ACK_success",\n'
                "                          DoubleValue(0.40),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_w1),\n"
                "                          MakeDoubleChecker<double>())\n"
                "            "
                '.AddAttribute("RewardW2", "Normal-mode reward weight: 1/(delay+1)",\n'
                "                          DoubleValue(0.30),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_w2),\n"
                "                          MakeDoubleChecker<double>())\n"
                "            "
                '.AddAttribute("RewardW3", "Normal-mode reward weight: Energy_residual",\n'
                "                          DoubleValue(0.10),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_w3),\n"
                "                          MakeDoubleChecker<double>())\n"
                "            "
                '.AddAttribute("RewardW4", "Normal-mode reward weight: (1 - Q_norm)",\n'
                "                          DoubleValue(0.20),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_w4),\n"
                "                          MakeDoubleChecker<double>())\n"
                "            "
                '.AddAttribute("Lambda", "Sensitivity lambda in alpha_t formula",\n'
                "                          DoubleValue(0.1),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_lambda),\n"
                "                          MakeDoubleChecker<double>())\n"
                "            "
                '.AddAttribute("SeqNoWindow", "Window for Delta_Seq counting",\n'
                "                          TimeValue(Seconds(5.0)),\n"
                "                          MakeTimeAccessor(&RoutingProtocol::m_seqNoWindow),\n"
                "                          MakeTimeChecker())\n"
                "            "
                '.AddAttribute("LowEnergyThreshold", "Energy fraction entering low-energy mode",\n'
                "                          DoubleValue(0.20),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_lowEnergyThreshold),\n"
                "                          MakeDoubleChecker<double>(0.0, 1.0))\n"
                "            "
                '.AddAttribute("QueueHighThreshold", "Queue occupancy entering high-load mode",\n'
                "                          DoubleValue(0.70),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_queueHighThreshold),\n"
                "                          MakeDoubleChecker<double>(0.0, 1.0))\n"
                "            "
                '.AddAttribute("QueueLowThreshold", "Queue occupancy exiting high-load mode",\n'
                "                          DoubleValue(0.30),\n"
                "                          MakeDoubleAccessor(&RoutingProtocol::m_queueLowThreshold),\n"
                "                          MakeDoubleChecker<double>(0.0, 1.0))\n"
                "            "
                '.AddAttribute("PeriodicAdaptInterval", "Period for epsilon-decay + alpha recompute + mode update",\n'
                "                          TimeValue(Seconds(10.0)),\n"
                "                          MakeTimeAccessor(&RoutingProtocol::m_periodicAdaptInterval),\n"
                "                          MakeTimeChecker())"
            )
            c = c[:m.end(1)] + inject + c[m.end(1):]
            print("  + 12 QS attributes registered")
        else:
            print("  ! WARN: AddConstructor anchor missing"); return False

    # Start(): init qtable + schedule first tick
    if "PeriodicAdaptiveTick" not in c:
        m = re.compile(r"(void\s+RoutingProtocol::Start\s*\(\s*\)\s*\{)", re.M).search(c)
        if m:
            inject = (
                "\n  // QSAQMAODV: init queue-state-aware qtable + start adaptive controller\n"
                "  m_qtable.SetMaxPaths(m_maxPaths);\n"
                "  m_qtable.SetLearningParameters(m_alpha0, m_gamma, m_epsilon0);\n"
                "  m_qtable.SetRewardWeights(m_w1, m_w2, m_w3, m_w4);\n"
                "  m_qtable.SetSensitivityLambda(m_lambda);\n"
                "  m_qtable.SetSeqNoWindow(m_seqNoWindow);\n"
                "  m_qtable.SetLowEnergyThreshold(m_lowEnergyThreshold);\n"
                "  m_qtable.SetQueueHighThreshold(m_queueHighThreshold);\n"
                "  m_qtable.SetQueueLowThreshold(m_queueLowThreshold);\n"
                "  m_periodicAdaptEvent =\n"
                "      Simulator::Schedule(m_periodicAdaptInterval,\n"
                "                          &RoutingProtocol::PeriodicAdaptiveTick, this);\n"
            )
            c = c[:m.end(1)] + inject + c[m.end(1):]
            print("  + qtable init + PeriodicAdaptiveTick in Start()")
        else:
            print("  ! WARN: Start() anchor missing")

    # Append method definitions
    if "RoutingProtocol::SetMaxPaths" not in c:
        c += (
            "\nnamespace ns3\n"
            "{\n"
            "namespace qsaqmaodv\n"
            "{\n"
            "\n"
            "void\n"
            "RoutingProtocol::SetMaxPaths(uint32_t mp)\n"
            "{\n"
            "  m_maxPaths = mp;\n"
            "  m_qtable.SetMaxPaths(mp);\n"
            "}\n"
            "\n"
            "uint32_t\n"
            "RoutingProtocol::GetMaxPaths() const\n"
            "{\n"
            "  return m_maxPaths;\n"
            "}\n"
            "\n"
            "double\n"
            "RoutingProtocol::GetEnergyFraction() const\n"
            "{\n"
            "  Ptr<Node> node = m_ipv4 ? m_ipv4->GetObject<Node>() : nullptr;\n"
            "  if (!node) return 1.0;\n"
            "  Ptr<EnergySourceContainer> esc = node->GetObject<EnergySourceContainer>();\n"
            "  if (!esc || esc->GetN() == 0) return 1.0;\n"
            "  Ptr<BasicEnergySource> src =\n"
            "      DynamicCast<BasicEnergySource>(esc->Get(0));\n"
            "  if (!src) return 1.0;\n"
            "  double initE = src->GetInitialEnergy();\n"
            "  double remE  = src->GetRemainingEnergy();\n"
            "  return (initE > 0.0) ? std::min(1.0, std::max(0.0, remE / initE)) : 1.0;\n"
            "}\n"
            "\n"
            "double\n"
            "RoutingProtocol::GetQueueOccupancy() const\n"
            "{\n"
            "  // Read local outgoing interface queue (BE) as proxy for path congestion.\n"
            "  // AdhocWifiMac with QosSupported=true exposes GetQosTxop(AC_BE).\n"
            "  if (!m_ipv4) return 0.0;\n"
            "  uint32_t nIfaces = m_ipv4->GetNInterfaces();\n"
            "  for (uint32_t i = 0; i < nIfaces; ++i)\n"
            "  {\n"
            "    Ptr<NetDevice> dev = m_ipv4->GetNetDevice(i);\n"
            "    if (!dev) continue;\n"
            "    Ptr<WifiNetDevice> wdev = DynamicCast<WifiNetDevice>(dev);\n"
            "    if (!wdev) continue;\n"
            "    Ptr<AdhocWifiMac> mac = DynamicCast<AdhocWifiMac>(wdev->GetMac());\n"
            "    if (!mac) continue;\n"
            "    Ptr<QosTxop> txop = mac->GetQosTxop(AC_BE);\n"
            "    if (!txop) continue;\n"
            "    Ptr<WifiMacQueue> q = txop->GetWifiMacQueue();\n"
            "    if (!q) continue;\n"
            "    uint32_t cur = q->GetNPackets();\n"
            "    uint32_t cap = q->GetMaxSize().GetValue();\n"
            "    return (cap > 0) ? std::min(1.0, (double)cur / cap) : 0.0;\n"
            "  }\n"
            "  return 0.0;\n"
            "}\n"
            "\n"
            "void\n"
            "RoutingProtocol::PeriodicAdaptiveTick()\n"
            "{\n"
            "  double eFrac = GetEnergyFraction();\n"
            "  double qOcc  = GetQueueOccupancy();\n"
            "  // (1) Periodic epsilon decay (§4.2)\n"
            "  m_qtable.PeriodicEpsilonDecay();\n"
            "  // (2) Recompute alpha_t from Delta_Seq (§4.3)\n"
            "  m_qtable.RecomputeAdaptiveAlpha();\n"
            "  // (3) Update operating mode + reward weights (§4.4)\n"
            "  //     Priority: Low-Energy > High-Load > Normal\n"
            "  m_qtable.RecomputeAdaptiveRewardWeights(eFrac, qOcc);\n"
            "  // Re-arm\n"
            "  m_periodicAdaptEvent =\n"
            "      Simulator::Schedule(m_periodicAdaptInterval,\n"
            "                          &RoutingProtocol::PeriodicAdaptiveTick, this);\n"
            "}\n"
            "\n"
            "} // namespace qsaqmaodv\n"
            "} // namespace ns3\n"
        )
        print("  + Appended method definitions")

    if c != orig:
        with open(CC, "w") as f: f.write(c)
    return True


def main():
    if not os.path.exists(H) or not os.path.exists(CC):
        print(f"ERROR: qsaqmaodv files missing at:\n  {H}\n  {CC}")
        sys.exit(1)
    print("=== QSAQMAODV Phase 2.3.a: Queue-State-Aware QTable infrastructure ===\n")
    backup(H); backup(CC); print()
    print("Patching header...")
    if not patch_header(): sys.exit(1)
    print("\nPatching implementation...")
    if not patch_impl(): sys.exit(1)
    print("\nDone. Next: 2.3b → 2.3c → 2.3d → fix-v2")


if __name__ == "__main__":
    main()
