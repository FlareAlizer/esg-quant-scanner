
export interface NewsItem {
  title: string;
  source: string;
  date: string;
  url: string;
}

export interface ScoreDetail {
  score: number;
  explanation: string;
  kpis: {
    name: string;
    score: number;
    details: string;
  }[];
}

export interface CompanyESGData {
  name: string;
  ticker: string;
  industry: string;
  country: string;
  totalScore: number;
  riskScore: 'Low' | 'Medium' | 'High';
  confidenceLevel: 'Low' | 'Medium' | 'High';
  summary: string;
  e: ScoreDetail;
  s: ScoreDetail;
  g: ScoreDetail;
  news: NewsItem[];
}
