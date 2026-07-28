
import React, { useState } from 'react';

interface ComparisonSetupProps {
  onCompare: (companies: string[]) => void;
  isLoading: boolean;
}

// Mocked list of available companies for comparison
const AVAILABLE_COMPANIES = ['Tech Giant Inc', 'Global Energy Co'];

export const ComparisonSetup: React.FC<ComparisonSetupProps> = ({ onCompare, isLoading }) => {
  const [selectedCompanies, setSelectedCompanies] = useState<string[]>([]);

  const handleCheckboxChange = (companyName: string) => {
    setSelectedCompanies(prev =>
      prev.includes(companyName)
        ? prev.filter(name => name !== companyName)
        : [...prev, companyName]
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCompare(selectedCompanies);
  };

  return (
    <div className="max-w-2xl mx-auto bg-neutral-800/50 p-6 rounded-xl border border-neutral-700">
      <h2 className="text-2xl font-bold text-center mb-4">Select Companies to Compare</h2>
      <form onSubmit={handleSubmit}>
        <div className="mb-6 space-y-3">
          {AVAILABLE_COMPANIES.map(company => (
            <label key={company} className="flex items-center p-3 bg-neutral-700/50 rounded-lg cursor-pointer hover:bg-neutral-700 transition-colors">
              <input
                type="checkbox"
                className="h-5 w-5 rounded bg-neutral-800 border-neutral-600 text-brand-secondary focus:ring-brand-secondary"
                checked={selectedCompanies.includes(company)}
                onChange={() => handleCheckboxChange(company)}
                disabled={isLoading}
              />
              <span className="ml-3 text-lg font-medium text-neutral-200">{company}</span>
            </label>
          ))}
        </div>
        <button
          type="submit"
          className="w-full py-3 px-6 bg-brand-primary text-white font-semibold rounded-lg hover:bg-blue-800 disabled:bg-neutral-600 disabled:cursor-not-allowed transition-colors"
          disabled={isLoading || selectedCompanies.length < 2}
        >
          {isLoading ? 'Loading...' : `Compare (${selectedCompanies.length})`}
        </button>
         {selectedCompanies.length < 2 && (
            <p className="text-center text-sm text-neutral-400 mt-3">Please select at least two companies.</p>
        )}
      </form>
    </div>
  );
};
