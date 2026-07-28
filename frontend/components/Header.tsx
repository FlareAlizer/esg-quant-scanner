
import React from 'react';

export const Header: React.FC = () => {
  return (
    <header className="text-center mb-8">
      <h1 className="text-4xl md:text-5xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-brand-secondary to-blue-300">
        ESG Quant Scanner
      </h1>
      <p className="mt-4 text-lg text-neutral-300 max-w-3xl mx-auto">
        AI-driven insights into corporate sustainability. We provide transparent, goal-oriented ESG assessments based on public data.
      </p>
    </header>
  );
};
