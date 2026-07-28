
import React from 'react';

interface ScoreCardProps {
  score: number;
}

export const ScoreCard: React.FC<ScoreCardProps> = ({ score }) => {
  const getScoreColor = (s: number) => {
    if (s >= 75) return 'text-green-400 border-green-400/50';
    if (s >= 50) return 'text-yellow-400 border-yellow-400/50';
    return 'text-red-400 border-red-400/50';
  };

  return (
    <div className="flex flex-col items-center">
      <p className="text-neutral-400 mb-2 font-semibold">Total ESG Score</p>
      <div className={`w-36 h-36 rounded-full border-4 ${getScoreColor(score)} flex items-center justify-center bg-neutral-800/50`}>
        <span className={`text-5xl font-bold ${getScoreColor(score)}`}>{score}</span>
      </div>
    </div>
  );
};
