
import React, { useState, useRef, useEffect } from 'react';
import { geminiService } from '../services/geminiService';

interface AIAssistantProps {
  context: string;
}

export const AIAssistant: React.FC<AIAssistantProps> = ({ context }) => {
  const [question, setQuestion] = useState<string>('');
  const [answer, setAnswer] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const answerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (answerRef.current) {
      answerRef.current.scrollTop = answerRef.current.scrollHeight;
    }
  }, [answer]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || isLoading) return;

    setIsLoading(true);
    setError(null);
    setAnswer('');
    
    try {
      const stream = geminiService.generateStream(context, question);
      for await (const chunk of stream) {
        setAnswer(prev => prev + chunk);
      }
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unknown error occurred while contacting the AI assistant.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-neutral-900/40 p-6 rounded-xl">
      <h3 className="text-xl font-bold mb-4">Ask AI Assistant</h3>
      <p className="text-sm text-neutral-400 mb-4">
        Ask a question about the company's ESG summary above. The AI will answer based only on the provided text.
      </p>
      
      <form onSubmit={handleSubmit}>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g., How is their employee turnover?"
            className="flex-grow bg-neutral-800 border-2 border-neutral-700 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-brand-secondary"
            disabled={isLoading}
          />
          <button
            type="submit"
            className="px-4 py-2 bg-brand-secondary/80 text-brand-primary font-semibold rounded-lg hover:bg-brand-secondary disabled:bg-neutral-600 disabled:cursor-not-allowed transition-colors"
            disabled={isLoading || !question.trim()}
          >
            {isLoading ? 'Thinking...' : 'Ask'}
          </button>
        </div>
      </form>

      {(answer || isLoading || error) && (
        <div className="mt-4 p-4 bg-neutral-800 rounded-lg min-h-[80px]">
          {error && <p className="text-red-400">{error}</p>}
          {isLoading && !answer && (
             <div className="flex items-center space-x-2 text-neutral-400">
                <div className="w-2 h-2 bg-brand-secondary rounded-full animate-pulse"></div>
                <div className="w-2 h-2 bg-brand-secondary rounded-full animate-pulse [animation-delay:0.2s]"></div>
                <div className="w-2 h-2 bg-brand-secondary rounded-full animate-pulse [animation-delay:0.4s]"></div>
                <span>Generating response...</span>
             </div>
          )}
          {answer && (
            <div ref={answerRef} className="prose prose-invert prose-sm max-w-none text-neutral-300 whitespace-pre-wrap">
              {answer}
              {isLoading && <span className="inline-block w-2 h-4 bg-neutral-100 animate-pulse ml-1"></span>}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
