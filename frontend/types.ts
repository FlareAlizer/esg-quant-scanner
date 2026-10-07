/** Mirrors the dict returned by backend/company_scorer.score_company. */

export const COMPONENT_CODES = ['P', 'A', 'R', 'K', 'S'] as const;
export type ComponentCode = (typeof COMPONENT_CODES)[number];

export interface ScoreComponent {
  name: string;
  /** 0-10, or null when there was no data to score the component on. */
  score: number | null;
  coverage: string;
  details: string;
  reasoning?: string;
}

export interface AssetScore {
  ticker: string;
  name: string;
  /** Sector as reported by the data source; null when unknown. */
  sector: string | null;
  /** Which set of normalisation bands was used; "Default" is the generic one. */
  sector_band: string;
  asset_type: string;
  components: Record<ComponentCode, ScoreComponent>;
  total_score: number | null;
  /** False when fewer than three components could be scored. */
  reliable: boolean;
  bucket: string;
  /** Share of the six quantitative metrics that had data, 0-1. */
  data_coverage: number;
  llm_available: boolean;
  risk_analysis: {
    controversy_risk_score: number | null;
    reasoning: string;
  };
}
