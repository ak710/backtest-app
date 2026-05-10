import { useState } from "react";
import UploadPage from "./pages/UploadPage";
import ResultsPage from "./pages/ResultsPage";
import HistoryPage from "./pages/HistoryPage";
import ReversalPage from "./pages/ReversalPage";
import { AnalysisResponse } from "./types";

type View = "upload" | "history" | "results" | "predictor";

const NAV_TABS: { id: View; label: string }[] = [
  { id: "upload", label: "Backtester" },
  { id: "predictor", label: "Predictor" },
  { id: "history", label: "History" },
];

export default function App() {
  const [view, setView] = useState<View>("upload");
  const [result, setResult] = useState<AnalysisResponse | null>(null);

  const showResult = (r: AnalysisResponse) => {
    setResult(r);
    setView("results");
  };

  if (view === "results" && result) {
    return (
      <div className="min-h-screen bg-gray-950">
        <ResultsPage
          result={result}
          onReset={() => { setResult(null); setView("upload"); }}
          onHistory={() => setView("history")}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Global nav bar */}
      <div className="border-b border-gray-800 bg-gray-900 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 flex items-center gap-1 h-12">
          {NAV_TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setView(tab.id)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                view === tab.id
                  ? "bg-gray-800 text-white"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {view === "predictor" ? (
        <ReversalPage />
      ) : view === "history" ? (
        <HistoryPage onBack={() => setView("upload")} onLoadRun={showResult} />
      ) : (
        <UploadPage onResult={showResult} onHistory={() => setView("history")} />
      )}
    </div>
  );
}
