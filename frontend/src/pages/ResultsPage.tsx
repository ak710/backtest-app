import { useState } from "react";
import { AnalysisResponse, PlotlyChart } from "../types";
import StrategyTable from "../components/StrategyTable";
import LLMInsights from "../components/LLMInsights";
import PlotlyChartComponent from "../components/PlotlyChart";
import ChartModal from "../components/ChartModal";
import SelectionCard from "../components/SelectionCard";

interface Props {
  result: AnalysisResponse;
  onReset: () => void;
  onHistory: () => void;
}

function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-white mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function ResultsPage({ result, onReset, onHistory }: Props) {
  const [activeChart, setActiveChart] = useState<PlotlyChart | null>(null);

  const valid = result.base_strategies.filter((s) => !s.skipped);
  const best = [...valid].sort((a, b) => b.metrics.sharpe - a.metrics.sharpe)[0];
  const bh = result.benchmark ?? null;
  const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

  const isValidChart = (c: PlotlyChart | Record<string, never>): c is PlotlyChart =>
    "figure" in c && !!c.figure;

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-10">
      {/* Modal */}
      {activeChart && (
        <ChartModal chart={activeChart} onClose={() => setActiveChart(null)} />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">
            {result.stock_symbol} – {result.timeframe} analysis
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            {valid.length} strategies tested ·{" "}
            {result.modified_strategies.filter((s) => !s.skipped).length} modifications
            {result.model_used && (
              <span className="ml-2 font-mono text-xs bg-gray-800 text-blue-400 px-2 py-0.5 rounded">
                {result.model_used}
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onHistory}
            className="bg-gray-800 hover:bg-gray-700 text-gray-400 text-sm font-medium rounded-lg px-4 py-2 transition-colors"
          >
            🕐 History
          </button>
          <button
            onClick={onReset}
            className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-medium rounded-lg px-4 py-2 transition-colors"
          >
            ← New Analysis
          </button>
        </div>
      </div>

      {/* Data quality warnings */}
      {result.data_quality && result.data_quality.length > 0 && (
        <div className="bg-yellow-950/60 border border-yellow-700 rounded-xl px-5 py-4 space-y-1">
          <p className="text-xs font-semibold text-yellow-400 uppercase tracking-wide mb-1">Data Quality Warnings</p>
          {result.data_quality.map((issue, i) => (
            <p key={i} className="text-sm text-yellow-300">⚠ {issue}</p>
          ))}
        </div>
      )}

      {/* Summary cards */}
      {best && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <MetricCard
            label="Best Sharpe"
            value={best.metrics.sharpe.toFixed(2)}
            sub={`${best.indicator_name.toUpperCase()} / ${best.strategy_template}`}
          />
          <MetricCard
            label="Best Total Return"
            value={pct(best.metrics.total_return)}
            sub={bh ? `vs B&H ${pct(bh.metrics.total_return)}` : "Best strategy"}
          />
          <MetricCard
            label="Best CAGR"
            value={pct(best.metrics.cagr)}
            sub={bh ? `vs B&H ${pct(bh.metrics.cagr)}` : "Annualized"}
          />
          <MetricCard
            label="Max Drawdown"
            value={pct(Math.abs(best.metrics.max_drawdown))}
            sub={bh ? `B&H DD ${pct(Math.abs(bh.metrics.max_drawdown))}` : "Best strategy"}
          />
        </div>
      )}

      {/* Selection Rationale */}
      <SelectionCard
        rationales={result.selection_rationales ?? []}
        fundamentals={result.fundamental_context ?? null}
      />

      {/* LLM Insights */}
      <LLMInsights
        summary={result.llm_summary}
        topStrategies={result.llm_top_strategies}
        modifications={result.llm_suggested_modifications}
        warnings={result.llm_warnings}
      />

      {/* Walk-forward banner */}
      {result.walk_forward_enabled && result.walk_forward_split_date && (
        <div className="bg-blue-950/50 border border-blue-700 rounded-xl px-5 py-4 flex items-start gap-3">
          <span className="text-blue-400 text-lg mt-0.5">⚡</span>
          <div>
            <p className="text-sm font-semibold text-blue-300">Walk-Forward Validation Enabled</p>
            <p className="text-xs text-blue-400 mt-0.5">
              In-sample period ends <span className="font-mono font-semibold">{result.walk_forward_split_date}</span>.
              Strategy selection and backtests below use only the in-sample data.
              The LLM's top strategies were re-run on the held-out out-of-sample period — see the OOS section below.
            </p>
          </div>
        </div>
      )}

      {/* Base Strategy Table */}
      <StrategyTable
        strategies={result.base_strategies}
        title={result.walk_forward_enabled ? "In-Sample Strategy Results" : "Base Strategy Results"}
        charts={result.strategy_charts}
        onViewGraph={setActiveChart}
        benchmark={bh}
      />

      {/* Modified Strategies Table */}
      {result.modified_strategies.length > 0 && (
        <StrategyTable
          strategies={result.modified_strategies}
          title="LLM-Suggested Modifications"
          charts={result.modified_strategy_charts}
          onViewGraph={setActiveChart}
        />
      )}

      {/* Out-of-Sample Results */}
      {result.walk_forward_enabled && result.oos_strategies.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-blue-800/40" />
            <span className="text-xs font-semibold text-blue-400 uppercase tracking-widest">Out-of-Sample Validation</span>
            <div className="flex-1 h-px bg-blue-800/40" />
          </div>
          <p className="text-xs text-gray-500">
            These are the LLM's top-ranked in-sample strategies, replayed on the held-out{" "}
            {result.walk_forward_split_date ? `data from ${result.walk_forward_split_date} onwards` : "OOS period"}.
            Lower OOS performance relative to IS is normal; large divergence suggests overfitting.
          </p>
          <StrategyTable
            strategies={result.oos_strategies}
            title="Out-of-Sample Results"
            charts={result.oos_strategy_charts}
            onViewGraph={setActiveChart}
          />
        </div>
      )}

      {/* Summary charts (equity curve + performance comparison) */}
      {result.charts.filter(isValidChart).length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">Charts</h2>
          <div className="space-y-6">
            {result.charts.filter(isValidChart).map((chart) => (
              <PlotlyChartComponent key={chart.id} chart={chart} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
