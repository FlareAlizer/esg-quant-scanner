import React from 'react';
import { type AssetScore } from '../types';
import { ScoreCard } from './ScoreCard';
import { ParksRadarChart } from './ParksRadarChart';
import { ComponentBreakdown } from './ComponentBreakdown';
import { AIAssistant } from './AIAssistant';

interface CompanyDashboardProps {
  data: AssetScore;
  assistantEnabled: boolean;
}

export const CompanyDashboard: React.FC<CompanyDashboardProps> = ({ data, assistantEnabled }) => {
  const risk = data.risk_analysis;

  return (
    <div className="bg-neutral-800/50 p-4 sm:p-6 rounded-2xl shadow-lg border border-neutral-700">
      <header className="mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-center">
        <div>
          <h2 className="text-3xl font-bold text-white">{data.name} ({data.ticker})</h2>
          <p className="text-neutral-400">
            {data.sector ?? 'сектор не определён'} · {data.asset_type}
            {data.sector_band === 'Default' && ' · общая шкала нормировки'}
          </p>
        </div>
        <div className="mt-4 sm:mt-0 text-left sm:text-right">
          <p className="font-semibold text-neutral-200">{data.bucket}</p>
          <p className="text-sm text-neutral-400">
            покрытие метрик {Math.round(data.data_coverage * 100)}%
            {!data.llm_available && ' · без LLM'}
          </p>
        </div>
      </header>

      {!data.reliable && (
        <p className="mb-6 p-3 text-sm text-yellow-300 bg-yellow-900/30 border border-yellow-700/50 rounded-lg">
          Оценено меньше трёх компонентов из пяти. Число ниже считать ориентиром, а не оценкой.
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 flex flex-col items-center justify-center space-y-6 bg-neutral-900/40 p-6 rounded-xl">
          <ScoreCard score={data.total_score} />
          <ParksRadarChart components={data.components} />
        </div>

        <div className="lg:col-span-2 space-y-6">
          <ComponentBreakdown components={data.components} />
          {risk.controversy_risk_score !== null && (
            <div className="bg-neutral-900/40 p-6 rounded-xl">
              <h3 className="text-xl font-bold mb-2">
                Репутационный риск: {risk.controversy_risk_score.toFixed(1)}/10
              </h3>
              <p className="text-neutral-300">{risk.reasoning}</p>
            </div>
          )}
          {assistantEnabled && <AIAssistant ticker={data.ticker} />}
        </div>
      </div>
    </div>
  );
};
