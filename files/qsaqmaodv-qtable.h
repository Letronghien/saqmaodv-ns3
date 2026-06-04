/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/**
 * Queue-State-Aware Self-Adaptive Q-Table for QS-QMAODV.
 *
 * Extends QMAODV's QTable with three adaptive mechanisms:
 *
 *   (1) Adaptive Exploration ε_t  (§4.2):
 *         on RERR  : ε_t = min(0.5, ε_t + 0.2)
 *         periodic : ε_t = max(0.1, ε_t − 0.02)
 *
 *   (2) Adaptive Learning Rate α_t  (§4.3):
 *         α_t = 0.1 + 0.8·(1 − exp(−λ·Δ_Seq))  ∈ [0.1, 0.9]
 *
 *   (3) Queue-State-Aware Reward Function  (§4.4) — KEY CONTRIBUTION:
 *         r_t = w1(t)·ACK + w2(t)·1/(delay+1) + w3(t)·E_res + w4(t)·(1−Q_norm)
 *
 *         where Q_norm = queue_occupancy / queue_capacity ∈ [0,1]
 *         (1 − Q_norm) rewards next-hops with available queue space.
 *
 *         Three operating modes driven by node state:
 *           Normal    : (w1,w2,w3,w4) = (0.40, 0.30, 0.10, 0.20)
 *           Low-Energy: (w1,w2,w3,w4) = (0.10, 0.10, 0.80, 0.00)  E_res < 20%
 *           High-Load : (w1,w2,w3,w4) = (0.20, 0.20, 0.10, 0.50)  Q_norm > 70%
 *
 * Low-Energy and High-Load modes use hysteresis to avoid oscillation.
 */

#ifndef QSAQMAODV_QTABLE_H
#define QSAQMAODV_QTABLE_H

#include "qsaqmaodv-rtable.h"

#include "ns3/ipv4-address.h"
#include "ns3/nstime.h"
#include "ns3/random-variable-stream.h"

#include <deque>
#include <map>
#include <vector>

namespace ns3
{
namespace qsaqmaodv
{

/// One Q-learning record per (destination, next-hop) pair.
struct QRecord
{
    RoutingTableEntry rt;
    double            qValue;
    uint32_t          txCount;
    uint32_t          ackCount;
    Time              lastUpd;

    QRecord() : qValue(0.0), txCount(0), ackCount(0), lastUpd(Seconds(0)) {}
    QRecord(const RoutingTableEntry& e, double q)
        : rt(e), qValue(q), txCount(0), ackCount(0), lastUpd(Seconds(0)) {}
};

/// Operating mode of the queue-state-aware reward function.
enum class QsMode { NORMAL, LOW_ENERGY, HIGH_LOAD };

/**
 * \brief Queue-State-Aware Self-Adaptive Q-Table.
 */
class QTable
{
  public:
    QTable(uint32_t maxPaths = 3);

    void     SetMaxPaths(uint32_t mp);
    uint32_t GetMaxPaths() const;

    // ---- Static hyper-parameters (initial values) -------------------------
    void SetLearningParameters(double alpha0, double gamma, double epsilon0);
    void SetRewardWeights(double w1, double w2, double w3, double w4 = 0.20);

    // ---- Self-Adaptive controller -----------------------------------------
    /** RERR-triggered ε bump. Call from RecvError(). */
    void OnRouteError();

    /** Periodic ε decay. Call every PeriodicAdaptInterval. */
    void PeriodicEpsilonDecay();

    /** Record a destination-SeqNo update (drives α_t). */
    void RecordSeqNoUpdate();

    /** Recompute α_t = 0.1 + 0.8·(1 − exp(−λ·Δ_Seq)). */
    void RecomputeAdaptiveAlpha();

    /**
     * \brief Update operating mode and reward weights from node state.
     *
     * Priority: Low-Energy > High-Load > Normal.
     * Hysteresis: Low-Energy exits when E_res > 25%; High-Load exits when
     * Q_norm < queueLowThresh.
     *
     * \param energyFraction  Residual energy fraction ∈ [0,1].
     * \param queueOccupancy  Interface queue occupancy ∈ [0,1].
     */
    void RecomputeAdaptiveRewardWeights(double energyFraction,
                                        double queueOccupancy);

    // Knobs
    void SetLowEnergyThreshold(double frac);
    void SetQueueHighThreshold(double frac);
    void SetQueueLowThreshold(double frac);
    void SetSensitivityLambda(double lambda);
    void SetSeqNoWindow(Time window);

    // Read accessors (logging / paper traces)
    double   GetAlpha()   const { return m_alpha; }
    double   GetGamma()   const { return m_gamma; }
    double   GetEpsilon() const { return m_epsilon; }
    double   GetW1()      const { return m_w1; }
    double   GetW2()      const { return m_w2; }
    double   GetW3()      const { return m_w3; }
    double   GetW4()      const { return m_w4; }
    QsMode   GetMode()    const { return m_mode; }
    uint32_t GetDeltaSeq() const;

    // ---- Standard Q-table operations (same shape as QMAODV) ---------------
    bool AddRoute(const RoutingTableEntry& rt);
    void ReinitQValues(Ipv4Address dst);
    uint32_t GetRoutes(Ipv4Address dst,
                       std::vector<RoutingTableEntry>& routes,
                       const RoutingTable* mainTable = nullptr) const;

    bool SelectEpsilonGreedy(const RoutingTableEntry& primary,
                             RoutingTableEntry& out,
                             const RoutingTable* mainTable = nullptr);

    /**
     * \brief Update Q for (dst, nextHop) using adaptive α_t and 4-term reward r_t.
     *
     * \param queueOccupancy  Queue occupancy of the selected next-hop ∈ [0,1].
     *                        Pass 0.0 if not available.
     */
    void UpdateQValue(Ipv4Address dst,
                      Ipv4Address nextHop,
                      double ackSuccess,
                      double delaySec,
                      double energyFraction = 1.0,
                      double queueOccupancy = 0.0);

    bool EnsureRecord(const RoutingTableEntry& rt);
    void UpdateQValueOrCreate(const RoutingTableEntry& rt,
                              double ackSuccess,
                              double delaySec,
                              double energyFraction = 1.0,
                              double queueOccupancy = 0.0);

    void DeleteRoutes(Ipv4Address dst);
    void DeleteRoute(Ipv4Address dst, Ipv4Address nextHop);
    void RemoveNextHopGlobally(Ipv4Address nextHop);

    uint32_t Size() const;
    uint32_t CountFor(Ipv4Address dst) const;
    bool     IsFull(Ipv4Address dst) const;
    void     Clear();
    void     Print(std::ostream& os) const;
    double   GetQValue(Ipv4Address dst, Ipv4Address nextHop) const;

  private:
    std::vector<QRecord>::iterator FindWorst(std::vector<QRecord>& vec);
    std::vector<QRecord> BuildCandidates(const RoutingTableEntry& primary,
                                         const RoutingTable* mainTable) const;

    /** Compute 4-term reward r_t. */
    double ComputeReward(double ackSuccess,
                         double delaySec,
                         double energyFrac,
                         double queueOccupancy) const;

    void PurgeSeqNoEvents();

    // Per-destination alternates with learned Q.
    std::map<Ipv4Address, std::vector<QRecord>> m_records;
    uint32_t m_maxPaths;

    // ---- Adaptive hyper-parameters (live state) ---------------------------
    double m_alpha;
    double m_gamma;
    double m_epsilon;
    double m_w1, m_w2, m_w3, m_w4;
    QsMode m_mode;

    // ---- Adaptation knobs -------------------------------------------------
    double m_epsilonMin;        // 0.10
    double m_epsilonMax;        // 0.50
    double m_epsilonStep;       // 0.02
    double m_epsilonBump;       // 0.20
    double m_lambda;            // 0.10
    Time   m_seqNoWindow;       // 5 s
    double m_lowEnergyThresh;   // 0.20 (entry); exit at 0.25
    double m_lowEnergyExit;     // 0.25
    double m_queueHighThresh;   // 0.70 (HIGH_LOAD entry)
    double m_queueLowThresh;    // 0.30 (HIGH_LOAD exit)

    // Normal-mode reward weights
    double m_w1Normal, m_w2Normal, m_w3Normal, m_w4Normal;
    // Low-energy mode reward weights
    double m_w1LowE, m_w2LowE, m_w3LowE, m_w4LowE;
    // High-load mode reward weights
    double m_w1HighL, m_w2HighL, m_w3HighL, m_w4HighL;

    // Δ_Seq sliding window
    mutable std::deque<Time> m_seqEvents;

    Ptr<UniformRandomVariable> m_uniform;
};

} // namespace qsaqmaodv
} // namespace ns3

#endif /* QSAQMAODV_QTABLE_H */
