
import React, { useState } from 'react';

interface SearchBarProps {
  onSearch: (query: string) => void;
  isLoading: boolean;
}

const SearchIcon: React.FC = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>
);


export const SearchBar: React.FC<SearchBarProps> = ({ onSearch, isLoading }) => {
  const [query, setQuery] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(query);
  };

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl mx-auto">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter company name or ticker (e.g., Tech Giant Inc)"
          className="w-full pl-5 pr-28 py-3 bg-neutral-800 border-2 border-neutral-700 rounded-full focus:outline-none focus:ring-2 focus:ring-brand-secondary focus:border-transparent transition-all"
          disabled={isLoading}
        />
        <button
          type="submit"
          className="absolute inset-y-0 right-0 flex items-center px-6 m-1.5 bg-brand-primary text-white font-semibold rounded-full hover:bg-blue-800 disabled:bg-neutral-600 disabled:cursor-not-allowed transition-colors"
          disabled={isLoading}
        >
          {isLoading ? '...' : <SearchIcon />}
          <span className="ml-2 hidden sm:inline">Search</span>
        </button>
      </div>
    </form>
  );
};
