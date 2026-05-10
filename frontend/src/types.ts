export interface RunSummary {
  id: string;
  created_at: string;
  stock_symbol: string;
  timeframe: string;
  model_used: string;
  walk_forward_enabled: boolean;
  best_sharpe: number | null;
  best_cagr: number | null;
  benchmark_cagr: number | null;
  num_strategies: number;
  data_quality: string[];
}

export interface Trade {
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  pnl_pct: number;
  num_bars: number;
}

export interface Metrics {
  total_return: number;
  cagr: number;
  sharpe: number;
  volatility: number;
  max_drawdown: number;
  max_drawdown_duration: number;
  num_trades: number;
  win_rate: number;
  avg_trade_pnl: number;
  profit_factor: number;
}

export interface StrategyResult {
  indicator_name: string;
  strategy_template: string;
  params: Record<string, unknown>;
  skipped: boolean;
  skip_reason: string;
  metrics: Metrics;
  trades: Trade[];
}

export interface TopStrategy {
  indicator_name: string;
  strategy_template: string;
  params: Record<string, unknown>;
  reason: string;
}

export interface SuggestedModification {
  base_indicator_name: string;
  base_strategy_template: string;
  new_params: Record<string, unknown>;
  risk_controls: Record<string, unknown>;
  expected_effect: string;
}

export interface PlotlyChart {
  id: string;
  title: string;
  figure: {
    data: unknown[];
    layout: Record<string, unknown>;
  };
}

export interface SelectionRationale {
  indicator_name: string;
  strategy_template: string;
  params: Record<string, unknown>;
  rationale: string;
}

export interface FundamentalContext {
  company_name?: string;
  sector?: string;
  industry?: string;
  market_cap_bn?: number;
  roic_avg?: number;
  gross_margin_avg?: number;
  net_margin_avg?: number;
  ebitda_margin_avg?: number;
  roa_avg?: number;
  revenue_cagr_3yr?: number;
}

export interface AnalysisResponse {
  stock_symbol: string;
  timeframe: string;
  model_used: string;
  base_strategies: StrategyResult[];
  modified_strategies: StrategyResult[];
  llm_summary: string;
  llm_top_strategies: TopStrategy[];
  llm_suggested_modifications: SuggestedModification[];
  llm_warnings: string[];
  charts: PlotlyChart[];
  strategy_charts: (PlotlyChart | Record<string, never>)[];
  modified_strategy_charts: (PlotlyChart | Record<string, never>)[];
  selection_rationales: SelectionRationale[];
  fundamental_context: FundamentalContext | null;
  benchmark: StrategyResult | null;
  data_quality: string[];
  oos_strategies: StrategyResult[];
  oos_strategy_charts: (PlotlyChart | Record<string, never>)[];
  walk_forward_enabled: boolean;
  walk_forward_split_date: string;
}
