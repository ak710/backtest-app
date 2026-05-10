import { useEffect, useState } from "react";
import { listRuns, loadRun, deleteRun } from "../api";
import { RunSummary, AnalysisResponse } from "../types";

interface Props {
  onBack: () => void;
  onLoadRun: (result: AnalysisResponse) => void;
}

const pct = (v: number | null) =>
  v == null ? "—" : `${(v * 100).toFixed(1)}%`;

const num = (v: number | null) =>
  v == null ? "—" : v.toFixed(2);

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric",
  }) + " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export default function HistoryPage({ onBack, onLoadRun }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [fetching, setFetching] = useState(true);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch(() => setError("Failed to load history."))
      .finally(() => setFetching(false));
  }, []);

  const handleLoad = async (id: string) => {
    setLoadingId(id);
    setError(null);
    try {
      const result = await loadRun(id);
      onLoadRun(result);
    } catch {
      setError("Failed to load run. It may be corrupted.");
      setLoadingId(null);
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await deleteRun(id);
      setRuns((prev) => prev.filter((r) => r.id !== id));
    } catch {
      setError("Failed to delete run.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">Run History</h1>
          <p className="text-gray-500 text-sm mt-1">
            {runs.length} saved run{runs.length !== 1 ? "s" : ""} · charts are regenerated on load
          </p>
        </div>
        <button
          onClick={onBack}
          className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-medium rounded-lg px-4 py-2 transition-colors"
        >
          ← New Analysis
        </button>
      </div>

      {error && (
        <div className="mb-6 bg-red-950 border border-red-800 rounded-lg px-4 py-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      {fetching ? (
        <div className="flex justify-center py-20">
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : runs.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-gray-500 text-lg">No runs saved yet.</p>
          <p className="text-gray-600 text-sm mt-2">
            Complete an analysis and it will appear here automatically.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => (
            <div
              key={run.id}
              className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex items-center gap-6"
            >
              {/* Symbol + meta */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-lg font-bold text-white">{run.stock_symbol}</span>
                  <span className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded capitalize">
                    {run.timeframe}
                  </span>
                  {run.walk_forward_enabled && (
                    <span className="text-xs bg-blue-900/60 text-blue-400 px-2 py-0.5 rounded">
                      Walk-Forward
                    </span>
                  )}
                  {run.data_quality.length > 0 && (
                    <span className="text-xs bg-yellow-900/50 text-yellow-500 px-2 py-0.5 rounded" title={run.data_quality.join(" | ")}>
                      ⚠ Data issues
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-1">{formatDate(run.created_at)}</p>
                <p className="text-xs text-gray-600 mt-0.5 font-mono truncate">{run.model_used}</p>
              </div>

              {/* Metrics */}
              <div className="hidden sm:grid grid-cols-3 gap-6 text-center shrink-0">
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Sharpe</p>
                  <p className="text-white font-semibold mt-0.5">{num(run.best_sharpe)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">CAGR</p>
                  <p className="text-emerald-400 font-semibold mt-0.5">{pct(run.best_cagr)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">B&amp;H</p>
                  <p className="text-gray-300 font-semibold mt-0.5">{pct(run.benchmark_cagr)}</p>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={() => handleLoad(run.id)}
                  disabled={loadingId === run.id}
                  className="bg-blue-700 hover:bg-blue-600 disabled:bg-gray-700 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
                >
                  {loadingId === run.id ? (
                    <>
                      <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Loading…
                    </>
                  ) : "Load"}
                </button>
                <button
                  onClick={() => handleDelete(run.id)}
                  disabled={deletingId === run.id}
                  className="text-gray-600 hover:text-red-400 disabled:opacity-40 text-sm px-2 py-2 rounded-lg transition-colors"
                  title="Delete run"
                >
                  {deletingId === run.id ? "…" : "✕"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
