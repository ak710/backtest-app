import { useState, FormEvent } from "react";
import axios from "axios";
import { predictReversal } from "../api";
import { ReversalPrediction, PatternSummary } from "../types";

const LOADING_STEPS = [
  "Fetching historical price data…",
  "Computing technical indicators…",
  "Running pattern similarity search…",
  "Analysing sector peers…",
  "Consulting LLM…",
];

function ProbabilityBar({ probability }: { probability: number }) {
  const clamped = Math.max(0, Math.min(100, probability));
  const color =
    clamped >= 65
      ? "from-emerald-500 to-emerald-400"
      : clamped >= 45
      ? "from-yellow-500 to-yellow-400"
      : "from-red-500 to-red-400";
  const textColor =
    clamped >= 65 ? "text-emerald-400" : clamped >= 45 ? "text-yellow-400" : "text-red-400";

  return (
    <div className="space-y-2">
      <div className="flex items-end justify-between">
        <span className={`text-5xl font-bold ${textColor}`}>{clamped.toFixed(0)}%</span>
        <span className="text-gray-400 text-sm pb-1">uptrend probability</span>
      </div>
      <div className="w-full h-4 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full bg-gradient-to-r ${color} rounded-full transition-all duration-700`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-gray-600">
        <span>0% — Bearish</span>
        <span>50% — Neutral</span>
        <span>100% — Bullish</span>
      </div>
    </div>
  );
}

function Badge({ label, variant }: { label: string; variant: "blue" | "green" | "yellow" | "red" | "gray" }) {
  const colors: Record<string, string> = {
    blue: "bg-blue-900/50 text-blue-300 border-blue-700",
    green: "bg-emerald-900/50 text-emerald-300 border-emerald-700",
    yellow: "bg-yellow-900/50 text-yellow-300 border-yellow-700",
    red: "bg-red-900/50 text-red-300 border-red-700",
    gray: "bg-gray-800 text-gray-400 border-gray-700",
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${colors[variant]}`}>
      {label}
    </span>
  );
}

function PatternPanel({ summary, label }: { summary: PatternSummary; label: string }) {
  if (!summary || (summary.match_count === 0 && !summary.error)) return null;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
      <h3 className="text-sm font-semibold text-gray-300">{label}</h3>
      {summary.error ? (
        <p className="text-sm text-gray-500 italic">{summary.error}</p>
      ) : (
        <>
          <p className="text-sm text-gray-400">
            Found <span className="text-white font-medium">{summary.match_count}</span> similar historical
            bars (avg similarity:{" "}
            <span className="text-white font-medium">{(summary.avg_similarity * 100).toFixed(0)}%</span>)
          </p>
          <div className="grid grid-cols-3 gap-2">
            {(["4w", "8w", "12w"] as const).map((h) => {
              const stats = summary.horizons[h];
              if (!stats || stats.uptrend_pct == null) return null;
              const color =
                stats.uptrend_pct >= 65
                  ? "text-emerald-400"
                  : stats.uptrend_pct >= 45
                  ? "text-yellow-400"
                  : "text-red-400";
              return (
                <div key={h} className="bg-gray-800 rounded-lg p-3 text-center">
                  <div className="text-xs text-gray-500 mb-1">{h} forward</div>
                  <div className={`text-lg font-bold ${color}`}>{stats.uptrend_pct}%</div>
                  <div className="text-xs text-gray-500">uptrend</div>
                  {stats.median_return_pct != null && (
                    <div className={`text-xs mt-1 ${stats.median_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {stats.median_return_pct >= 0 ? "+" : ""}{stats.median_return_pct.toFixed(1)}% median
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {summary.matches && summary.matches.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-gray-500 font-medium">Top similar bars:</p>
              {summary.matches.slice(0, 4).map((m, i) => (
                <div key={i} className="flex items-center justify-between text-xs text-gray-400 bg-gray-800 rounded px-2 py-1">
                  <span>{m.date} <span className="text-gray-600">(sim {(m.similarity * 100).toFixed(0)}%)</span></span>
                  <span className="flex gap-2">
                    {m.fwd_4w_pct != null && (
                      <span className={m.fwd_4w_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                        4w: {m.fwd_4w_pct >= 0 ? "+" : ""}{m.fwd_4w_pct.toFixed(1)}%
                      </span>
                    )}
                    {m.fwd_8w_pct != null && (
                      <span className={m.fwd_8w_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                        8w: {m.fwd_8w_pct >= 0 ? "+" : ""}{m.fwd_8w_pct.toFixed(1)}%
                      </span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function PeerPatternsPanel({ peers }: { peers: PatternSummary[] }) {
  const valid = peers.filter((p) => p.match_count > 0);
  if (valid.length === 0) return null;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
      <h3 className="text-sm font-semibold text-gray-300">Sector Peer Analysis</h3>
      <div className="space-y-2">
        {valid.map((p, i) => {
          const h8 = p.horizons["8w"];
          return (
            <div key={p.ticker ?? i} className="flex items-center justify-between bg-gray-800 rounded-lg px-3 py-2">
              <span className="text-sm font-medium text-white">{p.ticker}</span>
              <div className="flex items-center gap-3 text-xs text-gray-400">
                <span>{p.match_count} matches</span>
                {h8?.uptrend_pct != null && (
                  <span className={h8.uptrend_pct >= 50 ? "text-emerald-400" : "text-red-400"}>
                    8w: {h8.uptrend_pct}% uptrend
                  </span>
                )}
                {h8?.median_return_pct != null && (
                  <span className={h8.median_return_pct >= 0 ? "text-emerald-400" : "text-red-400"}>
                    {h8.median_return_pct >= 0 ? "+" : ""}{h8.median_return_pct.toFixed(1)}%
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function ReversalPage() {
  const [ticker, setTicker] = useState("");
  const [peersInput, setPeersInput] = useState("");
  const [model, setModel] = useState("nvidia/nemotron-3-super-120b-a12b:free");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ReversalPrediction | null>(null);
  const [showFullAnalysis, setShowFullAnalysis] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const sym = ticker.trim().toUpperCase();
    if (!sym) return setError("Please enter a stock ticker.");

    setError(null);
    setResult(null);
    setLoading(true);
    setLoadingStep(0);

    const stepInterval = setInterval(() => {
      setLoadingStep((s) => Math.min(s + 1, LOADING_STEPS.length - 1));
    }, 8000);

    const peerTickers = peersInput
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);

    try {
      const data = await predictReversal(sym, peerTickers.length > 0 ? peerTickers : undefined, model.trim() || undefined);
      setResult(data);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail ?? err.message;
        setError(typeof detail === "string" ? detail : JSON.stringify(detail));
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      clearInterval(stepInterval);
      setLoading(false);
    }
  };

  const pred = result?.prediction;
  const confidenceVariant =
    pred?.confidence === "high" ? "green" : pred?.confidence === "medium" ? "yellow" : "gray";
  const strengthVariant =
    pred?.signal_strength === "strong" ? "green" : pred?.signal_strength === "moderate" ? "yellow" : "gray";

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <div className="border-b border-gray-800 bg-gray-900">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-white">Reversal Predictor</h1>
            <p className="text-xs text-gray-500">Pattern-matching + LLM uptrend analysis</p>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        {/* Input form */}
        <form onSubmit={handleSubmit} className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Analyse a Stock</h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Stock Ticker</label>
              <input
                type="text"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                placeholder="e.g. AAPL"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-600 focus:outline-none focus:border-blue-500 text-sm"
                disabled={loading}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Peer Tickers <span className="text-gray-600">(optional, comma-separated)</span>
              </label>
              <input
                type="text"
                value={peersInput}
                onChange={(e) => setPeersInput(e.target.value)}
                placeholder="Auto-detected from sector"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-600 focus:outline-none focus:border-blue-500 text-sm"
                disabled={loading}
              />
            </div>
          </div>

          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            {showAdvanced ? "▲ Hide" : "▼ Show"} advanced options
          </button>

          {showAdvanced && (
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">OpenRouter Model</label>
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-600 focus:outline-none focus:border-blue-500 text-sm font-mono"
                disabled={loading}
              />
            </div>
          )}

          {error && (
            <div className="bg-red-900/30 border border-red-800 rounded-lg px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !ticker.trim()}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-semibold py-2.5 px-4 rounded-lg transition-colors text-sm"
          >
            {loading ? "Analysing…" : "Predict Reversal"}
          </button>
        </form>

        {/* Loading state */}
        {loading && (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 flex flex-col items-center gap-4">
            <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-gray-400">{LOADING_STEPS[loadingStep]}</p>
            <div className="flex gap-1">
              {LOADING_STEPS.map((_, i) => (
                <div
                  key={i}
                  className={`w-2 h-2 rounded-full transition-colors ${i <= loadingStep ? "bg-blue-500" : "bg-gray-700"}`}
                />
              ))}
            </div>
            <p className="text-xs text-gray-600 text-center max-w-sm">
              Fetching ~5 years of data, running pattern matching across this stock and sector peers,
              then consulting the LLM. This may take up to 60 seconds.
            </p>
          </div>
        )}

        {/* Results */}
        {result && pred && (
          <div className="space-y-4">
            {/* Header card */}
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-4">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-2xl font-bold text-white">{result.ticker}</h2>
                  {result.company_name !== result.ticker && (
                    <p className="text-sm text-gray-400">{result.company_name}</p>
                  )}
                </div>
                <div className="text-right">
                  <p className="text-xl font-semibold text-white">${Number(result.current_price).toFixed(2)}</p>
                  {result.change_percent != null && (
                    <p className={`text-sm ${Number(result.change_percent) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {Number(result.change_percent) >= 0 ? "+" : ""}{Number(result.change_percent).toFixed(2)}% today
                    </p>
                  )}
                  <p className="text-xs text-gray-600">as of {result.as_of}</p>
                </div>
              </div>

              <ProbabilityBar probability={pred.uptrend_probability} />

              <div className="flex flex-wrap gap-2 items-center">
                <Badge label={`${pred.timeframe_estimate} outlook`} variant="blue" />
                <Badge label={`${pred.confidence} confidence`} variant={confidenceVariant} />
                <Badge label={`${pred.signal_strength} signals`} variant={strengthVariant} />
                {result.peers_analyzed.length > 0 && (
                  <Badge label={`${result.peers_analyzed.length} peers analysed`} variant="gray" />
                )}
                <Badge label={`${result.weekly_bars} weekly bars`} variant="gray" />
              </div>

              {pred.historical_evidence_summary && (
                <p className="text-sm text-gray-400 italic border-l-2 border-blue-700 pl-3">
                  {pred.historical_evidence_summary}
                </p>
              )}
            </div>

            {/* Signal columns */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {/* Bullish */}
              <div className="bg-gray-900 border border-emerald-900/50 rounded-xl p-4 space-y-2">
                <h3 className="text-xs font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
                  <span>▲</span> Bullish Signals
                </h3>
                {pred.bullish_signals.length === 0 ? (
                  <p className="text-xs text-gray-600 italic">None identified</p>
                ) : (
                  <ul className="space-y-1.5">
                    {pred.bullish_signals.map((s, i) => (
                      <li key={i} className="text-xs text-gray-300 flex gap-2">
                        <span className="text-emerald-500 flex-shrink-0">•</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Bearish */}
              <div className="bg-gray-900 border border-red-900/50 rounded-xl p-4 space-y-2">
                <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wider flex items-center gap-1">
                  <span>▼</span> Bearish Signals
                </h3>
                {pred.bearish_signals.length === 0 ? (
                  <p className="text-xs text-gray-600 italic">None identified</p>
                ) : (
                  <ul className="space-y-1.5">
                    {pred.bearish_signals.map((s, i) => (
                      <li key={i} className="text-xs text-gray-300 flex gap-2">
                        <span className="text-red-500 flex-shrink-0">•</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Neutral */}
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-2">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  — Neutral / Mixed
                </h3>
                {pred.neutral_signals.length === 0 ? (
                  <p className="text-xs text-gray-600 italic">None</p>
                ) : (
                  <ul className="space-y-1.5">
                    {pred.neutral_signals.map((s, i) => (
                      <li key={i} className="text-xs text-gray-400 flex gap-2">
                        <span className="text-gray-600 flex-shrink-0">•</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            {/* Historical pattern evidence */}
            <PatternPanel summary={result.own_stock_pattern} label={`Historical Patterns — ${result.ticker}`} />

            {/* Peer analysis */}
            <PeerPatternsPanel peers={result.peer_patterns} />

            {/* Key levels */}
            {(pred.key_support_level != null || pred.key_resistance_level != null) && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-gray-300 mb-3">Key Price Levels</h3>
                <div className="flex gap-4">
                  {pred.key_support_level != null && (
                    <div className="bg-emerald-900/20 border border-emerald-800/50 rounded-lg px-4 py-3 text-center">
                      <div className="text-xs text-emerald-500 mb-1">Support</div>
                      <div className="text-lg font-bold text-emerald-400">${pred.key_support_level.toFixed(2)}</div>
                    </div>
                  )}
                  {pred.key_resistance_level != null && (
                    <div className="bg-red-900/20 border border-red-800/50 rounded-lg px-4 py-3 text-center">
                      <div className="text-xs text-red-500 mb-1">Resistance</div>
                      <div className="text-lg font-bold text-red-400">${pred.key_resistance_level.toFixed(2)}</div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Full LLM analysis */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
              <button
                onClick={() => setShowFullAnalysis(!showFullAnalysis)}
                className="w-full flex items-center justify-between text-sm font-semibold text-gray-300 hover:text-white transition-colors"
              >
                <span>LLM Analysis</span>
                <span className="text-gray-500">{showFullAnalysis ? "▲ Collapse" : "▼ Expand"}</span>
              </button>
              {showFullAnalysis && (
                <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-wrap">{pred.analysis}</p>
              )}
            </div>

            {/* Risk factors */}
            {pred.risk_factors.length > 0 && (
              <div className="bg-yellow-900/10 border border-yellow-800/40 rounded-xl p-4 space-y-2">
                <h3 className="text-xs font-semibold text-yellow-400 uppercase tracking-wider">Risk Factors</h3>
                <ul className="space-y-1.5">
                  {pred.risk_factors.map((r, i) => (
                    <li key={i} className="text-xs text-yellow-200/70 flex gap-2">
                      <span className="text-yellow-500 flex-shrink-0">⚠</span>
                      <span>{r}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Disclaimer */}
            <p className="text-xs text-gray-600 text-center pb-4">
              Not financial advice. Pattern-based analysis is probabilistic and past patterns do not guarantee future results.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
