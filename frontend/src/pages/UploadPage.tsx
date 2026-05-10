import { useState, useRef, FormEvent } from "react";
import axios from "axios";
import { apiClient } from "../api";
import { AnalysisResponse } from "../types";

interface Props {
  onResult: (r: AnalysisResponse) => void;
  onHistory: () => void;
}

export default function UploadPage({ onResult, onHistory }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [symbol, setSymbol] = useState("");
  const [timeframe, setTimeframe] = useState<"weekly" | "monthly">("monthly");
  const [rfr, setRfr] = useState("0.03");
  const [model, setModel] = useState("nvidia/nemotron-3-super-120b-a12b:free");
  const [commission, setCommission] = useState("0.001");
  const [slippage, setSlippage] = useState("0.0005");
  const [walkForward, setWalkForward] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return setError("Please select a CSV file.");
    if (!symbol.trim()) return setError("Please enter a stock symbol.");

    setError(null);
    setLoading(true);

    const form = new FormData();
    form.append("file", file);
    form.append("stock_symbol", symbol.trim().toUpperCase());
    form.append("timeframe", timeframe);
    form.append("risk_free_rate_annual", rfr);
    form.append("model", model.trim());
    form.append("commission", commission);
    form.append("slippage", slippage);
    form.append("walk_forward", String(walkForward));

    try {
      const res = await apiClient.post<AnalysisResponse>("/api/analyze", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      onResult(res.data);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail ?? err.message;
        setError(typeof detail === "string" ? detail : JSON.stringify(detail));
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="flex justify-end mb-2">
            <button
              type="button"
              onClick={onHistory}
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors flex items-center gap-1"
            >
              <span>🕐</span> History
            </button>
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">
            LLM Backtesting Bot
          </h1>
          <p className="mt-2 text-gray-400 text-sm">
            Upload weekly or monthly OHLCV data and let an LLM select &amp;
            analyze technical indicator strategies.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-gray-900 rounded-2xl border border-gray-800 p-8 space-y-6 shadow-xl"
        >
          {/* File upload */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              CSV File
            </label>
            <div
              className="border-2 border-dashed border-gray-700 rounded-lg p-6 text-center cursor-pointer hover:border-blue-500 transition-colors"
              onClick={() => fileRef.current?.click()}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              {file ? (
                <p className="text-blue-400 font-medium">{file.name}</p>
              ) : (
                <>
                  <p className="text-gray-400 text-sm">
                    Click to select a CSV file
                  </p>
                  <p className="text-gray-600 text-xs mt-1">
                    Required columns: time, open, high, low, close, volume
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Stock symbol */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Stock Symbol
            </label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="e.g. AAPL"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {/* Timeframe */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Timeframe
            </label>
            <select
              value={timeframe}
              onChange={(e) =>
                setTimeframe(e.target.value as "weekly" | "monthly")
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="monthly">Monthly</option>
              <option value="weekly">Weekly</option>
            </select>
          </div>

          {/* Risk-free rate */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Annual Risk-Free Rate
            </label>
            <div className="relative">
              <input
                type="number"
                value={rfr}
                onChange={(e) => setRfr(e.target.value)}
                step="0.001"
                min="0"
                max="1"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                (e.g. 0.03 = 3%)
              </span>
            </div>
          </div>

          {/* Model */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              OpenRouter Model
            </label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="e.g. anthropic/claude-3.5-sonnet"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
            />
            <p className="mt-1 text-xs text-gray-500">
              Any model available on OpenRouter (e.g. openai/gpt-4o, google/gemini-pro)
            </p>
          </div>

          {/* Advanced Settings */}
          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              <span className={`transition-transform ${showAdvanced ? "rotate-90" : ""}`}>▶</span>
              Advanced Settings
            </button>
            {showAdvanced && (
              <div className="mt-3 space-y-4 bg-gray-800/40 border border-gray-700 rounded-lg p-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">
                      Commission Rate
                    </label>
                    <input
                      type="number"
                      value={commission}
                      onChange={(e) => setCommission(e.target.value)}
                      step="0.0001"
                      min="0"
                      max="0.05"
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <p className="mt-0.5 text-xs text-gray-600">e.g. 0.001 = 0.1%</p>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">
                      Slippage Rate
                    </label>
                    <input
                      type="number"
                      value={slippage}
                      onChange={(e) => setSlippage(e.target.value)}
                      step="0.0001"
                      min="0"
                      max="0.05"
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <p className="mt-0.5 text-xs text-gray-600">e.g. 0.0005 = 0.05%</p>
                  </div>
                </div>
                <label className="flex items-start gap-3 cursor-pointer select-none">
                  <div className="relative mt-0.5">
                    <input
                      type="checkbox"
                      checked={walkForward}
                      onChange={(e) => setWalkForward(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-gray-700 peer-checked:bg-blue-600 rounded-full transition-colors" />
                    <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-300">Walk-Forward Validation</p>
                    <p className="text-xs text-gray-600 mt-0.5">
                      Splits data 70/30. LLM selects on the in-sample period; top strategies are
                      re-run on the held-out period to test out-of-sample generalisability.
                    </p>
                  </div>
                </label>
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="bg-red-950 border border-red-800 rounded-lg px-4 py-3 text-red-400 text-sm">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-semibold rounded-lg py-3 transition-colors"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg
                  className="animate-spin h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8v8H4z"
                  />
                </svg>
                Running analysis (this may take 1–3 minutes)…
              </span>
            ) : (
              "Run Analysis"
            )}
          </button>
        </form>

        <p className="mt-4 text-center text-gray-600 text-xs">
          The LLM will select 10–15 indicator configurations, run backtests, and
          propose improvements.
        </p>
      </div>
    </div>
  );
}
