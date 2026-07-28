
import React from 'react';
import { type CompanyESGData } from '../types';
import { ScoreCard } from './ScoreCard';
import { ESGRadarChart } from './ESGRadarChart';
import { ExplanationAccordion } from './ExplanationAccordion';
import { AIAssistant } from './AIAssistant';
import { NewsFeed } from './NewsFeed';

interface CompanyDashboardProps {
  data: CompanyESGData;
}

export const CompanyDashboard: React.FC<CompanyDashboardProps> = ({ data }) => {
  
  const getRiskColor = (risk: 'Low' | 'Medium' | 'High') => {
    switch(risk) {
      case 'Low': return 'bg-green-500';
      case 'Medium': return 'bg-yellow-500';
      case 'High': return 'bg-red-500';
      default: return 'bg-neutral-500';
    }
  }

  const getConfidenceColor = (level: 'Low' | 'Medium' | 'High') => {
    switch(level) {
      case 'Low': return 'text-red-400';
      case 'Medium': return 'text-yellow-400';
      case 'High': return 'text-green-400';
      default: return 'text-neutral-400';
    }
  }

  return (
    <div className="bg-neutral-800/50 p-4 sm:p-6 rounded-2xl shadow-lg border border-neutral-700">
      <header className="mb-6">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center">
          <div>
            <h2 className="text-3xl font-bold text-white">{data.name} ({data.ticker})</h2>
            <p className="text-neutral-400">{data.industry} - {data.country}</p>
          </div>
          <div className="flex items-center space-x-4 mt-4 sm:mt-0">
             <div className="text-right">
                <span className="text-sm font-medium text-neutral-400">Risk Score</span>
                <div className={`mt-1 px-3 py-1 text-sm font-bold text-white rounded-full ${getRiskColor(data.riskScore)}`}>
                  {data.riskScore}
                </div>
            </div>
            <div className="text-right">
                <span className="text-sm font-medium text-neutral-400">Confidence</span>
                 <div className={`mt-1 font-bold ${getConfidenceColor(data.confidenceLevel)}`}>
                  {data.confidenceLevel}
                </div>
            </div>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 flex flex-col items-center justify-center space-y-6 bg-neutral-900/40 p-6 rounded-xl">
          <ScoreCard score={data.totalScore} />
          <ESGRadarChart e={data.e.score} s={data.s.score} g={data.g.score} />
        </div>

        <div className="lg:col-span-2 space-y-6">
           <div className="bg-neutral-900/40 p-6 rounded-xl">
            <h3 className="text-xl font-bold mb-2">AI-Generated Summary</h3>
            <p className="text-neutral-300">{data.summary}</p>
          </div>
          <ExplanationAccordion eData={data.e} sData={data.s} gData={data.g} />
          <NewsFeed news={data.news} />
          <AIAssistant context={data.summary} />
        </div>
      </div>
    </div>
  );
};
