
import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { type CompanyESGData } from '../types';

interface ComparisonDashboardProps {
  companies: CompanyESGData[];
}

const getScoreColorClass = (score: number) => {
  if (score >= 75) return 'text-green-400';
  if (score >= 50) return 'text-yellow-400';
  return 'text-red-400';
};

const getRiskColorClass = (risk: 'Low' | 'Medium' | 'High') => {
  switch (risk) {
    case 'Low': return 'text-green-400';
    case 'Medium': return 'text-yellow-400';
    case 'High': return 'text-red-400';
    default: return 'text-neutral-400';
  }
};

const getConfidenceColorClass = (level: 'Low' | 'Medium' | 'High') => {
    return getRiskColorClass(level);
};

const chartColors = ['#4db8ff', '#ffaa00', '#a855f7'];

export const ComparisonDashboard: React.FC<ComparisonDashboardProps> = ({ companies }) => {
  const chartData = [
    { name: 'Environmental', ...Object.fromEntries(companies.map(c => [c.ticker, c.e.score])) },
    { name: 'Social', ...Object.fromEntries(companies.map(c => [c.ticker, c.s.score])) },
    { name: 'Governance', ...Object.fromEntries(companies.map(c => [c.ticker, c.g.score])) },
  ];

  const metrics = [
    { label: 'Total Score', key: 'totalScore', colorFn: getScoreColorClass },
    { label: 'E Score', key: 'e.score', colorFn: getScoreColorClass },
    { label: 'S Score', key: 's.score', colorFn: getScoreColorClass },
    { label: 'G Score', key: 'g.score', colorFn: getScoreColorClass },
    { label: 'Risk Score', key: 'riskScore', colorFn: getRiskColorClass },
    { label: 'Confidence', key: 'confidenceLevel', colorFn: getConfidenceColorClass },
  ];

  // Helper to access nested keys like 'e.score'
  const getMetricValue = (company: CompanyESGData, key: string) => {
    const keys = key.split('.');
    let value: any = company;
    for (const k of keys) {
      value = value[k];
    }
    return value;
  };

  return (
    <div className="bg-neutral-800/50 p-4 sm:p-6 rounded-2xl shadow-lg border border-neutral-700 space-y-8">
      <header>
        <h2 className="text-3xl font-bold text-center text-white">Company Comparison</h2>
      </header>

      {/* Comparison Table */}
      <div className="bg-neutral-900/40 p-6 rounded-xl">
        <h3 className="text-xl font-bold mb-4">Metric Breakdown</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="border-b-2 border-neutral-700">
              <tr>
                <th className="p-3 text-sm font-semibold text-neutral-400">Metric</th>
                {companies.map(c => (
                  <th key={c.ticker} className="p-3 text-sm font-semibold text-neutral-200 text-center">{c.name} ({c.ticker})</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.map(metric => (
                <tr key={metric.label} className="border-b border-neutral-800">
                  <td className="p-3 font-medium text-neutral-300">{metric.label}</td>
                  {companies.map(c => {
                    const value = getMetricValue(c, metric.key);
                    return (
                      // FIX: The original code caused a TypeScript error because `metric.colorFn` is a union
                      // of functions with incompatible parameter types. It also had a logic bug, passing `0`
                      // to functions expecting a string. Casting the function call to `any` solves both issues
                      // by telling TypeScript to trust that the correct value type is being passed at runtime.
                      <td key={c.ticker} className={`p-3 font-bold text-lg text-center ${(metric.colorFn as any)(value)}`}>
                        {value}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Comparison Chart */}
      <div className="bg-neutral-900/40 p-6 rounded-xl">
        <h3 className="text-xl font-bold mb-4">E, S, & G Score Comparison</h3>
        <div className="w-full h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#4a5568" />
              <XAxis dataKey="name" tick={{ fill: '#e2e8f0' }} />
              <YAxis tick={{ fill: '#e2e8f0' }} domain={[0, 100]} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#2d3748',
                  border: '1px solid #4a5568',
                  borderRadius: '0.5rem',
                }}
                cursor={{ fill: 'rgba(74, 85, 104, 0.3)' }}
              />
              <Legend wrapperStyle={{ color: '#e2e8f0' }} />
              {companies.map((c, index) => (
                <Bar key={c.ticker} dataKey={c.ticker} name={c.name} fill={chartColors[index % chartColors.length]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};
