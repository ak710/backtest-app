import { TopStrategy, SuggestedModification } from "../types";

interface Props {
  summary: string;
  topStrategies: TopStrategy[];
  modifications: SuggestedModification[];
  warnings: string[];
}

export default function LLMInsights({
  summary,
  topStrategies,
  modifications,
  warnings,
}: Props) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-white">LLM Analysis</h2>

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="bg-yellow-950 border border-yellow-800 rounded-xl p-4 space-y-1">
          {warnings.map((w, i) => (
            <p key={i} className="text-yellow-300 text-sm">
              ⚠ {w}
            </p>
          ))}
        </div>
      )}

      {/* Summary */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
          Summary Insights
        </h3>
        <p className="text-gray-200 text-sm leading-relaxed whitespace-pre-wrap">
          {summary}
        </p>
      </div>

      {/* Top strategies */}
      {topStrategies.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
            Top Strategies by Robustness
          </h3>
          <div className="space-y-3">
            {topStrategies.map((s, i) => (
              <div key={i} className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-blue-900 text-blue-300 rounded-full text-xs flex items-center justify-center font-bold">
                  {i + 1}
                </span>
                <div>
                  <p className="text-white text-sm font-medium">
                    {s.indicator_name.toUpperCase()} – {s.strategy_template}
                  </p>
                  <p className="text-gray-400 text-xs mt-0.5">{s.reason}</p>
                  <p className="text-gray-600 text-xs mt-0.5">
                    Params:{" "}
                    {Object.entries(s.params)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Suggested modifications */}
      {modifications.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
            Suggested Modifications
          </h3>
          <div className="space-y-4">
            {modifications.map((m, i) => (
              <div
                key={i}
                className="border border-gray-700 rounded-lg p-4 space-y-1"
              >
                <p className="text-white text-sm font-medium">
                  {m.base_indicator_name.toUpperCase()} –{" "}
                  {m.base_strategy_template}
                </p>
                {m.new_combo_components && m.new_combo_components.length > 0 ? (
                  <div className="text-gray-300 text-xs space-y-0.5">
                    <span className="text-gray-400">Components ({m.new_combo_logic ?? "MAJORITY"}):</span>
                    {m.new_combo_components.map((c, ci) => (
                      <div key={ci} className="ml-2">
                        <span className="text-gray-200">{c.indicator_name}</span>
                        {Object.keys(c.params).length > 0 && (
                          <span className="text-gray-400">
                            {" "}({Object.entries(c.params).map(([k, v]) => `${k}=${v}`).join(", ")})
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-300 text-xs">
                    New params:{" "}
                    {Object.entries(m.new_params)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")}
                  </p>
                )}
                {Object.keys(m.risk_controls).length > 0 && (
                  <p className="text-gray-300 text-xs">
                    Risk controls:{" "}
                    {Object.entries(m.risk_controls)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")}
                  </p>
                )}
                <p className="text-emerald-400 text-xs mt-1">
                  Expected: {m.expected_effect}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
