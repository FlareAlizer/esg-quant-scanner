import React, { useCallback, useEffect, useState } from 'react';
import { Header } from './components/Header';
import { SearchBar } from './components/SearchBar';
import { CompanyDashboard } from './components/CompanyDashboard';
import { ComparisonSetup } from './components/ComparisonSetup';
import { ComparisonDashboard } from './components/ComparisonDashboard';
import { api } from './services/api';
import { type AssetScore } from './types';

const Spinner: React.FC = () => (
  <div className="flex justify-center items-center p-8">
    <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-brand-secondary"></div>
  </div>
);

const ErrorBox: React.FC<{ message: string }> = ({ message }) => (
  <div className="text-center p-8 bg-red-900/50 border border-red-700 rounded-lg">
    <p className="text-xl font-semibold text-red-300">Ошибка</p>
    <p className="mt-2 text-red-400">{message}</p>
  </div>
);

const errorText = (err: unknown) => (err instanceof Error ? err.message : 'Неизвестная ошибка.');

const App: React.FC = () => {
  const [isCompareMode, setIsCompareMode] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [single, setSingle] = useState<AssetScore | null>(null);
  const [compared, setCompared] = useState<AssetScore[] | null>(null);
  // null until the backend has answered; the assistant is offered only on true.
  const [llmEnabled, setLlmEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    api.health().then(h => setLlmEnabled(h.llm_enabled)).catch(() => setLlmEnabled(null));
  }, []);

  const run = useCallback(async (job: () => Promise<void>) => {
    setIsLoading(true);
    setError(null);
    setSingle(null);
    setCompared(null);
    try {
      await job();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleSearch = useCallback(
    (ticker: string) => run(async () => setSingle(await api.fetchScore(ticker))),
    [run],
  );

  const handleCompare = useCallback(
    (tickers: string[]) => run(async () => setCompared(await Promise.all(tickers.map(t => api.fetchScore(t))))),
    [run],
  );

  // /?ticker=MSFT opens straight on a scored asset, so a result can be linked to.
  useEffect(() => {
    const ticker = new URLSearchParams(window.location.search).get('ticker');
    if (ticker) handleSearch(ticker);
  }, [handleSearch]);

  const toggleCompareMode = () => {
    setIsCompareMode(prev => !prev);
    setError(null);
    setSingle(null);
    setCompared(null);
  };

  const renderContent = () => {
    if (isLoading) return <Spinner />;
    if (error) return <ErrorBox message={error} />;
    if (compared) return <ComparisonDashboard assets={compared} />;
    if (single) return <CompanyDashboard data={single} assistantEnabled={llmEnabled === true} />;
    return (
      <div className="text-center p-8 bg-neutral-800/50 border border-dashed border-neutral-700 rounded-lg mt-12">
        <p className="max-w-2xl mx-auto text-neutral-400">
          Введите тикер Yahoo Finance, чтобы получить балл PARKS, или переключитесь в режим сравнения.
        </p>
        {llmEnabled === false && (
          <p className="mt-4 max-w-2xl mx-auto text-sm text-neutral-500">
            На сервере не задан LLM_API_KEY: компоненты K и S не оцениваются, ассистент отключён.
          </p>
        )}
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
            {isCompareMode ? 'Один актив' : 'Сравнить активы'}
          </button>
        </div>

        {isCompareMode ? (
          <ComparisonSetup onCompare={handleCompare} isLoading={isLoading} />
        ) : (
          <SearchBar onSearch={handleSearch} isLoading={isLoading} />
        )}

        <div className="mt-8">{renderContent()}</div>
      </main>
      <footer className="text-center py-4 text-neutral-500 text-sm">
        <p>Учебный проект. Не является инвестиционной рекомендацией.</p>
      </footer>
    </div>
  );
};

export default App;
