import { useState, useRef, FormEvent } from "react";
import axios from "axios";
import { apiClient } from "../api";
import { AnalysisResponse } from "../types";

interface Props {
  onResult: (r: AnalysisResponse) => void;
}

export default function UploadPage({ onResult }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [symbol, setSymbol] = useState("");
  const [timeframe, setTimeframe] = useState<"weekly" | "monthly">("monthly");
  const [rfr, setRfr] = useState("0.03");
  const [model, setModel] = useState("anthropic/claude-3.5-sonnet");
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
