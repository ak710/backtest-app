import { AnalysisResponse } from "../types";
import StrategyTable from "../components/StrategyTable";
import LLMInsights from "../components/LLMInsights";
import PlotlyChart from "../components/PlotlyChart";

interface Props {
  result: AnalysisResponse;
  onReset: () => void;
}

function MetricCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-white mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function ResultsPage({ result, onReset }: Props) {
  const valid = result.base_strategies.filter((s) => !s.skipped);
  const best = valid.sort((a, b) => b.metrics.sharpe - a.metrics.sharpe)[0];

  const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-10">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">
            {result.stock_symbol} – {result.timeframe} analysis
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            {valid.length} strategies tested · {result.modified_strategies.filter((s) => !s.skipped).length} modifications
            {result.model_used && (
              <span className="ml-2 font-mono text-xs bg-gray-800 text-blue-400 px-2 py-0.5 rounded">
                {result.model_used}
              </span>
            )}
          </p>
        </div>
        <button
          onClick={onReset}
          className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-medium rounded-lg px-4 py-2 transition-colors"
        >
          ← New Analysis
        </button>
      </div>

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
            sub="Best strategy"
          />
          <MetricCard
            label="Best CAGR"
            value={pct(best.metrics.cagr)}
            sub="Annualized"
          />
          <MetricCard
            label="Max Drawdown"
            value={pct(Math.abs(best.metrics.max_drawdown))}
            sub="Best strategy"
          />
        </div>
      )}

      {/* LLM Insights */}
      <LLMInsights
        summary={result.llm_summary}
        topStrategies={result.llm_top_strategies}
        modifications={result.llm_suggested_modifications}
        warnings={result.llm_warnings}
      />

      {/* Strategy Tables */}
      <StrategyTable
        strategies={result.base_strategies}
        title="Base Strategy Results"
      />

      {result.modified_strategies.length > 0 && (
        <StrategyTable
          strategies={result.modified_strategies}
          title="LLM-Suggested Modifications"
        />
      )}

      {/* Charts */}
      {result.charts.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">Charts</h2>
          <div className="space-y-6">
            {result.charts.map((chart) => (
              <PlotlyChart key={chart.id} chart={chart} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
