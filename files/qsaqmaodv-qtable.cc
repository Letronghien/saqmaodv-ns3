/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/**
 * QS-QMAODV Queue-State-Aware Self-Adaptive Q-Table — implementation.
 * See qsaqmaodv-qtable.h for design discussion.
 */

#include "qsaqmaodv-qtable.h"

#include "ns3/log.h"
#include "ns3/simulator.h"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("QsaqmaodvQTable");

namespace qsaqmaodv
{

QTable::QTable(uint32_t maxPaths)
    : m_maxPaths(maxPaths),
      // ---- Initial hyper-params (paper Table 1) ----
      m_alpha(0.5),
      m_gamma(0.9),
      m_epsilon(0.3),
      m_w1(0.40), m_w2(0.30), m_w3(0.10), m_w4(0.20),
      m_mode(QsMode::NORMAL),
      // ---- Adaptation knobs ----
      m_epsilonMin(0.10),
      m_epsilonMax(0.50),
      m_epsilonStep(0.02),
      m_epsilonBump(0.20),
      m_lambda(0.10),
      m_seqNoWindow(Seconds(5.0)),
      m_lowEnergyThresh(0.20),
      m_lowEnergyExit(0.25),
      m_queueHighThresh(0.70),
      m_queueLowThresh(0.30),
      // Normal mode weights
      m_w1Normal(0.40), m_w2Normal(0.30), m_w3Normal(0.10), m_w4Normal(0.20),
      // Low-energy mode weights (energy-first, queue ignored)
      m_w1LowE(0.10),   m_w2LowE(0.10),   m_w3LowE(0.80),   m_w4LowE(0.00),
      // High-load mode weights (queue-first)
      m_w1HighL(0.20),  m_w2HighL(0.20),  m_w3HighL(0.10),  m_w4HighL(0.50)
{
    m_uniform = CreateObject<UniformRandomVariable>();
}

// ============================================================================
// Hyper-parameter configuration
// ============================================================================

void QTable::SetMaxPaths(uint32_t mp)
{
    NS_ASSERT_MSG(mp >= 1, "MaxPaths must be >= 1");
    m_maxPaths = mp;
}

uint32_t QTable::GetMaxPaths() const { return m_maxPaths; }

void QTable::SetLearningParameters(double alpha0, double gamma, double epsilon0)
{
    NS_ASSERT(alpha0  >= 0.0 && alpha0  <= 1.0);
    NS_ASSERT(gamma   >= 0.0 && gamma   <= 1.0);
    NS_ASSERT(epsilon0 >= 0.0 && epsilon0 <= 1.0);
    m_alpha   = alpha0;
    m_gamma   = gamma;
    m_epsilon = epsilon0;
}

void QTable::SetRewardWeights(double w1, double w2, double w3, double w4)
{
    m_w1 = w1; m_w2 = w2; m_w3 = w3; m_w4 = w4;
    m_w1Normal = w1; m_w2Normal = w2; m_w3Normal = w3; m_w4Normal = w4;
}

void QTable::SetLowEnergyThreshold(double frac)  { m_lowEnergyThresh  = frac; }
void QTable::SetQueueHighThreshold(double frac)   { m_queueHighThresh  = frac; }
void QTable::SetQueueLowThreshold(double frac)    { m_queueLowThresh   = frac; }
void QTable::SetSensitivityLambda(double lambda)  { m_lambda           = lambda; }
void QTable::SetSeqNoWindow(Time window)          { m_seqNoWindow      = window; }

// ============================================================================
// SELF-ADAPTIVE CONTROLLER
// ============================================================================

// §4.2 — Adaptive Exploration
void QTable::OnRouteError()
{
    double old = m_epsilon;
    m_epsilon = std::min(m_epsilonMax, m_epsilon + m_epsilonBump);
    NS_LOG_DEBUG("QSAQM ε bump on RERR: " << old << " → " << m_epsilon);
}

void QTable::PeriodicEpsilonDecay()
{
    double old = m_epsilon;
    m_epsilon = std::max(m_epsilonMin, m_epsilon - m_epsilonStep);
    NS_LOG_DEBUG("QSAQM ε decay: " << old << " → " << m_epsilon);
}

// §4.3 — Adaptive Learning Rate
void QTable::RecordSeqNoUpdate()
{
    m_seqEvents.push_back(Simulator::Now());
    PurgeSeqNoEvents();
}

void QTable::PurgeSeqNoEvents()
{
    const Time threshold = Simulator::Now() - m_seqNoWindow;
    while (!m_seqEvents.empty() && m_seqEvents.front() < threshold)
        m_seqEvents.pop_front();
}

uint32_t QTable::GetDeltaSeq() const
{
    const Time threshold = Simulator::Now() - m_seqNoWindow;
    while (!m_seqEvents.empty() && m_seqEvents.front() < threshold)
        m_seqEvents.pop_front();
    return static_cast<uint32_t>(m_seqEvents.size());
}

void QTable::RecomputeAdaptiveAlpha()
{
    uint32_t dSeq  = GetDeltaSeq();
    double newAlpha = 0.1 + 0.8 * (1.0 - std::exp(-m_lambda * static_cast<double>(dSeq)));
    NS_LOG_DEBUG("QSAQM α recomputed: ΔSeq=" << dSeq << " α=" << newAlpha);
    m_alpha = newAlpha;
}

// §4.4 — Queue-State-Aware Reward Weights
// Priority: Low-Energy > High-Load > Normal
// Hysteresis prevents rapid mode oscillation.
void QTable::RecomputeAdaptiveRewardWeights(double energyFraction,
                                            double queueOccupancy)
{
    QsMode newMode = m_mode;

    // --- Determine new mode (priority order) ---
    if (m_mode == QsMode::LOW_ENERGY)
    {
        // Exit LOW_ENERGY only when energy recovers past hysteresis threshold
        if (energyFraction >= m_lowEnergyExit)
            newMode = QsMode::NORMAL;
        // else stay LOW_ENERGY regardless of queue
    }
    else if (energyFraction < m_lowEnergyThresh)
    {
        newMode = QsMode::LOW_ENERGY;
    }
    else if (m_mode == QsMode::HIGH_LOAD)
    {
        // Exit HIGH_LOAD when queue drops below low threshold
        if (queueOccupancy < m_queueLowThresh)
            newMode = QsMode::NORMAL;
    }
    else if (queueOccupancy >= m_queueHighThresh)
    {
        newMode = QsMode::HIGH_LOAD;
    }

    if (newMode == m_mode) return;  // no change, skip log

    m_mode = newMode;
    switch (m_mode)
    {
    case QsMode::LOW_ENERGY:
        m_w1 = m_w1LowE; m_w2 = m_w2LowE; m_w3 = m_w3LowE; m_w4 = m_w4LowE;
        NS_LOG_DEBUG("QSAQM → LOW_ENERGY mode (E_res=" << energyFraction << ")");
        break;
    case QsMode::HIGH_LOAD:
        m_w1 = m_w1HighL; m_w2 = m_w2HighL; m_w3 = m_w3HighL; m_w4 = m_w4HighL;
        NS_LOG_DEBUG("QSAQM → HIGH_LOAD mode (Q_norm=" << queueOccupancy << ")");
        break;
    case QsMode::NORMAL:
    default:
        m_w1 = m_w1Normal; m_w2 = m_w2Normal; m_w3 = m_w3Normal; m_w4 = m_w4Normal;
        NS_LOG_DEBUG("QSAQM → NORMAL mode");
        break;
    }
}

// 4-term reward: ACK + delay + energy + queue-state
double QTable::ComputeReward(double ackSuccess,
                             double delaySec,
                             double energyFrac,
                             double queueOccupancy) const
{
    if (delaySec      < 0.0) delaySec      = 0.0;
    if (queueOccupancy < 0.0) queueOccupancy = 0.0;
    if (queueOccupancy > 1.0) queueOccupancy = 1.0;

    double queueTerm = 1.0 - queueOccupancy;  // (1 − Q_norm): rewards uncongested next-hops

    return m_w1 * ackSuccess
         + m_w2 * (1.0 / (delaySec + 1.0))
         + m_w3 * energyFrac
         + m_w4 * queueTerm;
}

// ============================================================================
// Standard Q-table operations
// ============================================================================

std::vector<QRecord>::iterator QTable::FindWorst(std::vector<QRecord>& vec)
{
    if (vec.empty()) return vec.end();
    auto worst = vec.begin();
    for (auto it = vec.begin() + 1; it != vec.end(); ++it)
        if (it->rt.GetHop() > worst->rt.GetHop()) worst = it;
    return worst;
}

bool QTable::AddRoute(const RoutingTableEntry& rt)
{
    Ipv4Address dst = rt.GetDestination();
    Ipv4Address nh  = rt.GetNextHop();
    auto& vec = m_records[dst];

    for (auto& existing : vec)
    {
        if (existing.rt.GetNextHop() == nh)
        {
            existing.rt = rt;
            return false;
        }
    }

    if (vec.size() < m_maxPaths)
    {
        vec.push_back(QRecord(rt, 0.0));
        ReinitQValues(dst);
        return true;
    }
    auto worst = FindWorst(vec);
    if (worst != vec.end() && rt.GetHop() < worst->rt.GetHop())
    {
        *worst = QRecord(rt, 0.0);
        ReinitQValues(dst);
        return true;
    }
    return false;
}

bool QTable::EnsureRecord(const RoutingTableEntry& rt)
{
    Ipv4Address dst = rt.GetDestination();
    Ipv4Address nh  = rt.GetNextHop();
    auto& vec = m_records[dst];
    for (auto& existing : vec)
    {
        if (existing.rt.GetNextHop() == nh)
        {
            existing.rt = rt;
            return false;
        }
    }
    vec.push_back(QRecord(rt, 0.0));
    ReinitQValues(dst);
    return true;
}

void QTable::ReinitQValues(Ipv4Address dst)
{
    auto it = m_records.find(dst);
    if (it == m_records.end()) return;
    double sumInv = 0.0;
    for (const auto& r : it->second)
        sumInv += 1.0 / std::max<uint32_t>(1, r.rt.GetHop());
    if (sumInv <= 0.0) return;
    for (auto& r : it->second)
    {
        if (r.txCount > 0) continue;  // preserve learned values
        uint32_t hc = std::max<uint32_t>(1, r.rt.GetHop());
        r.qValue = (1.0 / hc) / sumInv;
    }
}

uint32_t QTable::GetRoutes(Ipv4Address dst,
                           std::vector<RoutingTableEntry>& routes,
                           const RoutingTable* mainTable) const
{
    auto it = m_records.find(dst);
    if (it == m_records.end()) return 0;
    uint32_t added = 0;
    for (const auto& r : it->second)
    {
        if (r.rt.GetFlag() != VALID || r.rt.GetLifeTime() <= Time(0)) continue;
        if (mainTable != nullptr)
        {
            RoutingTableEntry nbr;
            if (!const_cast<RoutingTable*>(mainTable)->LookupRoute(r.rt.GetNextHop(), nbr) ||
                nbr.GetFlag() != VALID) continue;
        }
        routes.push_back(r.rt);
        ++added;
    }
    return added;
}

std::vector<QRecord> QTable::BuildCandidates(const RoutingTableEntry& primary,
                                              const RoutingTable* mainTable) const
{
    Ipv4Address dst    = primary.GetDestination();
    Ipv4Address primNh = primary.GetNextHop();
    std::vector<QRecord> cands;

    double primQ    = 0.0;
    bool   primFound = false;
    auto it = m_records.find(dst);
    if (it != m_records.end())
    {
        for (const auto& r : it->second)
            if (r.rt.GetNextHop() == primNh) { primQ = r.qValue; primFound = true; break; }
    }

    if (it != m_records.end())
    {
        for (const auto& r : it->second)
        {
            if (r.rt.GetNextHop() == primNh) continue;
            if (r.rt.GetFlag() != VALID || r.rt.GetLifeTime() <= Time(0)) continue;
            if (mainTable != nullptr)
            {
                RoutingTableEntry nbr;
                if (!const_cast<RoutingTable*>(mainTable)->LookupRoute(r.rt.GetNextHop(), nbr) ||
                    nbr.GetFlag() != VALID) continue;
            }
            cands.push_back(r);
        }
    }

    uint32_t hcP = std::max<uint32_t>(1, primary.GetHop());
    double primQValue;
    if (primFound)
    {
        primQValue = primQ;
    }
    else
    {
        double sumInv = 1.0 / hcP;
        for (const auto& c : cands)
            sumInv += 1.0 / std::max<uint32_t>(1, c.rt.GetHop());
        primQValue = (sumInv > 0.0) ? (1.0 / hcP) / sumInv : 0.5;
    }
    cands.insert(cands.begin(), QRecord(primary, primQValue));
    return cands;
}

bool QTable::SelectEpsilonGreedy(const RoutingTableEntry& primary,
                                 RoutingTableEntry& out,
                                 const RoutingTable* mainTable)
{
    auto cands = BuildCandidates(primary, mainTable);
    if (cands.empty())  { out = primary; return false; }
    if (cands.size() == 1) { out = cands[0].rt; return true; }

    double u = m_uniform->GetValue(0.0, 1.0);
    if (u < m_epsilon)
    {
        uint32_t idx = static_cast<uint32_t>(
            m_uniform->GetValue(0.0, static_cast<double>(cands.size())));
        if (idx >= cands.size()) idx = static_cast<uint32_t>(cands.size()) - 1;
        out = cands[idx].rt;
        return true;
    }

    size_t   bestIdx = 0;
    double   bestQ   = -std::numeric_limits<double>::infinity();
    uint32_t bestHC  = std::numeric_limits<uint32_t>::max();
    for (size_t i = 0; i < cands.size(); ++i)
    {
        double   q  = cands[i].qValue;
        uint32_t hc = cands[i].rt.GetHop();
        if (q > bestQ || (std::fabs(q - bestQ) < 1e-9 && hc < bestHC))
        { bestQ = q; bestHC = hc; bestIdx = i; }
    }
    out = cands[bestIdx].rt;
    return true;
}

void QTable::UpdateQValue(Ipv4Address dst,
                          Ipv4Address nextHop,
                          double ackSuccess,
                          double delaySec,
                          double energyFraction,
                          double queueOccupancy)
{
    double reward = ComputeReward(ackSuccess, delaySec, energyFraction, queueOccupancy);

    auto it = m_records.find(dst);
    if (it == m_records.end()) return;

    QRecord* target   = nullptr;
    double   maxFuture = 0.0;
    for (auto& r : it->second)
    {
        if (r.qValue > maxFuture) maxFuture = r.qValue;
        if (r.rt.GetNextHop() == nextHop) target = &r;
    }
    if (target == nullptr) return;

    double oldQ = target->qValue;
    // Q ← (1 − α_t)·Q + α_t·[r_t + γ·max Q]
    target->qValue  = (1.0 - m_alpha) * oldQ + m_alpha * (reward + m_gamma * maxFuture);
    target->txCount += 1;
    if (ackSuccess > 0.5) target->ackCount += 1;
    target->lastUpd = Simulator::Now();

    NS_LOG_DEBUG("QSAQM Q-update dst=" << dst << " via=" << nextHop
                 << " r=" << reward << " Q: " << oldQ << "→" << target->qValue
                 << " mode=" << (int)m_mode);
}

void QTable::UpdateQValueOrCreate(const RoutingTableEntry& rt,
                                  double ackSuccess,
                                  double delaySec,
                                  double energyFraction,
                                  double queueOccupancy)
{
    EnsureRecord(rt);
    UpdateQValue(rt.GetDestination(), rt.GetNextHop(),
                 ackSuccess, delaySec, energyFraction, queueOccupancy);
}

void QTable::DeleteRoutes(Ipv4Address dst) { m_records.erase(dst); }

void QTable::DeleteRoute(Ipv4Address dst, Ipv4Address nh)
{
    auto it = m_records.find(dst);
    if (it == m_records.end()) return;
    auto& vec = it->second;
    vec.erase(std::remove_if(vec.begin(), vec.end(),
              [&](const QRecord& r) { return r.rt.GetNextHop() == nh; }),
              vec.end());
    if (vec.empty()) m_records.erase(it);
}

void QTable::RemoveNextHopGlobally(Ipv4Address nh)
{
    for (auto it = m_records.begin(); it != m_records.end(); )
    {
        auto& vec = it->second;
        vec.erase(std::remove_if(vec.begin(), vec.end(),
                  [&](const QRecord& r) { return r.rt.GetNextHop() == nh; }),
                  vec.end());
        if (vec.empty()) it = m_records.erase(it); else ++it;
    }
}

uint32_t QTable::Size() const
{
    return std::accumulate(m_records.begin(), m_records.end(), uint32_t{0},
                           [](uint32_t a, const auto& kv)
                           { return a + static_cast<uint32_t>(kv.second.size()); });
}

uint32_t QTable::CountFor(Ipv4Address dst) const
{
    auto it = m_records.find(dst);
    return (it == m_records.end()) ? 0 : static_cast<uint32_t>(it->second.size());
}

bool QTable::IsFull(Ipv4Address dst) const { return CountFor(dst) >= m_maxPaths; }

void QTable::Clear() { m_records.clear(); m_seqEvents.clear(); }

double QTable::GetQValue(Ipv4Address dst, Ipv4Address nh) const
{
    auto it = m_records.find(dst);
    if (it == m_records.end()) return 0.0;
    for (const auto& r : it->second)
        if (r.rt.GetNextHop() == nh) return r.qValue;
    return 0.0;
}

void QTable::Print(std::ostream& os) const
{
    const char* modeStr[] = {"NORMAL", "LOW_ENERGY", "HIGH_LOAD"};
    os << "QS-Q-Table (" << Size() << " entries"
       << " α=" << m_alpha << " γ=" << m_gamma << " ε=" << m_epsilon
       << " w=(" << m_w1 << "," << m_w2 << "," << m_w3 << "," << m_w4 << ")"
       << " mode=" << modeStr[(int)m_mode] << "):\n";
    for (const auto& kv : m_records)
    {
        os << "  dst=" << kv.first << " alts=" << kv.second.size() << "\n";
        for (const auto& r : kv.second)
        {
            os << "    via " << r.rt.GetNextHop()
               << " HC=" << (uint32_t)r.rt.GetHop()
               << " Q=" << r.qValue
               << " tx=" << r.txCount << " ack=" << r.ackCount << "\n";
        }
    }
}

} // namespace qsaqmaodv
} // namespace ns3
