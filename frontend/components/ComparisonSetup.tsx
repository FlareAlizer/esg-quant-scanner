import React, { useState } from 'react';

interface ComparisonSetupProps {
  onCompare: (tickers: string[]) => void;
  isLoading: boolean;
}

const MAX_TICKERS = 5;

/** "msft, ko  jpm" -> ["MSFT", "KO", "JPM"], without duplicates. */
const parseTickers = (raw: string) => [...new Set(raw.toUpperCase().split(/[\s,;]+/).filter(Boolean))];

export const ComparisonSetup: React.FC<ComparisonSetupProps> = ({ onCompare, isLoading }) => {
  const [raw, setRaw] = useState('');
  const tickers = parseTickers(raw);
  const valid = tickers.length >= 2 && tickers.length <= MAX_TICKERS;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (valid) onCompare(tickers);
  };

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl mx-auto bg-neutral-800/50 p-6 rounded-xl border border-neutral-700">
      <input
        type="text"
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        placeholder="Тикеры через пробел или запятую: MSFT KO JPM"
        className="w-full px-4 py-3 mb-4 bg-neutral-800 border-2 border-neutral-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-secondary"
        disabled={isLoading}
      />
      <button
        type="submit"
        className="w-full py-3 px-6 bg-brand-primary text-white font-semibold rounded-lg hover:bg-blue-800 disabled:bg-neutral-600 disabled:cursor-not-allowed transition-colors"
        disabled={isLoading || !valid}
      >
        {isLoading ? 'Загрузка...' : `Сравнить (${tickers.length})`}
      </button>
      {!valid && (
        <p className="text-center text-sm text-neutral-400 mt-3">От двух до {MAX_TICKERS} тикеров.</p>
      )}
    </form>
  );
};
