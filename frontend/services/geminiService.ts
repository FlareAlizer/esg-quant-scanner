import { GoogleGenAI } from "@google/genai";

/**
 * Gemini client for the assistant panel.
 *
 * Anything in a browser bundle is public: the key is visible in DevTools and in
 * the built JS. Fine for local dev and demos, not for production. There the call
 * should go browser -> POST /api/assistant -> server -> Gemini, so the key never
 * leaves the server and can be rate limited.
 */

const API_KEY = import.meta.env.VITE_GEMINI_API_KEY as string | undefined;

if (!API_KEY) {
  console.warn(
    "VITE_GEMINI_API_KEY не задан. AI-ассистент отключён. " +
      "Скопируйте .env.example в .env и укажите ключ."
  );
}

const SYSTEM_INSTRUCTION =
  "You are an expert ESG analyst assistant. Answer questions based *only* on the " +
  "provided company ESG summary. Do not use external knowledge. If the answer is not " +
  "in the summary, say the information is not available. Keep answers concise.";

export const geminiService = {
  /** Lets the UI hide the assistant up front when there's no key. */
  isAvailable(): boolean {
    return Boolean(API_KEY);
  },

  /** Streams the response in chunks. */
  async *generateStream(context: string, question: string): AsyncGenerator<string> {
    if (!API_KEY) {
      throw new Error("AI-ассистент не настроен: отсутствует VITE_GEMINI_API_KEY.");
    }

    // Per call rather than per module, so a missing key doesn't break the import.
    const ai = new GoogleGenAI({ apiKey: API_KEY });

    const prompt = `**Company ESG Summary:**\n---\n${context}\n---\n\n**Question:** ${question}`;

    try {
      const stream = await ai.models.generateContentStream({
        model: "gemini-2.5-flash",
        contents: prompt,
        config: { systemInstruction: SYSTEM_INSTRUCTION },
      });

      for await (const chunk of stream) {
        // chunk.text is undefined on control chunks
        if (chunk.text) yield chunk.text;
      }
    } catch (error) {
      console.error("Ошибка вызова Gemini API:", error);
      throw new Error("Не удалось получить ответ от AI-ассистента.");
    }
  },
};
