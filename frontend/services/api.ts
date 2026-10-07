import { type AssetScore } from '../types';

/**
 * Client for the Python backend (backend/api.py).
 *
 * The default is a relative path: in dev Vite proxies /api to the backend, see
 * vite.config.ts. The model key lives on the server and never reaches the
 * browser, so there is nothing secret to configure here.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

// Scoring a new ticker means several upstream calls, with the LLM it can take a minute.
const REQUEST_TIMEOUT_MS = 120_000;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Without this a hung backend leaves the UI loading forever.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { ...init, signal: controller.signal });

    if (!response.ok) {
      let detail = `Ошибка запроса (HTTP ${response.status}).`;
      try {
        const body = await response.json();
        if (typeof body?.detail === 'string') detail = body.detail;
      } catch {
        // Not JSON (a proxy error page, say). The status is more useful than nothing.
      }
      throw new Error(detail);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`Превышено время ожидания (${REQUEST_TIMEOUT_MS / 1000} с).`);
    }
    if (error instanceof TypeError) {
      throw new Error('Бэкенд недоступен. Запущен ли uvicorn?');
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  health(): Promise<{ status: string; llm_enabled: boolean }> {
    return request('/health');
  },

  /** Tickers like BHARTIARTL.NS and BRK-B contain punctuation, and users type spaces. */
  fetchScore(ticker: string): Promise<AssetScore> {
    return request(`/score/${encodeURIComponent(ticker.trim())}`);
  },

  async ask(ticker: string, question: string): Promise<string> {
    const body = await request<{ answer: string }>('/assistant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, question }),
    });
    return body.answer;
  },
};
