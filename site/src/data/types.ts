export type FactorKey = "quality" | "growth" | "valuation" | "health";
export type SegmentKey = "operating" | "financials" | "pre_revenue";

export interface MetricSpec {
  key: string;
  label: string;
  short: string;
  factor: FactorKey;
  higher_better: boolean;
  unit: "pct" | "pp" | "x" | "score";
  formula: string;
}

export interface FactorSpec {
  key: FactorKey;
  label: string;
  short: string;
  /** Value contains price by construction, so its correlation with price is
   *  arithmetic rather than predictive. Surfaced wherever that matters. */
  price_dependent: boolean;
}

export interface MetricCell {
  raw: number | null;
  pct: number | null;
  basis: string | null;
}

export interface Stability {
  rank_min: number;
  rank_max: number;
  rank_median: number;
  weightings_tested: number;
  score: number;
}

/** How each figure was derived - which tag resolved, which fallback was taken.
 *  The period, filing date, accession and form live on the row itself. */
export interface Derivation {
  basis: string | null;
  ebit_source: string;
  debt_source: string;
  gross_profit_source: string;
  tax_rate_source: string;
  effective_tax_rate: number;
}

export interface StockRow {
  ticker: string;
  name: string;
  sector: string | null;
  industry: string | null;
  exchange: string;
  cik: string;
  market_cap: number | null;
  segment: SegmentKey;
  scoring_date: string;
  run_date: string;
  price: number;
  price_at_scoring_asof: string;
  prior_price: number | null;
  prior_price_date: string | null;
  price_change_pct: number | null;
  price_change_abs: number | null;
  composite: number | null;
  rank: number;
  sector_decile: number | null;
  sector_rank: number | null;
  factors: Record<FactorKey, number | null>;
  metrics: Record<string, MetricCell>;
  missing: string[];
  missing_reasons: Record<string, string>;
  coverage: number;
  stability: Stability | null;
  fundamentals_asof: string | null;
  filed: string | null;
  accn: string | null;
  form: string | null;
  derivation: Derivation;
  notes: string[];
  weights_version: string;
  is_new: boolean;
  composite_change: number | null;
  rank_change: number | null;
}

export interface InsufficientRow {
  ticker: string;
  name: string;
  sector: string | null;
  exchange: string;
  market_cap: number | null;
  segment: SegmentKey;
  coverage: number;
  reason: string;
  missing: string[];
  missing_reasons: Record<string, string>;
  price: number;
  price_change_pct: number | null;
}

export interface ScoresMeta {
  generated_at: string;
  scoring_date: string;
  prior_scoring_date: string;
  run_date: string;
  weights_version: string;
  weights: Record<FactorKey, number>;
  first_run: boolean;
  settings: {
    scoring: { roic_hurdle: number; winsorize_lo_pct: number; winsorize_hi_pct: number; stability_sweep: number[] };
    universe: Record<string, number | string[]>;
  };
  sources: Record<string, { name: string; licence: string }>;
  counts: Record<string, number>;
}

export interface SegmentMeta {
  key: SegmentKey;
  label: string;
  applicable_metrics: string[];
  metric_resolution: Record<string, number>;
  cohorts: Record<string, number>;
}

export interface ScoresPayload {
  meta: ScoresMeta;
  segments_meta: SegmentMeta[];
  metrics: MetricSpec[];
  factors: FactorSpec[];
  segments: Record<SegmentKey, StockRow[]>;
  insufficient: InsufficientRow[];
}

export interface HistoryPoint {
  month: string;
  composite: number | null;
  rank: number | null;
  price: number | null;
  /** Carried so the score-versus-price view can report per factor, not only
   *  on the composite. */
  factors: Record<FactorKey, number | null> | null;
  sector: string | null;
  weights_version: string;
  /** Backtested months are weaker evidence than live ones and are labelled
   *  distinctly wherever they are shown. */
  backtested: boolean;
}

export interface HistoryIndex {
  months: string[];
  observations: number;
  tickers: Record<string, HistoryPoint[]>;
}

export interface FunnelStage {
  stage: string;
  count: number;
}

export interface CoverageReport {
  generated_at: string;
  scoring_date: string;
  funnel: FunnelStage[];
  metric_resolution_by_segment: Record<SegmentKey, Record<string, number>>;
  applicable_metrics_by_segment: Record<SegmentKey, string[]>;
  excluded: { ticker: string; stage: string; reason: string }[];
  insufficient_data: InsufficientRow[];
  unresolved_metrics: { ticker: string; metric: string; reason: string }[];
  price_review: { ticker: string; change_pct: number; splits_in_window: unknown[]; note: string }[];
  price_failures: { ticker: string; reason: string }[];
  fundamentals_failures: { ticker: string; reason: string }[];
}
