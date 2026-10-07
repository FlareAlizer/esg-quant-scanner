import React, { useState } from 'react';

interface SearchBarProps {
  onSearch: (ticker: string) => void;
  isLoading: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({ onSearch, isLoading }) => {
  const [query, setQuery] = useState('');
  const ticker = query.trim();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (ticker) onSearch(ticker);
  };

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl mx-auto">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Тикер, например MSFT или BHARTIARTL.NS"
          maxLength={15}
          className="w-full pl-5 pr-32 py-3 bg-neutral-800 border-2 border-neutral-700 rounded-full focus:outline-none focus:ring-2 focus:ring-brand-secondary focus:border-transparent transition-all"
          disabled={isLoading}
        />
        <button
          type="submit"
          className="absolute inset-y-0 right-0 flex items-center px-6 m-1.5 bg-brand-primary text-white font-semibold rounded-full hover:bg-blue-800 disabled:bg-neutral-600 disabled:cursor-not-allowed transition-colors"
          disabled={isLoading || !ticker}
        >
          {isLoading ? '...' : 'Оценить'}
        </button>
      </div>
    </form>
  );
};
