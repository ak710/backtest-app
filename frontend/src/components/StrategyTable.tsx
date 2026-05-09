import { StrategyResult } from "../types";

interface Props {
  strategies: StrategyResult[];
  title: string;
}

const pct = (v: number) => `${(v * 100).toFixed(2)}%`;
const num = (v: number, d = 3) => v.toFixed(d);

function MetricCell({ value, good }: { value: string; good: boolean | null }) {
  const color =
    good === null
      ? "text-gray-300"
      : good
      ? "text-emerald-400"
      : "text-red-400";
  return <td className={`px-3 py-2 text-right text-sm ${color}`}>{value}</td>;
}

export default function StrategyTable({ strategies, title }: Props) {
  const valid = strategies.filter((s) => !s.skipped);
  const skipped = strategies.filter((s) => s.skipped);

  if (valid.length === 0 && skipped.length === 0) return null;

  const sorted = [...valid].sort(
    (a, b) => (b.metrics?.sharpe ?? 0) - (a.metrics?.sharpe ?? 0)
  );

  return (
    <div>
      <h2 className="text-lg font-semibold text-white mb-3">{title}</h2>
      <div className="overflow-x-auto rounded-xl border border-gray-800">
        <table className="w-full text-sm">
          <thead className="bg-gray-800 text-gray-400 text-xs uppercase tracking-wide">
            <tr>
              <th className="px-3 py-3 text-left">Indicator</th>
              <th className="px-3 py-3 text-left">Strategy</th>
              <th className="px-3 py-3 text-right">Total Return</th>
              <th className="px-3 py-3 text-right">CAGR</th>
              <th className="px-3 py-3 text-right">Sharpe</th>
              <th className="px-3 py-3 text-right">Max DD</th>
              <th className="px-3 py-3 text-right">Volatility</th>
              <th className="px-3 py-3 text-right">Trades</th>
              <th className="px-3 py-3 text-right">Win Rate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {sorted.map((s, i) => {
              const m = s.metrics;
              return (
                <tr
                  key={i}
                  className="hover:bg-gray-800/50 transition-colors"
                >
                  <td className="px-3 py-2 font-medium text-white">
                    {s.indicator_name.toUpperCase()}
                  </td>
                  <td className="px-3 py-2 text-gray-400 text-xs">
                    {s.strategy_template}
                  </td>
                  <MetricCell
                    value={pct(m.total_return)}
                    good={m.total_return > 0}
                  />
                  <MetricCell value={pct(m.cagr)} good={m.cagr > 0} />
                  <MetricCell
                    value={num(m.sharpe)}
                    good={m.sharpe > 0.5}
                  />
                  <MetricCell
                    value={pct(Math.abs(m.max_drawdown))}
                    good={Math.abs(m.max_drawdown) < 0.2}
                  />
                  <MetricCell
                    value={pct(m.volatility)}
                    good={null}
                  />
                  <td className="px-3 py-2 text-right text-gray-300">
                    {m.num_trades}
                  </td>
                  <MetricCell
                    value={pct(m.win_rate)}
                    good={m.win_rate > 0.5}
                  />
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {skipped.length > 0 && (
        <p className="mt-2 text-xs text-gray-500">
          {skipped.length} indicator(s) skipped due to insufficient data or
          unsupported parameters.
        </p>
      )}
    </div>
  );
}
