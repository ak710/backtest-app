import { useState } from "react";
import UploadPage from "./pages/UploadPage";
import ResultsPage from "./pages/ResultsPage";
import { AnalysisResponse } from "./types";

export default function App() {
  const [result, setResult] = useState<AnalysisResponse | null>(null);

  return (
    <div className="min-h-screen bg-gray-950">
      {result ? (
        <ResultsPage result={result} onReset={() => setResult(null)} />
      ) : (
        <UploadPage onResult={setResult} />
      )}
    </div>
  );
}
