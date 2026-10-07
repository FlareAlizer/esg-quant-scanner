import React, { useState } from 'react';
import { api } from '../services/api';

/**
 * Question box about the asset on screen. The request goes to the backend,
 * which builds the profile and calls the model with the server-side key.
 */
export const AIAssistant: React.FC<{ ticker: string }> = ({ ticker }) => {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || isLoading) return;

    setIsLoading(true);
    setError(null);
    setAnswer('');

    try {
      setAnswer(await api.ask(ticker, question.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось получить ответ.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-neutral-900/40 p-6 rounded-xl">
      <h3 className="text-xl font-bold mb-2">Вопрос по профилю</h3>
      <p className="text-sm text-neutral-400 mb-4">
        Модель отвечает только по данным скоринга выше и не знает ничего сверх них.
      </p>

      <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Например: что сильнее всего тянет балл вниз?"
          maxLength={500}
          className="flex-grow bg-neutral-800 border-2 border-neutral-700 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-brand-secondary"
          disabled={isLoading}
        />
        <button
          type="submit"
          className="px-4 py-2 bg-brand-secondary/80 text-brand-primary font-semibold rounded-lg hover:bg-brand-secondary disabled:bg-neutral-600 disabled:cursor-not-allowed transition-colors"
          disabled={isLoading || !question.trim()}
        >
          {isLoading ? 'Думаю...' : 'Спросить'}
        </button>
      </form>

      {(answer || error) && (
        <div className="mt-4 p-4 bg-neutral-800 rounded-lg">
          {error && <p className="text-red-400">{error}</p>}
          {answer && <p className="text-neutral-300 whitespace-pre-wrap">{answer}</p>}
        </div>
      )}
    </div>
  );
};
