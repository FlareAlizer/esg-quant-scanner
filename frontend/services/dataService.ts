import { type CompanyESGData } from "../types";

/** Client for the Python backend. */

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000/api/v1";

const REQUEST_TIMEOUT_MS = 30_000;

async function extractErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return body?.detail ?? body?.message ?? fallback;
  } catch {
    // Not JSON (a proxy 502 page, say). The status is more useful than nothing.
    return `${fallback} (HTTP ${response.status})`;
  }
}

export const dataService = {
  async fetchCompanyData(ticker: string): Promise<CompanyESGData> {
    // Tickers like BHARTIARTL.NS and BRK.B contain dots, and users type spaces.
    const url = `${API_BASE_URL}/esg-score/${encodeURIComponent(ticker.trim())}`;

    // Without this a hung backend leaves the UI loading forever.
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
      const response = await fetch(url, { signal: controller.signal });

      if (!response.ok) {
        throw new Error(await extractErrorMessage(response, `Не удалось получить данные для ${ticker}`));
      }

      return (await response.json()) as CompanyESGData;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new Error(`Превышено время ожидания (${REQUEST_TIMEOUT_MS / 1000}с). Бэкенд запущен?`);
      }
      throw error instanceof Error ? error : new Error("Неизвестная ошибка запроса.");
    } finally {
      clearTimeout(timer);
    }
  },
};
