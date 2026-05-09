import { SelectionRationale, FundamentalContext } from "../types";

interface Props {
  rationales: SelectionRationale[];
  fundamentals: FundamentalContext | null;
}

function pct(v: number | undefined) {
  if (v === undefined || v === null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function money(v: number | undefined) {
  if (v === undefined || v === null) return "—";
  return `$${v.toFixed(1)}B`;
}

function FundamentalRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-gray-800 last:border-0">
      <span className="text-gray-400 text-sm">{label}</span>
      <span className="text-white text-sm font-medium">{value}</span>
    </div>
  );
}

export default function SelectionCard({ rationales, fundamentals }: Props) {
  if (rationales.length === 0) return null;

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-white">LLM Indicator Selection Rationale</h2>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Fundamental context panel */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 lg:col-span-1">
          <h3 className="text-sm font-semibold text-blue-400 uppercase tracking-wide mb-3">
            Roic.ai Fundamental Data
          </h3>
          {fundamentals ? (
            <div>
              {fundamentals.sector && (
                <div className="mb-3">
                  <p className="text-white font-medium">{fundamentals.sector}</p>
                  {fundamentals.industry && (
                    <p className="text-gray-500 text-xs">{fundamentals.industry}</p>
                  )}
                </div>
              )}
              <FundamentalRow label="Market Cap" value={money(fundamentals.market_cap_bn)} />
              <FundamentalRow label="Avg ROIC" value={pct(fundamentals.roic_avg)} />
              <FundamentalRow label="Gross Margin" value={pct(fundamentals.gross_margin_avg)} />
              <FundamentalRow label="Net Margin" value={pct(fundamentals.net_margin_avg)} />
              <FundamentalRow label="EBITDA Margin" value={pct(fundamentals.ebitda_margin_avg)} />
              <FundamentalRow label="ROA" value={pct(fundamentals.roa_avg)} />
              <FundamentalRow label="Revenue CAGR (3yr)" value={pct(fundamentals.revenue_cagr_3yr)} />
              <p className="text-xs text-gray-600 mt-3">
                This data was sent to the LLM to inform indicator selection. High ROIC + strong growth
                favours trend/momentum strategies; low margins + cyclical profiles favour mean-reversion.
              </p>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">
              No fundamental data available. The LLM selected indicators based on price data alone.
              Add a <span className="font-mono text-gray-400">ROIC_API_KEY</span> to enable this.
            </p>
          )}
        </div>

        {/* Rationale list */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 lg:col-span-2">
          <h3 className="text-sm font-semibold text-blue-400 uppercase tracking-wide mb-3">
            Why Each Indicator Was Selected
          </h3>
          <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
            {rationales.map((r, i) => (
              <div key={i} className="border border-gray-800 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className="text-white font-medium text-sm">
                    {r.indicator_name.toUpperCase()}
                  </span>
                  <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
                    {r.strategy_template}
                  </span>
                  {Object.keys(r.params).length > 0 && (
                    <span className="text-xs text-gray-600">
                      {Object.entries(r.params)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(", ")}
                    </span>
                  )}
                </div>
                <p className="text-gray-300 text-sm leading-relaxed">{r.rationale}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
