import axios from "axios";
import { AnalysisResponse, ReversalPrediction, RunSummary } from "./types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 300_000,
});

export async function listRuns(): Promise<RunSummary[]> {
  const res = await apiClient.get<{ runs: RunSummary[] }>("/api/runs");
  return res.data.runs;
}

export async function loadRun(id: string): Promise<AnalysisResponse> {
  const res = await apiClient.get<AnalysisResponse>(`/api/runs/${id}`);
  return res.data;
}

export async function deleteRun(id: string): Promise<void> {
  await apiClient.delete(`/api/runs/${id}`);
}

export async function predictReversal(
  ticker: string,
  peerTickers?: string[],
  model?: string,
): Promise<ReversalPrediction> {
  const res = await apiClient.post<ReversalPrediction>("/api/predict", {
    ticker,
    peer_tickers: peerTickers && peerTickers.length > 0 ? peerTickers : undefined,
    model: model || undefined,
  }, { timeout: 900_000 }); // 15 min — thinking models can be slow
  return res.data;
}
