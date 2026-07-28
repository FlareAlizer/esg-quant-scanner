
import React from 'react';
import { type NewsItem } from '../types';

interface NewsFeedProps {
  news: NewsItem[];
}

const ExternalLinkIcon: React.FC = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 ml-1 inline-block text-neutral-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
  </svg>
);


export const NewsFeed: React.FC<NewsFeedProps> = ({ news }) => {
  return (
    <div className="bg-neutral-900/40 p-6 rounded-xl">
      <h3 className="text-xl font-bold mb-4">Recent ESG News</h3>
      <ul className="space-y-4">
        {news.map((item, index) => (
          <li key={index}>
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block p-4 bg-neutral-800/60 rounded-lg hover:bg-neutral-700/80 transition-colors group"
            >
              <p className="font-semibold text-neutral-200 group-hover:text-brand-secondary">{item.title} <ExternalLinkIcon/></p>
              <div className="flex justify-between items-center mt-2 text-sm text-neutral-400">
                <span>{item.source}</span>
                <span>{item.date}</span>
              </div>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
};
