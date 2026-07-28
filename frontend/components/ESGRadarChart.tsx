
import React from 'react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer } from 'recharts';

interface ESGRadarChartProps {
  e: number;
  s: number;
  g: number;
}

export const ESGRadarChart: React.FC<ESGRadarChartProps> = ({ e, s, g }) => {
  const data = [
    { subject: 'E', score: e, fullMark: 100 },
    { subject: 'S', score: s, fullMark: 100 },
    { subject: 'G', score: g, fullMark: 100 },
  ];

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="80%" data={data}>
          <PolarGrid stroke="#4a5568" />
          <PolarAngleAxis dataKey="subject" tick={{ fill: '#e2e8f0', fontSize: 14 }} />
          <Radar name="Score" dataKey="score" stroke="#4db8ff" fill="#4db8ff" fillOpacity={0.6} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
};
