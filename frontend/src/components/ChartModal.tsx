import { useEffect } from "react";
import PlotlyChart from "./PlotlyChart";
import { PlotlyChart as PlotlyChartType } from "../types";

interface Props {
  chart: PlotlyChartType;
  onClose: () => void;
}

export default function ChartModal({ chart, onClose }: Props) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-5xl bg-gray-900 rounded-2xl border border-gray-700 shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-white">{chart.title}</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors text-xl leading-none"
          >
            ×
          </button>
        </div>
        <div className="p-4">
          <PlotlyChart chart={chart} />
        </div>
      </div>
    </div>
  );
}
