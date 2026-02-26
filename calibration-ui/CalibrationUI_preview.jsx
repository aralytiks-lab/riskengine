import { useState, useEffect, useCallback } from "react";
import { Camera, CheckCircle, AlertTriangle, XCircle, Settings, Shield, BarChart3, Clock, Save, ChevronDown, ChevronRight, RefreshCw } from "lucide-react";

// ── Mock data matching the v1.2 seed ──
const INITIAL_FACTORS = [
  { factor_name: "LTV", weight: 0.15, enabled: true, description: "Loan-to-Value ratio", score_range_min: -8, score_range_max: 8, display_order: 1 },
  { factor_name: "Term", weight: 0.10, enabled: true, description: "Contract term length", score_range_min: -3, score_range_max: 6, display_order: 2 },
  { factor_name: "Age", weight: 0.10, enabled: true, description: "Customer age at application", score_range_min: -10, score_range_max: 7, display_order: 3 },
  { factor_name: "CRIF", weight: 0.15, enabled: true, description: "CRIF bureau score", score_range_min: -8, score_range_max: 8, display_order: 4 },
  { factor_name: "Intrum", weight: 0.10, enabled: true, description: "Intrum collection score", score_range_min: -4, score_range_max: 5, display_order: 5 },
  { factor_name: "DSCR", weight: 0.15, enabled: true, description: "Debt Service Coverage Ratio", score_range_min: -8, score_range_max: 7, display_order: 6 },
  { factor_name: "Permit", weight: 0.10, enabled: true, description: "Party type + residence permit", score_range_min: -3, score_range_max: 5, display_order: 7 },
  { factor_name: "VehiclePriceTier", weight: 0.05, enabled: true, description: "Vehicle price segment", score_range_min: -2, score_range_max: 3, display_order: 8 },
  { factor_name: "ZEK", weight: 0.05, enabled: true, description: "ZEK credit entries", score_range_min: -7, score_range_max: 5, display_order: 9 },
  { factor_name: "DealerRisk", weight: 0.05, enabled: true, description: "Dealer default rate", score_range_min: -6, score_range_max: 4, display_order: 10 },
];

const INITIAL_BINS = {
  LTV: [
    { id: 1, bin_order: 1, bin_label: "<75%", lower_bound: null, upper_bound: 75, raw_score: 8, risk_interpretation: "Strong equity cushion" },
    { id: 2, bin_order: 2, bin_label: "75-85%", lower_bound: 75, upper_bound: 85, raw_score: 4, risk_interpretation: "Adequate equity" },
    { id: 3, bin_order: 3, bin_label: "85-95%", lower_bound: 85, upper_bound: 95, raw_score: 0, risk_interpretation: "Neutral" },
    { id: 4, bin_order: 4, bin_label: ">95%", lower_bound: 95, upper_bound: null, raw_score: -8, risk_interpretation: "Minimal equity" },
    { id: 5, bin_order: 5, bin_label: "MISSING", lower_bound: null, upper_bound: null, raw_score: -5, risk_interpretation: "Cannot assess", is_missing_bin: true },
  ],
  Term: [
    { id: 6, bin_order: 1, bin_label: "≤36m", lower_bound: null, upper_bound: 36, raw_score: 5, risk_interpretation: "Short term" },
    { id: 7, bin_order: 2, bin_label: "37-48m", lower_bound: 37, upper_bound: 48, raw_score: 6, risk_interpretation: "Optimal term" },
    { id: 8, bin_order: 3, bin_label: ">48m", lower_bound: 48, upper_bound: null, raw_score: -3, risk_interpretation: "Long exposure" },
  ],
  Age: [
    { id: 9, bin_order: 1, bin_label: "<18", lower_bound: null, upper_bound: 18, raw_score: -10, risk_interpretation: "Minor" },
    { id: 10, bin_order: 2, bin_label: "18-25", lower_bound: 18, upper_bound: 25, raw_score: -6, risk_interpretation: "Young adult" },
    { id: 11, bin_order: 3, bin_label: "26-35", lower_bound: 26, upper_bound: 35, raw_score: 2, risk_interpretation: "Early career" },
    { id: 12, bin_order: 4, bin_label: "36-45", lower_bound: 36, upper_bound: 45, raw_score: 0, risk_interpretation: "Mid career" },
    { id: 13, bin_order: 5, bin_label: "46-55", lower_bound: 46, upper_bound: 55, raw_score: 7, risk_interpretation: "Peak earning" },
    { id: 14, bin_order: 6, bin_label: "56+", lower_bound: 56, upper_bound: null, raw_score: -2, risk_interpretation: "Senior" },
  ],
  CRIF: [
    { id: 15, bin_order: 1, bin_label: "≥700 (Excellent)", lower_bound: 700, upper_bound: null, raw_score: 8, risk_interpretation: "Top creditworthiness" },
    { id: 16, bin_order: 2, bin_label: "500-699 (Good)", lower_bound: 500, upper_bound: 699, raw_score: 4, risk_interpretation: "Above average" },
    { id: 17, bin_order: 3, bin_label: "300-499 (Fair)", lower_bound: 300, upper_bound: 499, raw_score: -2, risk_interpretation: "Below average" },
    { id: 18, bin_order: 4, bin_label: "<300 (Poor)", lower_bound: null, upper_bound: 300, raw_score: -8, risk_interpretation: "Serious issues" },
    { id: 19, bin_order: 5, bin_label: "MISSING", lower_bound: null, upper_bound: null, raw_score: -5, risk_interpretation: "No data", is_missing_bin: true },
  ],
  Intrum: [
    { id: 20, bin_order: 1, bin_label: "0 (No data)", lower_bound: null, upper_bound: null, raw_score: -4, risk_interpretation: "Unverifiable" },
    { id: 21, bin_order: 2, bin_label: "1", lower_bound: null, upper_bound: null, raw_score: 1, risk_interpretation: "Minimal history" },
    { id: 22, bin_order: 3, bin_label: "2-3", lower_bound: 2, upper_bound: 3, raw_score: -1, risk_interpretation: "Some concerns" },
    { id: 23, bin_order: 4, bin_label: ">3 (Established)", lower_bound: 3, upper_bound: null, raw_score: 5, risk_interpretation: "Proven behaviour" },
  ],
  DSCR: [
    { id: 24, bin_order: 1, bin_label: "<0 (Negative)", lower_bound: null, upper_bound: 0, raw_score: -8, risk_interpretation: "Cannot service" },
    { id: 25, bin_order: 2, bin_label: "0-3 (Tight)", lower_bound: 0, upper_bound: 3, raw_score: -3, risk_interpretation: "Minimal headroom" },
    { id: 26, bin_order: 3, bin_label: "3-7 (Adequate)", lower_bound: 3, upper_bound: 7, raw_score: 0, risk_interpretation: "Meets minimum" },
    { id: 27, bin_order: 4, bin_label: "7-15 (Good)", lower_bound: 7, upper_bound: 15, raw_score: 3, risk_interpretation: "Comfortable" },
    { id: 28, bin_order: 5, bin_label: ">15 (Strong)", lower_bound: 15, upper_bound: null, raw_score: 7, risk_interpretation: "Very strong" },
    { id: 29, bin_order: 6, bin_label: "MISSING", lower_bound: null, upper_bound: null, raw_score: -5, risk_interpretation: "Cannot calculate", is_missing_bin: true },
  ],
  Permit: [
    { id: 30, bin_order: 1, bin_label: "B2B", lower_bound: null, upper_bound: null, raw_score: -3, risk_interpretation: "Business applicant" },
    { id: 31, bin_order: 2, bin_label: "B_permit", lower_bound: null, upper_bound: null, raw_score: -3, risk_interpretation: "Temporary residence" },
    { id: 32, bin_order: 3, bin_label: "C_permit", lower_bound: null, upper_bound: null, raw_score: 5, risk_interpretation: "Permanent settlement" },
    { id: 33, bin_order: 4, bin_label: "L/Diplomat", lower_bound: null, upper_bound: null, raw_score: -1, risk_interpretation: "Short-term" },
    { id: 34, bin_order: 5, bin_label: "Other_B2C", lower_bound: null, upper_bound: null, raw_score: 2, risk_interpretation: "Default category" },
  ],
  VehiclePriceTier: [
    { id: 35, bin_order: 1, bin_label: "≤20k (Economy)", lower_bound: null, upper_bound: 20000, raw_score: -2, risk_interpretation: "Higher LGD" },
    { id: 36, bin_order: 2, bin_label: "20k-50k (Mid)", lower_bound: 20000, upper_bound: 50000, raw_score: 3, risk_interpretation: "Best recovery" },
    { id: 37, bin_order: 3, bin_label: "50k-100k (Premium)", lower_bound: 50000, upper_bound: 100000, raw_score: 2, risk_interpretation: "Good collateral" },
    { id: 38, bin_order: 4, bin_label: ">100k (Luxury)", lower_bound: 100000, upper_bound: null, raw_score: -1, risk_interpretation: "Concentration risk" },
  ],
  ZEK: [
    { id: 39, bin_order: 1, bin_label: "Clean", lower_bound: null, upper_bound: null, raw_score: 5, risk_interpretation: "No negatives" },
    { id: 40, bin_order: 2, bin_label: "1 entry", lower_bound: null, upper_bound: null, raw_score: -3, risk_interpretation: "Isolated incident" },
    { id: 41, bin_order: 3, bin_label: "2+ entries", lower_bound: null, upper_bound: null, raw_score: -7, risk_interpretation: "Pattern" },
    { id: 42, bin_order: 4, bin_label: "NOT_CHECKED", lower_bound: null, upper_bound: null, raw_score: 0, risk_interpretation: "Not queried", is_missing_bin: true },
  ],
  DealerRisk: [
    { id: 43, bin_order: 1, bin_label: "≤3% (Low)", lower_bound: null, upper_bound: 0.03, raw_score: 4, risk_interpretation: "Trusted" },
    { id: 44, bin_order: 2, bin_label: "3-8% (Average)", lower_bound: 0.03, upper_bound: 0.08, raw_score: 0, risk_interpretation: "Normal" },
    { id: 45, bin_order: 3, bin_label: "8-15% (Elevated)", lower_bound: 0.08, upper_bound: 0.15, raw_score: -3, risk_interpretation: "Under watch" },
    { id: 46, bin_order: 4, bin_label: ">15% (High)", lower_bound: 0.15, upper_bound: null, raw_score: -6, risk_interpretation: "Watchlist" },
    { id: 47, bin_order: 5, bin_label: "New/Unknown", lower_bound: null, upper_bound: null, raw_score: -2, risk_interpretation: "Unproven", is_missing_bin: true },
  ],
};

const INITIAL_TIERS = [
  { id: 1, tier_name: "BRIGHT_GREEN", tier_order: 1, min_score: 25, decision: "AUTO_APPROVE", estimated_pd: 0.015, color_hex: "#27AE60", description: "Auto-approve" },
  { id: 2, tier_name: "GREEN", tier_order: 2, min_score: 10, decision: "APPROVE_STANDARD", estimated_pd: 0.035, color_hex: "#2ECC71", description: "Standard approval" },
  { id: 3, tier_name: "YELLOW", tier_order: 3, min_score: 0, decision: "MANUAL_REVIEW", estimated_pd: 0.07, color_hex: "#F39C12", description: "Credit analyst review" },
  { id: 4, tier_name: "RED", tier_order: 4, min_score: null, decision: "DECLINE", estimated_pd: 0.15, color_hex: "#E74C3C", description: "Decline" },
];

const INITIAL_RULES = [
  { id: 1, rule_code: "BR-01", rule_name: "Minor applicant", condition_field: "age", condition_operator: "<", condition_value: "18", enabled: true, severity: "HARD" },
  { id: 2, rule_code: "BR-02", rule_name: "Extreme over-financing", condition_field: "ltv", condition_operator: ">", condition_value: "120", enabled: true, severity: "HARD" },
  { id: 3, rule_code: "BR-03", rule_name: "Negative DSCR", condition_field: "dscr_value", condition_operator: "<", condition_value: "0", enabled: true, severity: "HARD" },
  { id: 4, rule_code: "BR-04", rule_name: "Multiple ZEK negatives", condition_field: "zek_entry_count", condition_operator: ">=", condition_value: "3", enabled: true, severity: "HARD" },
  { id: 5, rule_code: "BR-05", rule_name: "Critical CRIF score", condition_field: "crif_score", condition_operator: "<", condition_value: "150", enabled: true, severity: "HARD" },
  { id: 6, rule_code: "BR-06", rule_name: "No income data (B2C)", condition_field: "monthly_net_income", condition_operator: "<=", condition_value: "0", enabled: true, severity: "HARD" },
  { id: 7, rule_code: "BR-07", rule_name: "Watchlist dealer", condition_field: "dealer_default_rate", condition_operator: ">", condition_value: "0.20", enabled: true, severity: "HARD" },
  { id: 8, rule_code: "BR-08", rule_name: "Excessive term", condition_field: "term_months", condition_operator: ">", condition_value: "72", enabled: true, severity: "HARD" },
];

const AUDIT_LOG = [
  { changed_at: "2026-02-26T14:30:00Z", changed_by: "avi.kannan", action: "PUBLISHED", table_name: "model_version", field_name: null, old_value: null, new_value: "1.2.0" },
  { changed_at: "2026-02-26T14:28:00Z", changed_by: "avi.kannan", action: "UPDATED", table_name: "scoring_factor_bins", field_name: "raw_score", old_value: "-6", new_value: "-8" },
  { changed_at: "2026-02-26T14:25:00Z", changed_by: "system", action: "CREATED", table_name: "model_version", field_name: null, old_value: null, new_value: "1.2.0" },
];

// ── Score bar component ──
function ScoreBar({ score, min, max }) {
  const range = max - min;
  const pct = Math.max(0, Math.min(100, ((score - min) / range) * 100));
  const color = score > 0 ? "#27AE60" : score < 0 ? "#E74C3C" : "#95A5A6";
  const zeroPct = Math.max(0, Math.min(100, ((0 - min) / range) * 100));
  return (
    <div className="relative w-full h-5 bg-gray-100 rounded overflow-hidden">
      <div className="absolute top-0 h-full w-px bg-gray-400" style={{ left: `${zeroPct}%` }} />
      <div
        className="absolute top-0 h-full rounded"
        style={{
          left: score >= 0 ? `${zeroPct}%` : `${pct}%`,
          width: `${Math.abs(pct - zeroPct)}%`,
          backgroundColor: color,
          opacity: 0.7,
        }}
      />
      <span className="absolute inset-0 flex items-center justify-center text-xs font-bold text-gray-700">
        {score > 0 ? "+" : ""}{score}
      </span>
    </div>
  );
}

// ── Main App ──
export default function CalibrationUI() {
  const [tab, setTab] = useState("factors");
  const [factors, setFactors] = useState(INITIAL_FACTORS);
  const [bins, setBins] = useState(INITIAL_BINS);
  const [tiers, setTiers] = useState(INITIAL_TIERS);
  const [rules, setRules] = useState(INITIAL_RULES);
  const [expandedFactor, setExpandedFactor] = useState("LTV");
  const [dirty, setDirty] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const versionId = "1.2.0";

  const handleBinScoreChange = (factorName, binId, newScore) => {
    setBins(prev => ({
      ...prev,
      [factorName]: prev[factorName].map(b => b.id === binId ? { ...b, raw_score: parseFloat(newScore) || 0 } : b),
    }));
    setDirty(true);
  };

  const handleTierChange = (tierId, field, value) => {
    setTiers(prev => prev.map(t => t.id === tierId ? { ...t, [field]: field === "min_score" || field === "estimated_pd" ? parseFloat(value) || 0 : value } : t));
    setDirty(true);
  };

  const handleRuleToggle = (ruleId) => {
    setRules(prev => prev.map(r => r.id === ruleId ? { ...r, enabled: !r.enabled } : r));
    setDirty(true);
  };

  const handleRuleValueChange = (ruleId, value) => {
    setRules(prev => prev.map(r => r.id === ruleId ? { ...r, condition_value: value } : r));
    setDirty(true);
  };

  const handleSave = () => {
    setDirty(false);
    setSaveMsg("Changes saved as draft. Publish to activate.");
    setTimeout(() => setSaveMsg(null), 3000);
  };

  const handlePublish = () => {
    setDirty(false);
    setSaveMsg("Model v1.2.0 published successfully!");
    setTimeout(() => setSaveMsg(null), 3000);
  };

  const tabs = [
    { key: "factors", label: "Scoring Factors", icon: <BarChart3 size={16} /> },
    { key: "tiers", label: "Tier Thresholds", icon: <Settings size={16} /> },
    { key: "rules", label: "Business Rules", icon: <Shield size={16} /> },
    { key: "audit", label: "Audit Log", icon: <Clock size={16} /> },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-800">Risk Engine Calibration</h1>
              <p className="text-sm text-gray-500 mt-1">
                Model <span className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-blue-700">{versionId}</span>
                <span className="ml-2 px-2 py-0.5 bg-green-100 text-green-700 rounded-full text-xs font-medium">PUBLISHED</span>
                <span className="ml-2 text-gray-400">Next calibration: May 2026</span>
              </p>
            </div>
            <div className="flex gap-3">
              {dirty && (
                <span className="flex items-center text-amber-600 text-sm">
                  <AlertTriangle size={14} className="mr-1" /> Unsaved changes
                </span>
              )}
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 flex items-center gap-2"
              >
                <Save size={14} /> Save Draft
              </button>
              <button
                onClick={handlePublish}
                className="px-4 py-2 bg-blue-600 rounded-lg text-sm font-medium text-white hover:bg-blue-700 flex items-center gap-2"
              >
                <CheckCircle size={14} /> Publish
              </button>
            </div>
          </div>
          {saveMsg && (
            <div className="mt-3 p-2 bg-green-50 border border-green-200 rounded text-green-700 text-sm flex items-center">
              <CheckCircle size={14} className="mr-2" /> {saveMsg}
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="max-w-7xl mx-auto px-6">
        <div className="flex border-b border-gray-200 mt-4">
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === t.key
                  ? "border-blue-600 text-blue-700"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* ── Factors Tab ── */}
        {tab === "factors" && (
          <div className="space-y-3">
            {factors.map(f => (
              <div key={f.factor_name} className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
                {/* Factor header */}
                <button
                  onClick={() => setExpandedFactor(expandedFactor === f.factor_name ? null : f.factor_name)}
                  className="w-full flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center gap-4">
                    {expandedFactor === f.factor_name ? <ChevronDown size={16} className="text-gray-400" /> : <ChevronRight size={16} className="text-gray-400" />}
                    <span className="font-semibold text-gray-800">{f.factor_name}</span>
                    <span className="text-xs text-gray-500">{f.description}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-mono">{(f.weight * 100).toFixed(0)}%</span>
                    <span className="text-xs text-gray-400">{f.score_range_min} to +{f.score_range_max}</span>
                    <span className={`w-2 h-2 rounded-full ${f.enabled ? "bg-green-400" : "bg-red-400"}`} />
                  </div>
                </button>

                {/* Expanded bins */}
                {expandedFactor === f.factor_name && bins[f.factor_name] && (
                  <div className="border-t border-gray-100 px-5 py-3 bg-gray-50">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-gray-500 text-xs uppercase tracking-wider">
                          <th className="pb-2 w-8">#</th>
                          <th className="pb-2">Bin</th>
                          <th className="pb-2">Boundaries</th>
                          <th className="pb-2 w-24">Score</th>
                          <th className="pb-2 w-48">Visual</th>
                          <th className="pb-2">Interpretation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bins[f.factor_name].map(b => (
                          <tr key={b.id} className={`border-t border-gray-100 ${b.is_missing_bin ? "bg-amber-50/50" : ""}`}>
                            <td className="py-2 text-gray-400">{b.bin_order}</td>
                            <td className="py-2 font-medium text-gray-800">
                              {b.bin_label}
                              {b.is_missing_bin && <span className="ml-1 text-xs text-amber-600">(missing)</span>}
                            </td>
                            <td className="py-2 text-gray-500 font-mono text-xs">
                              {b.lower_bound != null || b.upper_bound != null
                                ? `${b.lower_bound ?? "−∞"} → ${b.upper_bound ?? "+∞"}`
                                : "categorical"}
                            </td>
                            <td className="py-2">
                              <input
                                type="number"
                                value={b.raw_score}
                                onChange={e => handleBinScoreChange(f.factor_name, b.id, e.target.value)}
                                className="w-20 px-2 py-1 border border-gray-300 rounded text-center font-mono text-sm focus:ring-2 focus:ring-blue-300 focus:border-blue-400 outline-none"
                                step="0.5"
                              />
                            </td>
                            <td className="py-2">
                              <ScoreBar score={b.raw_score} min={f.score_range_min} max={f.score_range_max} />
                            </td>
                            <td className="py-2 text-gray-500 text-xs">{b.risk_interpretation}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* ── Tiers Tab ── */}
        {tab === "tiers" && (
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr className="text-left text-gray-500 text-xs uppercase tracking-wider">
                  <th className="px-5 py-3">Tier</th>
                  <th className="px-5 py-3">Min Score</th>
                  <th className="px-5 py-3">Decision</th>
                  <th className="px-5 py-3">Estimated PD</th>
                  <th className="px-5 py-3">Description</th>
                </tr>
              </thead>
              <tbody>
                {tiers.map(t => (
                  <tr key={t.id} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded-full" style={{ backgroundColor: t.color_hex }} />
                        <span className="font-semibold">{t.tier_name}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      {t.min_score !== null ? (
                        <input
                          type="number"
                          value={t.min_score}
                          onChange={e => handleTierChange(t.id, "min_score", e.target.value)}
                          className="w-20 px-2 py-1 border border-gray-300 rounded text-center font-mono text-sm focus:ring-2 focus:ring-blue-300 outline-none"
                          step="1"
                        />
                      ) : (
                        <span className="text-gray-400 text-xs">−∞ (default)</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <select
                        value={t.decision}
                        onChange={e => handleTierChange(t.id, "decision", e.target.value)}
                        className="px-2 py-1 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-300 outline-none"
                      >
                        <option>AUTO_APPROVE</option>
                        <option>APPROVE_STANDARD</option>
                        <option>MANUAL_REVIEW</option>
                        <option>DECLINE</option>
                      </select>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          value={(t.estimated_pd * 100).toFixed(1)}
                          onChange={e => handleTierChange(t.id, "estimated_pd", parseFloat(e.target.value) / 100)}
                          className="w-20 px-2 py-1 border border-gray-300 rounded text-center font-mono text-sm focus:ring-2 focus:ring-blue-300 outline-none"
                          step="0.1"
                        />
                        <span className="text-gray-400 text-xs">%</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-gray-500">{t.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Rules Tab ── */}
        {tab === "rules" && (
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr className="text-left text-gray-500 text-xs uppercase tracking-wider">
                  <th className="px-5 py-3 w-12">On</th>
                  <th className="px-5 py-3">Code</th>
                  <th className="px-5 py-3">Rule Name</th>
                  <th className="px-5 py-3">Field</th>
                  <th className="px-5 py-3">Operator</th>
                  <th className="px-5 py-3">Threshold</th>
                  <th className="px-5 py-3">Severity</th>
                </tr>
              </thead>
              <tbody>
                {rules.map(r => (
                  <tr key={r.id} className={`border-t border-gray-100 ${!r.enabled ? "opacity-50" : ""}`}>
                    <td className="px-5 py-3">
                      <button
                        onClick={() => handleRuleToggle(r.id)}
                        className={`w-9 h-5 rounded-full transition-colors ${r.enabled ? "bg-green-500" : "bg-gray-300"} relative`}
                      >
                        <div className={`w-4 h-4 bg-white rounded-full shadow absolute top-0.5 transition-transform ${r.enabled ? "translate-x-4" : "translate-x-0.5"}`} />
                      </button>
                    </td>
                    <td className="px-5 py-3 font-mono font-bold text-red-600">{r.rule_code}</td>
                    <td className="px-5 py-3 font-medium">{r.rule_name}</td>
                    <td className="px-5 py-3 font-mono text-xs text-gray-600">{r.condition_field}</td>
                    <td className="px-5 py-3 font-mono text-center">{r.condition_operator}</td>
                    <td className="px-5 py-3">
                      <input
                        type="text"
                        value={r.condition_value}
                        onChange={e => handleRuleValueChange(r.id, e.target.value)}
                        className="w-24 px-2 py-1 border border-gray-300 rounded text-center font-mono text-sm focus:ring-2 focus:ring-blue-300 outline-none"
                      />
                    </td>
                    <td className="px-5 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${r.severity === "HARD" ? "bg-red-100 text-red-700" : "bg-yellow-100 text-yellow-700"}`}>
                        {r.severity}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Audit Tab ── */}
        {tab === "audit" && (
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">Change History</span>
              <button className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1">
                <RefreshCw size={14} /> Refresh
              </button>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr className="text-left text-gray-500 text-xs uppercase tracking-wider">
                  <th className="px-5 py-3">Timestamp</th>
                  <th className="px-5 py-3">User</th>
                  <th className="px-5 py-3">Action</th>
                  <th className="px-5 py-3">Table</th>
                  <th className="px-5 py-3">Field</th>
                  <th className="px-5 py-3">Old Value</th>
                  <th className="px-5 py-3">New Value</th>
                </tr>
              </thead>
              <tbody>
                {AUDIT_LOG.map((a, i) => (
                  <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-5 py-3 text-gray-500 font-mono text-xs">{new Date(a.changed_at).toLocaleString()}</td>
                    <td className="px-5 py-3 font-medium">{a.changed_by}</td>
                    <td className="px-5 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        a.action === "PUBLISHED" ? "bg-green-100 text-green-700" :
                        a.action === "UPDATED" ? "bg-blue-100 text-blue-700" :
                        "bg-gray-100 text-gray-700"
                      }`}>
                        {a.action}
                      </span>
                    </td>
                    <td className="px-5 py-3 font-mono text-xs">{a.table_name}</td>
                    <td className="px-5 py-3 text-gray-500">{a.field_name || "—"}</td>
                    <td className="px-5 py-3 font-mono text-xs text-red-600">{a.old_value || "—"}</td>
                    <td className="px-5 py-3 font-mono text-xs text-green-600">{a.new_value || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
