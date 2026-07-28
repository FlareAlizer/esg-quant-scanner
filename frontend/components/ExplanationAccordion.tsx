
import React, { useState } from 'react';
import { type ScoreDetail } from '../types';

interface AccordionItemProps {
  title: string;
  score: number;
  data: ScoreDetail;
  isOpen: boolean;
  onToggle: () => void;
}

const ChevronDownIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={`h-6 w-6 transition-transform duration-300 ${className}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
  </svg>
);


const AccordionItem: React.FC<AccordionItemProps> = ({ title, score, data, isOpen, onToggle }) => {
  const getPillarColor = (pillar: string) => {
    switch (pillar) {
      case 'E': return 'text-green-400';
      case 'S': return 'text-blue-400';
      case 'G': return 'text-purple-400';
      default: return 'text-neutral-100';
    }
  }

  return (
    <div className="border border-neutral-700 rounded-lg overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex justify-between items-center p-4 bg-neutral-700/50 hover:bg-neutral-700 transition-colors"
      >
        <div className="flex items-center">
          <span className={`text-xl font-bold ${getPillarColor(title)}`}>{title}</span>
          <span className="ml-4 text-lg font-semibold text-white">Score: {score}</span>
        </div>
        <ChevronDownIcon className={isOpen ? 'rotate-180' : ''} />
      </button>
      <div className={`transition-all duration-300 ease-in-out ${isOpen ? 'max-h-screen' : 'max-h-0'}`}>
        <div className="p-4 bg-neutral-900/40">
          <p className="font-semibold mb-3 text-neutral-300">Overall Explanation:</p>
          <p className="mb-4 text-neutral-400 italic">{data.explanation}</p>
          <div className="space-y-3">
            <p className="font-semibold text-neutral-300">Key Performance Indicators (KPIs):</p>
            {data.kpis.map((kpi) => (
              <div key={kpi.name} className="p-3 bg-neutral-800/60 rounded-md">
                <p className="font-bold text-neutral-200">{kpi.name}</p>
                <p className="text-sm text-neutral-400 whitespace-pre-wrap">{kpi.details}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

interface ExplanationAccordionProps {
  eData: ScoreDetail;
  sData: ScoreDetail;
  gData: ScoreDetail;
}

export const ExplanationAccordion: React.FC<ExplanationAccordionProps> = ({ eData, sData, gData }) => {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const handleToggle = (index: number) => {
    setOpenIndex(openIndex === index ? null : index);
  };

  return (
    <div className="space-y-2">
      <h3 className="text-xl font-bold mb-2 text-white">Detailed Score Breakdown</h3>
      <AccordionItem title="E" score={eData.score} data={eData} isOpen={openIndex === 0} onToggle={() => handleToggle(0)} />
      <AccordionItem title="S" score={sData.score} data={sData} isOpen={openIndex === 1} onToggle={() => handleToggle(1)} />
      <AccordionItem title="G" score={gData.score} data={gData} isOpen={openIndex === 2} onToggle={() => handleToggle(2)} />
    </div>
  );
};
