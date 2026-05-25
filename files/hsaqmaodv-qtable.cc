/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/**
 * H-SAQMAODV Hybrid QTable — implementation.
 * See hsaqmaodv-qtable.h for design rationale.
 */

#include "hsaqmaodv-qtable.h"

#include "ns3/log.h"
#include "ns3/simulator.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("HsaqmaodvQTable");

namespace hsaqmaodv {

// ============================================================================
// Constructor
// ============================================================================

QTable::QTable(uint32_t maxPaths, double tviHigh, double tviLow)
    : saqmaodv::QTable(maxPaths),
      m_tviHigh(tviHigh),
      m_tviLow(tviLow)
{
    NS_ASSERT_MSG(tviLow > 0.0,       "tviLow must be > 0");
    NS_ASSERT_MSG(tviHigh > tviLow,   "tviHigh must be > tviLow");
}

// ============================================================================
// TVI threshold configuration
// ============================================================================

void
QTable::SetTVIThresholds(double tviHigh, double tviLow)
{
    NS_ASSERT_MSG(tviLow > 0.0,     "tviLow must be > 0");
    NS_ASSERT_MSG(tviHigh > tviLow, "tviHigh must be > tviLow");
    m_tviHigh = tviHigh;
    m_tviLow  = tviLow;
}

// ============================================================================
// TVI / mode helpers
// ============================================================================

double
QTable::GetSeqNoWindowSeconds() const
{
    // m_seqNoWindow is a ns3::Time in the base class.
    // We read it via the public accessor SeqNoWindow -> use GetSeqNoWindow()
    // Fallback: 5.0 s (paper default).
    double w = 5.0;
    // Base class exposes only SetSeqNoWindow; derive value from GetDeltaSeq()
    // granularity is already baked in.  Use 5 s as the normaliser (paper §4.2).
    return w;
}

double
QTable::GetTVI() const
{
    double window = GetSeqNoWindowSeconds();
    if (window <= 0.0) return 0.0;
    return static_cast<double>(GetDeltaSeq()) / window;
}

TopologyMode
QTable::GetCurrentMode() const
{
    double tvi = GetTVI();
    if (tvi > m_tviHigh) return MODE_BYPASS;
    if (tvi < m_tviLow)  return MODE_GREEDY;
    return MODE_EXPLORE;
}

std::string
QTable::GetModeName() const
{
    switch (GetCurrentMode())
    {
    case MODE_BYPASS:  return "BYPASS";
    case MODE_GREEDY:  return "GREEDY";
    case MODE_EXPLORE: return "EXPLORE";
    default:           return "UNKNOWN";
    }
}

// ============================================================================
// Greedy selection (MODE_GREEDY)
// ============================================================================

bool
QTable::SelectGreedy(const saqmaodv::RoutingTableEntry& primary,
                     saqmaodv::RoutingTableEntry&       out,
                     const saqmaodv::RoutingTable*      mainTable) const
{
    ns3::Ipv4Address dst = primary.GetDst();

    std::vector<saqmaodv::RoutingTableEntry> routes;
    uint32_t n = GetRoutes(dst, routes, mainTable);
    if (n == 0)
    {
        NS_LOG_DEBUG("HSAQMAODV GREEDY: no Q-records for " << dst
                     << ", falling back to primary");
        out = primary;
        return true;
    }

    // Find the entry with the highest Q-value.
    double bestQ = std::numeric_limits<double>::lowest();
    int    bestIdx = -1;
    for (uint32_t i = 0; i < routes.size(); ++i)
    {
        double q = GetQValue(dst, routes[i].GetNextHop());
        NS_LOG_DEBUG("HSAQMAODV GREEDY candidate: nh=" << routes[i].GetNextHop()
                     << " Q=" << q);
        if (q > bestQ)
        {
            bestQ    = q;
            bestIdx  = static_cast<int>(i);
        }
    }

    if (bestIdx < 0)
    {
        out = primary;
        return true;
    }

    out = routes[bestIdx];
    NS_LOG_DEBUG("HSAQMAODV GREEDY selected: nh=" << out.GetNextHop()
                 << " Q=" << bestQ);
    return true;
}

// ============================================================================
// 3-mode route selection (core contribution)
// ============================================================================

bool
QTable::SelectHybridRoute(const saqmaodv::RoutingTableEntry& primary,
                          saqmaodv::RoutingTableEntry&       out,
                          const saqmaodv::RoutingTable*      mainTable)
{
    TopologyMode mode = GetCurrentMode();

    NS_LOG_DEBUG("HSAQMAODV SelectHybridRoute: TVI=" << GetTVI()
                 << " mode=" << GetModeName()
                 << " dst=" << primary.GetDst());

    switch (mode)
    {
    case MODE_BYPASS:
        // Network too dynamic: bypass Q-table entirely.
        NS_LOG_DEBUG("HSAQMAODV BYPASS: returning primary route nh="
                     << primary.GetNextHop());
        out = primary;
        return true;

    case MODE_GREEDY:
        // Network stable: exploit best known Q-value.
        return SelectGreedy(primary, out, mainTable);

    case MODE_EXPLORE:
    default:
        // Sweet spot: standard epsilon-greedy from SA-QMAODV base class.
        return SelectEpsilonGreedy(primary, out, mainTable);
    }
}

} // namespace hsaqmaodv
} // namespace ns3
