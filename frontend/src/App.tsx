import { useState } from "react";
import UploadPage from "./pages/UploadPage";
import ResultsPage from "./pages/ResultsPage";
import HistoryPage from "./pages/HistoryPage";
import { AnalysisResponse } from "./types";

type View = "upload" | "history" | "results";

export default function App() {
  const [view, setView] = useState<View>("upload");
  const [result, setResult] = useState<AnalysisResponse | null>(null);

  const showResult = (r: AnalysisResponse) => {
    setResult(r);
    setView("results");
  };

  return (
    <div className="min-h-screen bg-gray-950">
      {view === "results" && result ? (
        <ResultsPage
          result={result}
          onReset={() => { setResult(null); setView("upload"); }}
          onHistory={() => setView("history")}
        />
      ) : view === "history" ? (
        <HistoryPage
          onBack={() => setView("upload")}
          onLoadRun={showResult}
        />
      ) : (
        <UploadPage
          onResult={showResult}
          onHistory={() => setView("history")}
        />
      )}
    </div>
  );
}
