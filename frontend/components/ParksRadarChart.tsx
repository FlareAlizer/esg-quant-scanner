import React from 'react';
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from 'recharts';
import { COMPONENT_CODES, type AssetScore } from '../types';

export const ParksRadarChart: React.FC<{ components: AssetScore['components'] }> = ({ components }) => {
  // A component without data is drawn at the centre and marked in the breakdown.
  const data = COMPONENT_CODES.map(code => ({ subject: code, score: components[code].score ?? 0 }));

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="80%" data={data}>
          <PolarGrid stroke="#4a5568" />
          <PolarAngleAxis dataKey="subject" tick={{ fill: '#e2e8f0', fontSize: 14 }} />
          {/* Fixed scale: without it the chart stretches to the largest value. */}
          <PolarRadiusAxis domain={[0, 10]} tick={false} axisLine={false} />
          <Radar name="Балл" dataKey="score" stroke="#4db8ff" fill="#4db8ff" fillOpacity={0.6} isAnimationActive={false} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
};
