import React from 'react';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { COMPONENT_CODES, type AssetScore } from '../types';
import { formatScore, scoreColor } from './ScoreCard';

const chartColors = ['#4db8ff', '#ffaa00', '#a855f7', '#34d399', '#f87171'];

export const ComparisonDashboard: React.FC<{ assets: AssetScore[] }> = ({ assets }) => {
  // One group of bars per component, one bar per asset. A component without
  // data has no bar rather than a zero-height one that reads as "worst".
  const chartData = COMPONENT_CODES.map(code => ({
    name: code,
    ...Object.fromEntries(assets.map(a => [a.ticker, a.components[code].score ?? undefined])),
  }));

  const rows: { label: string; value: (a: AssetScore) => number | null }[] = [
    { label: 'PARKS', value: a => a.total_score },
    ...COMPONENT_CODES.map(code => ({
      label: `${code} · ${assets[0].components[code].name}`,
      value: (a: AssetScore) => a.components[code].score,
    })),
  ];

  return (
    <div className="bg-neutral-800/50 p-4 sm:p-6 rounded-2xl shadow-lg border border-neutral-700 space-y-8">
      <div className="bg-neutral-900/40 p-6 rounded-xl overflow-x-auto">
        <table className="w-full text-left">
          <thead className="border-b-2 border-neutral-700">
            <tr>
              <th className="p-3 text-sm font-semibold text-neutral-400">Метрика</th>
              {assets.map(a => (
                <th key={a.ticker} className="p-3 text-sm font-semibold text-neutral-200 text-center">
                  {a.name} ({a.ticker})
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.label} className="border-b border-neutral-800">
                <td className="p-3 font-medium text-neutral-300">{row.label}</td>
                {assets.map(a => (
                  <td key={a.ticker} className={`p-3 font-bold text-lg text-center ${scoreColor(row.value(a))}`}>
                    {formatScore(row.value(a))}
                  </td>
                ))}
              </tr>
            ))}
            <tr>
              <td className="p-3 font-medium text-neutral-300">Покрытие метрик</td>
              {assets.map(a => (
                <td key={a.ticker} className="p-3 text-center text-neutral-300">
                  {Math.round(a.data_coverage * 100)}%{!a.reliable && ' · мало данных'}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="bg-neutral-900/40 p-6 rounded-xl">
        <div className="w-full h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#4a5568" />
              <XAxis dataKey="name" tick={{ fill: '#e2e8f0' }} />
              <YAxis tick={{ fill: '#e2e8f0' }} domain={[0, 10]} />
              <Tooltip
                contentStyle={{ backgroundColor: '#2d3748', border: '1px solid #4a5568', borderRadius: '0.5rem' }}
                cursor={{ fill: 'rgba(74, 85, 104, 0.3)' }}
              />
              <Legend wrapperStyle={{ color: '#e2e8f0' }} />
              {assets.map((a, index) => (
                <Bar key={a.ticker} dataKey={a.ticker} fill={chartColors[index % chartColors.length]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};
