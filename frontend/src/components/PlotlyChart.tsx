import { lazy, Suspense } from "react";
import type { Layout, Data } from "plotly.js";
import { PlotlyChart as PlotlyChartType } from "../types";

// Dynamic import to avoid bundling all of plotly.js eagerly
const Plot = lazy(() => import("react-plotly.js"));

interface Props {
  chart: PlotlyChartType;
}

export default function PlotlyChart({ chart }: Props) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">{chart.title}</h3>
      <Suspense
        fallback={
          <div className="h-64 flex items-center justify-center text-gray-500 text-sm">
            Loading chart…
          </div>
        }
      >
        <Plot
          data={chart.figure.data as Data[]}
          layout={{
            ...chart.figure.layout,
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            font: { color: "#e5e7eb" },
          } as Partial<Layout>}
          config={{ responsive: true, displayModeBar: true }}
          style={{ width: "100%", minHeight: "400px" }}
          useResizeHandler
        />
      </Suspense>
    </div>
  );
}
