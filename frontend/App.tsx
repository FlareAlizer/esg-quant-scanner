
import React, { useState, useCallback } from 'react';
import { Header } from './components/Header';
import { SearchBar } from './components/SearchBar';
import { CompanyDashboard } from './components/CompanyDashboard';
import { ComparisonSetup } from './components/ComparisonSetup';
import { ComparisonDashboard } from './components/ComparisonDashboard';
import { dataService } from './services/dataService';
import { type CompanyESGData } from './types';

const App: React.FC = () => {
  // State for single company search
  const [companyData, setCompanyData] = useState<CompanyESGData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [initialLoad, setInitialLoad] = useState<boolean>(true);

  // State for multi-company comparison
  const [isCompareMode, setIsCompareMode] = useState<boolean>(false);
  const [comparisonData, setComparisonData] = useState<CompanyESGData[] | null>(null);
  const [isComparisonLoading, setIsComparisonLoading] = useState<boolean>(false);
  const [comparisonError, setComparisonError] = useState<string | null>(null);


  const handleSearch = useCallback(async (companyName: string) => {
    if (!companyName) {
      setError("Please enter a company name.");
      setCompanyData(null);
      return;
    }
    
    setIsLoading(true);
    setError(null);
    setCompanyData(null);
    setInitialLoad(false);

    try {
      const data = await dataService.fetchCompanyData(companyName);
      setCompanyData(data);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unknown error occurred.");
      }
      setCompanyData(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleCompare = useCallback(async (companyNames: string[]) => {
    if (companyNames.length < 2) {
      setComparisonError("Please select at least two companies to compare.");
      setComparisonData(null);
      return;
    }

    setIsComparisonLoading(true);
    setComparisonError(null);
    setComparisonData(null);

    try {
      const dataPromises = companyNames.map(name => dataService.fetchCompanyData(name));
      const results = await Promise.all(dataPromises);
      setComparisonData(results);
    } catch (err) {
       if (err instanceof Error) {
        setComparisonError(err.message);
      } else {
        setComparisonError("An unknown error occurred while fetching comparison data.");
      }
      setComparisonData(null);
    } finally {
      setIsComparisonLoading(false);
    }
  }, []);

  const toggleCompareMode = () => {
    setIsCompareMode(prev => !prev);
    // Reset all data states when switching modes to ensure a clean slate
    setCompanyData(null);
    setError(null);
    setComparisonData(null);
    setComparisonError(null);
    setInitialLoad(true); // Reset to show welcome message if switching back to single search
  };

  const renderContent = () => {
    // Comparison Mode Content
    if (isCompareMode) {
      if (isComparisonLoading) {
        return (
          <div className="flex justify-center items-center p-8">
            <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-brand-secondary"></div>
          </div>
        );
      }
      if (comparisonError) {
        return (
          <div className="text-center p-8 bg-red-900/50 border border-red-700 rounded-lg">
            <p className="text-xl font-semibold text-red-300">Error</p>
            <p className="mt-2 text-red-400">{comparisonError}</p>
          </div>
        );
      }
      if (comparisonData) {
        return (
          <div className="animate-fade-in">
            <ComparisonDashboard companies={comparisonData} />
          </div>
        );
      }
      return null; // The ComparisonSetup component is rendered outside this function
    }

    // Single Search Mode Content
    if (isLoading) {
       return (
        <div className="flex justify-center items-center p-8">
          <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-brand-secondary"></div>
        </div>
      );
    }
    if (error) {
       return (
        <div className="text-center p-8 bg-red-900/50 border border-red-700 rounded-lg">
          <p className="text-xl font-semibold text-red-300">Error</p>
          <p className="mt-2 text-red-400">{error}</p>
        </div>
      );
    }
    if (companyData) {
      return (
        <div className="animate-fade-in">
          <CompanyDashboard data={companyData} />
        </div>
      );
    }
    if (!initialLoad) {
      return (
        <div className="text-center p-8 bg-neutral-800 border border-neutral-700 rounded-lg">
          <p className="text-xl font-semibold text-neutral-300">No Data Found</p>
          <p className="mt-2 text-neutral-400">Could not find ESG data for the specified company. Please try another name.</p>
        </div>
      );
    }
    // Initial Welcome Message
    return (
      <div className="text-center p-8 bg-neutral-800/50 border border-dashed border-neutral-700 rounded-lg mt-12">
        <h2 className="text-2xl font-bold text-neutral-300">Welcome to the ESG Quant Scanner</h2>
        <p className="mt-4 max-w-2xl mx-auto text-neutral-400">
          Enter a company name above to begin your analysis, or switch to comparison mode to evaluate multiple companies.
        </p>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-neutral-900 text-neutral-100 font-sans">
      <main className="container mx-auto px-4 py-8">
        <Header />

        <div className="max-w-3xl mx-auto text-center mb-6">
          <button
            onClick={toggleCompareMode}
            className="px-6 py-2 font-semibold bg-neutral-700/50 border border-neutral-600 rounded-full hover:bg-neutral-700 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-secondary"
          >
            {isCompareMode ? 'Switch to Single Search' : 'Compare Companies'}
          </button>
        </div>
        
        {isCompareMode ? (
          <ComparisonSetup onCompare={handleCompare} isLoading={isComparisonLoading} />
        ) : (
          <SearchBar onSearch={handleSearch} isLoading={isLoading} />
        )}
        
        <div className="mt-8">
          {renderContent()}
        </div>
      </main>
      <footer className="text-center py-4 text-neutral-500 text-sm">
        <p>ESG Quant Scanner &copy; {new Date().getFullYear()}</p>
      </footer>
    </div>
  );
};

export default App;
