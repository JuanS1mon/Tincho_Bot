"use client";
import { useEffect, useRef, useState } from "react";

interface Message {
  role: "user" | "marquitos";
  content: string;
}

const QUICK_QUESTIONS = [
  "¿Cómo vas hoy?",
  "¿Hay algún pump?",
  "¿Cuánto llevo de PnL?",
  "¿Arrancamos?",
];
export default function MarquitosChat({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [history, setHistory] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, isOpen, loading]);

  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 100);
  }, [isOpen]);

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return;
    const userMsg: Message = { role: "user", content: text.trim() };
    setHistory(h => [...h, userMsg]);
    setInput("");
    setLoading(true);
    try {
      const res = await fetch("/api/marquitos/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMsg.content,
          history: history.map(m => ({ role: m.role, content: m.content })),
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.reply) {
        setHistory(h => [...h, { role: "marquitos", content: `❌ Error: ${data.detail ?? "sin respuesta"}` }]);
      } else {
        setHistory(h => [...h, { role: "marquitos", content: data.reply }]);
      }
    } catch {
      setHistory(h => [...h, { role: "marquitos", content: "❌ No pude conectarme con el servidor. ¿Está corriendo el bot?" }]);
    } finally {
      setLoading(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed bottom-[13rem] right-4 z-40 w-[22rem] max-h-[520px] rounded-2xl border border-red-500/30 bg-[var(--card)] shadow-2xl shadow-red-500/20 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--border)] bg-red-500/8 flex items-center gap-3 flex-shrink-0">
        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-red-500 to-orange-700 flex items-center justify-center text-lg flex-shrink-0 select-none shadow-md">🔥</div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-bold text-red-200">Marquitos</div>
          <div className="text-[10px] text-red-300/60">Scalper · Adicto a TODO</div>
        </div>
        <div className="flex items-center gap-2">
          {history.length > 0 && (
            <button
              onClick={() => setHistory([])}
              title="Limpiar chat"
              className="text-[10px] text-red-400/60 hover:text-red-300 px-1.5 py-0.5 rounded hover:bg-red-500/10 transition-colors"
            >
              limpiar
            </button>
          )}
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--text)] p-1 rounded-lg hover:bg-white/5 transition-colors">✕</button>
        </div>
      </div>
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
        {/* Mensaje de bienvenida */}
        {history.length === 0 && (
          <div className="space-y-3">
            <div className="flex gap-2 items-start">
              <div className="w-7 h-7 rounded-full bg-red-600/30 flex items-center justify-center text-sm flex-shrink-0 mt-0.5">🔥</div>
              <div className="rounded-2xl rounded-tl-none px-3 py-2.5 text-xs bg-red-500/10 border border-red-500/20 flex-1 text-[var(--text)] leading-relaxed">
                ¡Soy Marquitos! Scalper adicto a TODO. 0.8% de ganancia y salgo. ¿Operamos?
              </div>
            </div>
            <div className="pl-9 flex flex-wrap gap-1.5">
              {QUICK_QUESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="text-[10px] px-2 py-1 rounded-full border border-red-500/30 text-red-300/80 hover:bg-red-500/15 hover:text-red-200 hover:border-red-400/50 transition-all"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {/* Historial */}
        {history.map((msg, i) => (
          <div key={i} className={`flex gap-2 items-start ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
            {msg.role === "marquitos" && (
              <div className="w-7 h-7 rounded-full bg-red-600/30 flex items-center justify-center text-sm flex-shrink-0 mt-0.5">🔥</div>
            )}
            <div className={`flex flex-col gap-2 max-w-[82%] ${msg.role === "user" ? "items-end ml-auto" : "items-start"}`}>
              <div
                className={`rounded-2xl px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap ${
                  msg.role === "user"
                    ? "rounded-tr-none bg-red-600/25 border border-red-500/30 text-red-100"
                    : "rounded-tl-none bg-[var(--bg)] border border-[var(--border)] text-[var(--text)]"
                }`}
              >
                {msg.content}
              </div>
            </div>
          </div>
        ))}
        {/* Typing indicator */}
        {loading && (
          <div className="flex gap-2 items-start">
            <div className="w-7 h-7 rounded-full bg-red-600/30 flex items-center justify-center text-sm flex-shrink-0 mt-0.5">🔥</div>
            <div className="rounded-2xl rounded-tl-none px-3 py-2.5 bg-[var(--bg)] border border-[var(--border)] flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      {/* Input */}
      <div className="p-3 border-t border-[var(--border)] flex-shrink-0">
        <form
          onSubmit={e => { e.preventDefault(); sendMessage(input); }}
          className="flex gap-2 items-center"
        >
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Preguntale algo a Marquitos..."
            disabled={loading}
            className="flex-1 px-3 py-2 rounded-xl bg-white/5 border border-[var(--border)] text-xs text-[var(--text)] placeholder-[var(--muted)] focus:outline-none focus:border-red-500/50 disabled:opacity-50 transition-all"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="w-8 h-8 rounded-xl bg-red-600 hover:bg-red-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-all active:scale-95 flex-shrink-0 text-white text-sm"
          >
            ↑
          </button>
        </form>
      </div>
    </div>
  );
}
