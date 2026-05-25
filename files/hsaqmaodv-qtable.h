/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/**
 * H-SAQMAODV Hybrid Q-Table (Topology-Aware 3-Mode Switching).
 *
 * Extends saqmaodv::QTable with Topology Volatility Indicator (TVI):
 *
 *   TVI = DeltaSeq_count / seqNoWindow_seconds
 *
 *   TVI > tviHigh  ->  MODE_BYPASS : return primary route directly (AODV-like)
 *   TVI < tviLow   ->  MODE_GREEDY : return highest-Q route (epsilon forced 0)
 *   otherwise      ->  MODE_EXPLORE: standard epsilon-greedy (SA-QMAODV default)
 *
 * Integration into routing protocol:
 *   1. Add  #include "hsaqmaodv-qtable.h"  beside saqmaodv-qtable.h
 *   2. Add  hsaqmaodv::QTable m_hqtable  member (or change m_qtable type)
 *   3. Call m_hqtable.SetTVIThresholds(high, low)  in Start()
 *   4. Replace SelectEpsilonGreedy() calls with SelectHybridRoute()
 */

#ifndef HSAQMAODV_QTABLE_H
#define HSAQMAODV_QTABLE_H

#include "saqmaodv-qtable.h"
#include "ns3/nstime.h"
#include <string>

namespace ns3 {
namespace hsaqmaodv {

/** Routing mode chosen by TVI. */
enum TopologyMode
{
    MODE_BYPASS  = 0, ///< Too dynamic - use primary route directly
    MODE_EXPLORE = 1, ///< Sweet spot  - epsilon-greedy (SA-QMAODV default)
    MODE_GREEDY  = 2, ///< Stable      - exploit best Q-value (epsilon = 0)
};

/**
 * \brief H-SAQMAODV Hybrid QTable.
 *
 * Inherits the full SA adaptive controller (adaptive epsilon, alpha,
 * reward weights) from saqmaodv::QTable and adds 3-mode route selection.
 */
class QTable : public saqmaodv::QTable
{
  public:
    /**
     * \param maxPaths  Max alternate routes per destination (default 3).
     * \param tviHigh   TVI above which MODE_BYPASS activates (default 3.0).
     * \param tviLow    TVI below which MODE_GREEDY activates  (default 1.0).
     */
    explicit QTable(uint32_t maxPaths = 3,
                    double   tviHigh  = 3.0,
                    double   tviLow   = 1.0);

    // ---- TVI thresholds -----------------------------------------------------
    void   SetTVIThresholds(double tviHigh, double tviLow);
    double GetTVIHigh() const { return m_tviHigh; }
    double GetTVILow()  const { return m_tviLow;  }

    // ---- Mode query ---------------------------------------------------------
    TopologyMode GetCurrentMode() const;  ///< O(1): compare TVI vs thresholds
    std::string  GetModeName()    const;  ///< "BYPASS"|"EXPLORE"|"GREEDY"
    double       GetTVI()         const;  ///< Raw TVI value for logging

    // ---- Core contribution: 3-mode route selection --------------------------
    /**
     * \brief Topology-aware route selection.
     *
     *  MODE_BYPASS  -> out = primary  (no Q-table access)
     *  MODE_GREEDY  -> out = route with max Q-value for primary.GetDst()
     *  MODE_EXPLORE -> delegates to saqmaodv::QTable::SelectEpsilonGreedy()
     *
     * \return true if out was filled; false if Q-table empty for destination.
     */
    bool SelectHybridRoute(const saqmaodv::RoutingTableEntry& primary,
                           saqmaodv::RoutingTableEntry&       out,
                           const saqmaodv::RoutingTable*      mainTable = nullptr);

  private:
    double m_tviHigh;
    double m_tviLow;

    /// Select route with maximum Q-value (used in MODE_GREEDY).
    bool SelectGreedy(const saqmaodv::RoutingTableEntry& primary,
                      saqmaodv::RoutingTableEntry&       out,
                      const saqmaodv::RoutingTable*      mainTable) const;

    /// Get seqNoWindow length as floating-point seconds.
    double GetSeqNoWindowSeconds() const;
};

} // namespace hsaqmaodv
} // namespace ns3

#endif /* HSAQMAODV_QTABLE_H */
