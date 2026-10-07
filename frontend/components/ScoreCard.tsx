import React from 'react';

/** Same thresholds as assign_bucket in backend/company_scorer.py. */
export const scoreColor = (score: number | null) => {
  if (score === null) return 'text-neutral-400';
  if (score >= 7) return 'text-green-400';
  if (score >= 5.5) return 'text-yellow-400';
  return 'text-red-400';
};

export const formatScore = (score: number | null) => (score === null ? 'н/д' : score.toFixed(1));

export const ScoreCard: React.FC<{ score: number | null }> = ({ score }) => (
  <div className="flex flex-col items-center">
    <p className="text-neutral-400 mb-2 font-semibold">PARKS, 0–10</p>
    <div className={`w-36 h-36 rounded-full border-4 border-current flex items-center justify-center bg-neutral-800/50 ${scoreColor(score)}`}>
      <span className="text-5xl font-bold">{formatScore(score)}</span>
    </div>
  </div>
);
