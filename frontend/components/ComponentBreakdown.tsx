import React from 'react';
import { COMPONENT_CODES, type AssetScore } from '../types';
import { formatScore, scoreColor } from './ScoreCard';

export const ComponentBreakdown: React.FC<{ components: AssetScore['components'] }> = ({ components }) => (
  <div className="space-y-2">
    <h3 className="text-xl font-bold mb-2 text-white">Компоненты</h3>
    {COMPONENT_CODES.map(code => {
      const part = components[code];
      return (
        <div key={code} className="p-4 border border-neutral-700 rounded-lg bg-neutral-900/40">
          <div className="flex justify-between items-baseline">
            <p className="font-bold text-neutral-200">
              <span className="text-brand-secondary mr-2">{code}</span>
              {part.name}
              <span className="ml-3 text-xs font-normal text-neutral-500">данные: {part.coverage}</span>
            </p>
            <span className={`text-lg font-bold ${scoreColor(part.score)}`}>{formatScore(part.score)}</span>
          </div>
          <p className="mt-1 text-sm text-neutral-400">{part.details}</p>
          {part.reasoning && <p className="mt-2 text-sm text-neutral-300 italic">{part.reasoning}</p>}
        </div>
      );
    })}
  </div>
);
