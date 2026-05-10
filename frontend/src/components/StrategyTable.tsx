import { StrategyResult, PlotlyChart } from "../types";

interface Props {
  strategies: StrategyResult[];
  title: string;
  charts?: (PlotlyChart | Record<string, never>)[];
  onViewGraph?: (chart: PlotlyChart) => void;
  benchmark?: StrategyResult | null;
}

const pct = (v: number) => `${(v * 100).toFixed(2)}%`;
const num = (v: number, d = 3) => v.toFixed(d);

const TOOLTIPS: Record<string, string> = {
  "Total Return": "Net % gain from start to end, including all trades.",
  CAGR: "Compound Annual Growth Rate — annualised total return.",
  Sharpe: "Risk-adjusted return: excess return ÷ volatility. >1 is good, >2 is excellent.",
  "Max DD": "Worst peak-to-trough decline. Lower is better (e.g. <20% is healthy).",
  Volatility: "Annualised standard deviation of bar returns.",
  Trades: "Number of completed round-trip trades.",
  "Win Rate": "% of trades that closed with a profit.",
};

function MetricCell({ value, good }: { value: string; good: boolean | null }) {
  const color =
    good === null ? "text-gray-300" : good ? "text-emerald-400" : "text-red-400";
  return <td className={`px-3 py-2 text-right text-sm ${color}`}>{value}</td>;
}

function TH({ label }: { label: string }) {
  const tip = TOOLTIPS[label];
  return (
    <th
      className={`px-3 py-3 text-right text-xs uppercase tracking-wide ${tip ? "cursor-help underline decoration-dotted decoration-gray-600" : ""}`}
      title={tip}
    >
      {label}
      {tip && <span className="ml-0.5 text-gray-600 text-[10px] align-super">ⓘ</span>}
    </th>
  );
}

function BenchmarkRow({ bh, hasCharts }: { bh: StrategyResult; hasCharts: boolean }) {
  const m = bh.metrics;
  return (
    <tr className="bg-yellow-950/30 border-b border-yellow-800/40">
      <td className="px-3 py-2 font-medium text-yellow-400 text-sm">★ Buy &amp; Hold</td>
      <td className="px-3 py-2 text-yellow-600 text-xs">benchmark</td>
      <MetricCell value={pct(m.total_return)} good={m.total_return > 0} />
      <MetricCell value={pct(m.cagr)} good={m.cagr > 0} />
      <MetricCell value={num(m.sharpe)} good={m.sharpe > 0.5} />
      <MetricCell value={pct(Math.abs(m.max_drawdown))} good={Math.abs(m.max_drawdown) < 0.2} />
      <MetricCell value={pct(m.volatility)} good={null} />
      <td className="px-3 py-2 text-right text-yellow-600 text-sm">1</td>
      <MetricCell value={pct(m.win_rate)} good={m.win_rate > 0.5} />
      {hasCharts && <td className="px-3 py-2" />}
    </tr>
  );
}

export default function StrategyTable({ strategies, title, charts = [], onViewGraph, benchmark }: Props) {
  const valid = strategies.filter((s) => !s.skipped);
  const skipped = strategies.filter((s) => s.skipped);

  if (valid.length === 0 && skipped.length === 0) return null;

  const sorted = strategies
    .map((s, originalIndex) => ({ s, originalIndex }))
    .filter(({ s }) => !s.skipped)
    .sort((a, b) => (b.s.metrics?.sharpe ?? 0) - (a.s.metrics?.sharpe ?? 0));

  const hasCharts = charts.some((c) => c && "figure" in c);

  const handleExportCSV = () => {
    const headers = ["Indicator", "Strategy", "Total Return %", "CAGR %", "Sharpe", "Max DD %", "Volatility %", "Trades", "Win Rate %"];

    const strategyRows = sorted.map(({ s }) => {
      const m = s.metrics;
      return [
        s.indicator_name.toUpperCase(),
        s.strategy_template,
        (m.total_return * 100).toFixed(2),
        (m.cagr * 100).toFixed(2),
        m.sharpe.toFixed(3),
        (Math.abs(m.max_drawdown) * 100).toFixed(2),
        (m.volatility * 100).toFixed(2),
        m.num_trades,
        (m.win_rate * 100).toFixed(2),
      ];
    });

    const benchmarkRows = benchmark
      ? [[
          "BUY_AND_HOLD",
          "benchmark",
          (benchmark.metrics.total_return * 100).toFixed(2),
          (benchmark.metrics.cagr * 100).toFixed(2),
          benchmark.metrics.sharpe.toFixed(3),
          (Math.abs(benchmark.metrics.max_drawdown) * 100).toFixed(2),
          (benchmark.metrics.volatility * 100).toFixed(2),
          1,
          (benchmark.metrics.win_rate * 100).toFixed(2),
        ]]
      : [];

    const csv = [headers, ...benchmarkRows, ...strategyRows]
      .map((row) => row.map((v) => `"${v}"`).join(","))
      .join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.replace(/\s+/g, "_")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        <button
          onClick={handleExportCSV}
          className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 font-medium px-3 py-1.5 rounded-lg transition-colors border border-gray-700"
        >
          ↓ Export CSV
        </button>
      </div>
      <div className="overflow-x-auto rounded-xl border border-gray-800">
        <table className="w-full text-sm">
          <thead className="bg-gray-800 text-gray-400">
            <tr>
              <th className="px-3 py-3 text-left text-xs uppercase tracking-wide">Indicator</th>
              <th className="px-3 py-3 text-left text-xs uppercase tracking-wide">Strategy</th>
              <TH label="Total Return" />
              <TH label="CAGR" />
              <TH label="Sharpe" />
              <TH label="Max DD" />
              <TH label="Volatility" />
              <TH label="Trades" />
              <TH label="Win Rate" />
              {hasCharts && <th className="px-3 py-3 text-center text-xs uppercase tracking-wide">Chart</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {benchmark && <BenchmarkRow bh={benchmark} hasCharts={hasCharts} />}
            {sorted.map(({ s, originalIndex }) => {
              const m = s.metrics;
              const chart = charts[originalIndex];
              const hasChart = chart && "figure" in chart;
              return (
                <tr key={originalIndex} className="hover:bg-gray-800/50 transition-colors">
                  <td className="px-3 py-2 font-medium text-white">
                    {s.indicator_name.toUpperCase()}
                  </td>
                  <td className="px-3 py-2 text-gray-400 text-xs">
                    {s.strategy_template}
                  </td>
                  <MetricCell value={pct(m.total_return)} good={m.total_return > 0} />
                  <MetricCell value={pct(m.cagr)} good={m.cagr > 0} />
                  <MetricCell value={num(m.sharpe)} good={m.sharpe > 0.5} />
                  <MetricCell value={pct(Math.abs(m.max_drawdown))} good={Math.abs(m.max_drawdown) < 0.2} />
                  <MetricCell value={pct(m.volatility)} good={null} />
                  <td className="px-3 py-2 text-right text-gray-300">{m.num_trades}</td>
                  <MetricCell value={pct(m.win_rate)} good={m.win_rate > 0.5} />
                  {hasCharts && (
                    <td className="px-3 py-2 text-center">
                      {hasChart ? (
                        <button
                          onClick={() => onViewGraph?.(chart as PlotlyChart)}
                          className="text-xs bg-blue-900 hover:bg-blue-700 text-blue-300 font-medium px-3 py-1 rounded-lg transition-colors"
                        >
                          View Graph
                        </button>
                      ) : (
                        <span className="text-gray-600 text-xs">—</span>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {skipped.length > 0 && (
        <p className="mt-2 text-xs text-gray-500">
          {skipped.length} indicator(s) skipped due to insufficient data or unsupported parameters.
        </p>
      )}
    </div>
  );
}
