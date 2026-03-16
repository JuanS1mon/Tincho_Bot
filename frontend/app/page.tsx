"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
const MarquitosChat = dynamic(() => import("./MarquitosChat"), { ssr: false });

// ── Types ─────────────────────────────────────────────────────────────────────

interface Portfolio {
  capital: number;
  available_capital: number;
  initial_capital: number;
  total_pnl: number;
  total_trades: number;
  winning_trades: number;
  win_rate: number;
  open_positions: number;
  positions: Record<string, Position>;
}

interface Position {
  direction: string;
  entry_price: number;
  current_price: number;
  quantity: number;
  capital_used: number;
  stop_loss: number;
  take_profit: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

interface MarketSnapshot {
  price: number;
  trend: string;
  rsi: number;
  sma20: number;
  sma50: number;
  volume_trend: string;
  oi_trend: string;
  funding_rate: number;
}

interface Signal {
  signal: string;
  strategy: string;
  confidence: number;
  reason: string;
}

interface AgentStatus {
  status: string;
  cycle: number;
  dry_run: boolean;
  last_cycle_time: number;
  last_error: string;
  symbols: string[];
  recovered_positions?: RecoveredPosition[];
}

interface RecoveredPosition {
  symbol: string;
  direction: string;
  entry_price: number;
  quantity: number;
  timestamp: number;
}

interface Trade {
  symbol: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  pnl_pct: number;
  strategy: string;
  duration_seconds: number;
  timestamp: number;
}

// ── Fetch helper ──────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`/api${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// ── Badge components ──────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ANALYZING: "bg-blue-500/20 text-blue-400 border-blue-500/40",
    IDLE:      "bg-slate-500/20 text-slate-400 border-slate-500/40",
    ERROR:     "bg-red-500/20 text-red-400 border-red-500/40",
    STOPPED:   "bg-slate-600/20 text-slate-500 border-slate-600/40",
  };
  const cls = colors[status] ?? "bg-slate-500/20 text-slate-400 border-slate-500/40";
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      {status}
    </span>
  );
}

function TrendBadge({ trend }: { trend: string }) {
  const colors: Record<string, string> = {
    BULLISH: "text-green-400",
    BEARISH: "text-red-400",
    NEUTRAL: "text-yellow-400",
  };
  const arrows: Record<string, string> = {
    BULLISH: "▲",
    BEARISH: "▼",
    NEUTRAL: "→",
  };
  return (
    <span className={`font-semibold ${colors[trend] ?? "text-slate-400"}`}>
      {arrows[trend] ?? "?"} {trend}
    </span>
  );
}

function SignalBadge({ signal }: { signal: string }) {
  if (signal === "LONG")
    return <span className="px-2 py-0.5 rounded text-xs font-bold bg-green-500/20 text-green-400 border border-green-500/30">LONG</span>;
  if (signal === "SHORT")
    return <span className="px-2 py-0.5 rounded text-xs font-bold bg-red-500/20 text-red-400 border border-red-500/30">SHORT</span>;
  return <span className="px-2 py-0.5 rounded text-xs font-medium bg-slate-700/40 text-slate-500 border border-slate-600/30">SIN SEÑAL</span>;
}

function PnlValue({ value }: { value: number }) {
  const cls = value > 0 ? "text-green-400" : value < 0 ? "text-red-400" : "text-slate-400";
  const sign = value > 0 ? "+" : "";
  return <span className={`font-mono font-semibold ${cls}`}>{sign}{value.toFixed(4)} USDT</span>;
}

// ── Card wrapper ──────────────────────────────────────────────────────────────

function Card({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 lg:p-6 ${className}`}>
      <h2 className="text-xs font-semibold uppercase tracking-widest text-[var(--muted)] mb-4 lg:mb-5">{title}</h2>
      {children}
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div>
      <div className="text-xs lg:text-sm text-[var(--muted)] mb-0.5">{label}</div>
      <div className="text-lg lg:text-xl font-semibold leading-tight">{value}</div>
      {sub && <div className="text-xs text-[var(--muted)] mt-0.5">{sub}</div>}
    </div>
  );
}

// ── RSI Bar ───────────────────────────────────────────────────────────────────

function RsiBar({ rsi }: { rsi: number }) {
  const color = rsi > 70 ? "bg-red-500" : rsi < 30 ? "bg-blue-400" : rsi > 50 ? "bg-green-500" : "bg-yellow-400";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-[var(--muted)]">
        <span>RSI</span>
        <span className="font-mono font-semibold text-[var(--text)]">{rsi.toFixed(1)}</span>
      </div>
      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${rsi}%` } as React.CSSProperties} />
      </div>
      <div className="flex justify-between text-[10px] text-[var(--muted)]">
        <span>0</span><span>30</span><span>50</span><span>70</span><span>100</span>
      </div>
    </div>
  );
}

// ── Offline state ─────────────────────────────────────────────────────────────

function OfflineBanner() {
  return (
    <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-4 text-sm text-yellow-300 flex items-center gap-3">
      <span className="text-lg">⚠️</span>
      <div>
        <strong>Agente no detectado</strong>
        <div className="text-yellow-400/70 text-xs mt-0.5">
          Iniciá el bot con <code className="bg-yellow-900/30 px-1 rounded">python app/main.py --dry-run --interval 60</code> y recargá la página.
        </div>
      </div>
    </div>
  );
}

function RecoveredPositionsBanner({ positions }: { positions: RecoveredPosition[] }) {
  if (!positions.length) return null;

  return (
    <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-4 text-sm text-cyan-200">
      <div className="flex items-start gap-3">
        <span className="text-lg">↺</span>
        <div className="min-w-0 flex-1">
          <div className="font-semibold text-cyan-100">Posiciones recuperadas tras reinicio</div>
          <div className="text-cyan-200/75 text-xs mt-0.5">
            El bot volvió a cargar posiciones abiertas desde Binance y las está monitoreando otra vez.
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {positions.map((pos) => (
              <div
                key={`${pos.symbol}-${pos.timestamp}`}
                className="rounded-lg border border-cyan-400/20 bg-black/20 px-3 py-2"
              >
                <div className="font-mono text-cyan-50 text-xs">
                  {pos.symbol} · {pos.direction}
                </div>
                <div className="text-[11px] text-cyan-200/70 mt-0.5">
                  entrada ${pos.entry_price.toLocaleString()} · qty {pos.quantity}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Trading alert ─────────────────────────────────────────────────────────────

function TradingAlert({ count, positions }: { count: number; positions: Record<string, Position> }) {
  const symbols = Object.keys(positions).join(", ");
  return (
    <div className="rounded-2xl border-2 border-green-500/60 bg-green-500/10 shadow-lg shadow-green-500/20 overflow-hidden">
      <div className="flex flex-col sm:flex-row items-center gap-6 p-8">
        <div className="flex-shrink-0">
          <img src="/trading.gif" alt="Operando" className="h-40 w-40 rounded-2xl object-cover shadow-md" />
        </div>
        <div className="flex-1 min-w-0 text-center sm:text-left">
          <span className="inline-flex items-center gap-2 px-5 py-2 rounded-full text-xl font-black bg-green-500/20 text-green-300 border-2 border-green-500/50 animate-pulse mb-3">
            🚀 OPERANDO
          </span>
          <p className="text-3xl font-bold text-green-300 mt-2">
            {count} posición{count !== 1 ? "es" : ""} activa{count !== 1 ? "s" : ""}
          </p>
          <p className="text-lg text-green-300/60 font-mono mt-1 truncate">{symbols}</p>
        </div>
      </div>
    </div>
  );
}

// ── No-signal alert ───────────────────────────────────────────────────────────

function NoSignalAlert({ reasons }: { reasons: { symbol: string; reason: string }[] }) {
  return (
    <div className="rounded-2xl border-2 border-amber-500/50 bg-amber-500/8 shadow-lg shadow-amber-500/10 overflow-hidden">
      <div className="flex flex-col sm:flex-row items-center gap-6 p-8">
        <div className="flex-shrink-0">
          <img src="/no-trading.gif" alt="Sin operaciones" className="h-40 w-40 rounded-2xl object-cover shadow-md" />
        </div>
        <div className="flex-1 min-w-0 text-center sm:text-left">
          <span className="inline-flex items-center gap-2 px-5 py-2 rounded-full text-xl font-black bg-amber-500/15 text-amber-300 border-2 border-amber-500/40 mb-3">
            ⏸ SIN SEÑAL
          </span>
          <p className="text-2xl font-bold text-amber-300/80 mt-2">Monitoreando mercado</p>
          <div className="mt-3 space-y-1.5">
            {reasons.map(({ symbol, reason }) => (
              <p key={symbol} className="text-base text-amber-200/60 leading-snug">
                <span className="text-amber-300/90 font-semibold">{symbol}:</span> {reason}
              </p>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Bullish Modal ─────────────────────────────────────────────────────────────

interface BullishResult {
  status: string;
  symbol: string;
  direction: string;
  entry_price: number;
  quantity: number;
  capital_used: number;
  leverage: number;
  stop_loss: number;
  take_profit: number;
  dry_run: boolean;
}

function BullishModal({ availableCapital, onClose, initialSymbol = "" }: { availableCapital: number; onClose: () => void; initialSymbol?: string }) {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [pct, setPct] = useState(10);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BullishResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const capitalToUse = (availableCapital * pct) / 100;

  async function handleSubmit() {
    const sym = symbol.trim();
    if (!sym) { setError("Ingresá el símbolo (ej: DOGE, PEPE)"); return; }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/bullish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: sym, pct: pct / 100 }),
      });
      const data = await res.json();
      if (!res.ok) setError(data.detail ?? "Error desconocido");
      else setResult(data as BullishResult);
    } catch { setError("No se pudo conectar con el servidor"); }
    finally { setLoading(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-green-500/30 bg-[var(--card)] shadow-2xl shadow-green-500/10 p-6 space-y-5" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-green-400">🐂 MODO BULLISH</h2>
            <p className="text-xs text-[var(--muted)] mt-0.5">Compra manual de meme coin en futuros</p>
          </div>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--text)] p-1 rounded-lg hover:bg-white/5 transition-colors">✕</button>
        </div>

        {result ? (
          <div className="space-y-4">
            <div className="rounded-xl bg-green-500/10 border border-green-500/30 p-4 space-y-3">
              <div className="flex items-center gap-2 text-green-400 font-bold">✓ Orden {result.dry_run ? "simulada" : "ejecutada"}</div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-[var(--muted)]">Par: </span><span className="font-mono font-semibold">{result.symbol}</span></div>
                <div><span className="text-[var(--muted)]">Precio: </span><span className="font-mono">${result.entry_price.toLocaleString()}</span></div>
                <div><span className="text-[var(--muted)]">Cantidad: </span><span className="font-mono">{result.quantity}</span></div>
                <div><span className="text-[var(--muted)]">Capital: </span><span className="font-mono">{result.capital_used.toFixed(2)} USDT</span></div>
                <div><span className="text-[var(--muted)]">SL: </span><span className="font-mono text-red-400">${result.stop_loss.toLocaleString()}</span></div>
                <div><span className="text-[var(--muted)]">TP: </span><span className="font-mono text-green-400">${result.take_profit.toLocaleString()}</span></div>
              </div>
            </div>
            <button onClick={onClose} className="w-full py-2.5 rounded-xl bg-green-600 hover:bg-green-500 text-white font-semibold transition-colors">Cerrar</button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg bg-white/5 border border-[var(--border)] p-3 flex justify-between text-sm">
              <span className="text-[var(--muted)]">Capital disponible</span>
              <span className="font-mono font-semibold">{availableCapital.toFixed(2)} USDT</span>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted)] uppercase tracking-wider">Moneda (sin USDT)</label>
              <input
                type="text"
                value={symbol}
                onChange={e => setSymbol(e.target.value.toUpperCase())}
                placeholder="ej: DOGE, PEPE, SHIB, WIF"
                className="w-full px-3 py-2.5 rounded-xl bg-white/5 border border-[var(--border)] text-[var(--text)] placeholder-[var(--muted)] focus:outline-none focus:border-green-500/50 transition-all font-mono"
                onKeyDown={e => e.key === "Enter" && handleSubmit()}
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-[var(--muted)] uppercase tracking-wider">Porcentaje del capital</label>
                <span className="text-sm font-bold text-green-400">{pct}%</span>
              </div>
              <input type="range" min={1} max={50} value={pct} onChange={e => setPct(Number(e.target.value))} title="Porcentaje del capital a invertir" aria-label="Porcentaje del capital" className="w-full h-2 rounded-full appearance-none bg-slate-700 cursor-pointer accent-green-500" />
              <div className="flex justify-between text-xs text-[var(--muted)]">
                <span>1%</span>
                <span className="font-mono font-semibold text-green-400">{capitalToUse.toFixed(2)} USDT</span>
                <span>50%</span>
              </div>
            </div>
            <div className="flex gap-2">
              {[5, 10, 20, 50].map(v => (
                <button key={v} onClick={() => setPct(v)} className={`flex-1 py-1.5 rounded-lg text-xs font-semibold border transition-all ${pct === v ? "bg-green-500/20 border-green-500/50 text-green-400" : "bg-white/5 border-[var(--border)] text-[var(--muted)] hover:border-green-500/30"}`}>{v}%</button>
              ))}
            </div>
            {error && <div className="rounded-lg bg-red-500/10 border border-red-500/30 p-3 text-sm text-red-300">⚠ {error}</div>}
            <button onClick={handleSubmit} disabled={loading || !symbol.trim()} className="w-full py-3 rounded-xl bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold transition-all active:scale-95">
              {loading ? "Analizando y comprando..." : `🐂 Comprar ${symbol || "?"} USDT`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Bombarda Confirm ──────────────────────────────────────────────────────────

interface BombardaResult {
  status: string;
  closed: { symbol: string; direction: string; entry_price: number; exit_price: number; pnl: number; pnl_pct: number }[];
  errors: { symbol: string; error: string }[];
  dry_run: boolean;
  message: string;
}

function BombardaConfirm({ posCount, onClose, onConfirm, loading, result }: {
  posCount: number; onClose: () => void; onConfirm: () => void; loading: boolean; result: BombardaResult | null;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4" onClick={!loading ? onClose : undefined}>
      <div className="w-full max-w-md rounded-2xl border border-red-500/50 bg-[var(--card)] shadow-2xl shadow-red-500/20 p-6 space-y-5" onClick={e => e.stopPropagation()}>
        {result ? (
          <div className="space-y-4">
            <div className="text-center">
              <div className="text-4xl mb-2">💣</div>
              <h2 className="text-xl font-bold text-red-400">¡Bombarda ejecutada!</h2>
              <p className="text-sm text-[var(--muted)] mt-1">{result.message}</p>
            </div>
            {result.closed.length > 0 && (
              <div className="space-y-2">
                {result.closed.map((c, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg bg-white/5 border border-[var(--border)] p-3 text-sm">
                    <div><span className="font-semibold">{c.symbol}</span><span className="text-xs text-[var(--muted)] ml-2">{c.direction}</span></div>
                    <span className={`font-mono font-semibold ${c.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>{c.pnl >= 0 ? "+" : ""}{c.pnl.toFixed(4)} USDT</span>
                  </div>
                ))}
              </div>
            )}
            {result.errors.length > 0 && (
              <div className="rounded-lg bg-red-500/10 border border-red-500/30 p-3 text-xs text-red-300 space-y-1">
                {result.errors.map((e, i) => <div key={i}>⚠ {e.symbol}: {e.error}</div>)}
              </div>
            )}
            <button onClick={onClose} className="w-full py-2.5 rounded-xl bg-slate-700 hover:bg-slate-600 text-white font-semibold transition-colors">Cerrar</button>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="text-center">
              <div className="text-5xl mb-3 animate-bounce">💣</div>
              <h2 className="text-2xl font-black text-red-400 tracking-tight">LA BOMBARDA</h2>
              <p className="text-sm text-[var(--muted)] mt-2">Cerrará <strong className="text-red-300">{posCount} posición{posCount !== 1 ? "es" : ""}</strong> a precio de mercado de forma inmediata.</p>
              <p className="text-xs text-red-400/60 mt-1">Esta acción no se puede deshacer.</p>
            </div>
            <div className="flex gap-3">
              <button onClick={onClose} disabled={loading} className="flex-1 py-3 rounded-xl bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white font-semibold transition-colors">Cancelar</button>
              <button onClick={onConfirm} disabled={loading} className="flex-1 py-3 rounded-xl bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white font-black text-base transition-all active:scale-95 shadow-lg shadow-red-500/30">
                {loading ? "Cerrando..." : "¡EJECUTAR!"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Tincho2 Chat ──────────────────────────────────────────────────────────────

interface T2Message {
  role: "user" | "assistant" | "system";
  content: string;
  bullishSymbol?: string;
  paramsApplied?: Record<string, unknown>;
}

const PARAM_LABELS: Record<string, string> = {
  leverage: "Leverage",
  stop_loss: "Stop Loss",
  take_profit: "Take Profit",
  max_capital_per_trade: "Capital por trade",
  risk_per_trade: "Riesgo por trade",
  timeframe: "Timeframe",
};

function formatParamValue(key: string, val: unknown): string {
  if (key === "leverage") return `${val}x`;
  if (key === "timeframe") return String(val);
  if (typeof val === "number") return `${(val * 100).toFixed(1)}%`;
  return String(val);
}

const QUICK_QUESTIONS = [
  "¿Cómo van las inversiones?",
  "¿Qué moneda me recomendás?",
  "¿Es buen momento para comprar?",
  "¿Cómo está el riesgo actual?",
];

// Extrae símbolo de etiqueta [BULLISH:XXX] si existe en el texto
function extractBullishTag(text: string): string | null {
  const m = text.match(/\[BULLISH:([A-Z0-9]+)\]/);
  return m ? m[1] : null;
}

// Limpia la etiqueta del texto visible
function cleanBullishTag(text: string): string {
  return text.replace(/\s*\[BULLISH:[A-Z0-9]+\]/g, "").trim();
}

function Tincho2Chat({
  agentStatus,
  isOpen,
  onToggle,
  onBullishRecommend,
}: {
  agentStatus: AgentStatus | null;
  isOpen: boolean;
  onToggle: () => void;
  onBullishRecommend: (symbol: string) => void;
}) {
  const [history, setHistory] = useState<T2Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Scroll al último mensaje
  useEffect(() => {
    if (isOpen) messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, isOpen, loading]);

  // Focus input al abrir
  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 100);
  }, [isOpen]);

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return;
    const userMsg: T2Message = { role: "user", content: text.trim() };
    const newHistory = [...history, userMsg];
    setHistory(newHistory);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMsg.content,
          history: history.map(m => ({ role: m.role, content: m.content })),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setHistory(h => [...h, { role: "assistant", content: `❌ Error: ${data.detail ?? "no response"}` }]);
      } else {
        const reply: string = data.reply;
        const bullishSym = extractBullishTag(reply);
        const cleanReply = cleanBullishTag(reply);
        const paramsApplied = data.paramsApplied ?? undefined;
        setHistory(h => [...h, { role: "assistant", content: cleanReply, bullishSymbol: bullishSym ?? undefined, paramsApplied } as T2Message]);
      }
    } catch {
      setHistory(h => [...h, { role: "assistant", content: "❌ No pude conectarme con el servidor. ¿Está corriendo el bot?" }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {/* Floating toggle button */}
      <button
        onClick={onToggle}
        title="Hablar con Tincho2"
        className="fixed bottom-48 right-4 z-40 w-14 h-14 rounded-full shadow-xl transition-all duration-150 active:scale-95 flex items-center justify-center text-2xl relative"
        style={{
          background: isOpen
            ? "radial-gradient(circle at 35% 35%, #c084fc, #9333ea 60%, #581c87)"
            : "radial-gradient(circle at 35% 35%, #a78bfa, #7c3aed 60%, #3b0764)",
          boxShadow: "0 6px 0 #3b0764, 0 10px 20px rgba(124,58,237,0.5), inset 0 2px 4px rgba(255,255,255,0.2)",
        } as React.CSSProperties}
      >
        {isOpen ? "✕" : "🤖"}
        {!isOpen && history.length === 0 && (
          <span className="absolute top-0.5 right-0.5 w-3 h-3 rounded-full bg-purple-300 border-2 border-[var(--bg)] animate-ping" />
        )}
      </button>

      {/* Chat panel */}
      {isOpen && (
        <div className="fixed bottom-[13rem] right-4 z-40 w-[22rem] max-h-[520px] rounded-2xl border border-purple-500/30 bg-[var(--card)] shadow-2xl shadow-purple-500/20 flex flex-col overflow-hidden">

          {/* Header */}
          <div className="px-4 py-3 border-b border-[var(--border)] bg-purple-500/8 flex items-center gap-3 flex-shrink-0">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-purple-500 to-violet-700 flex items-center justify-center text-lg flex-shrink-0 select-none shadow-md">🤖</div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-purple-200">Tincho2</div>
              <div className="text-[10px] text-purple-300/60">
                {agentStatus ? `Ciclo #${agentStatus.cycle} · ${agentStatus.dry_run ? "DRY-RUN" : "LIVE"}` : "Asesor IA"}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {history.length > 0 && (
                <button
                  onClick={() => setHistory([])}
                  title="Limpiar chat"
                  className="text-[10px] text-purple-400/60 hover:text-purple-300 px-1.5 py-0.5 rounded hover:bg-purple-500/10 transition-colors"
                >
                  limpiar
                </button>
              )}
              <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />
            </div>
          </div>

          {/* Messages area */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">

            {/* Mensaje de bienvenida */}
            {history.length === 0 && (
              <div className="space-y-3">
                <div className="flex gap-2 items-start">
                  <div className="w-7 h-7 rounded-full bg-purple-600/30 flex items-center justify-center text-sm flex-shrink-0 mt-0.5">🤖</div>
                  <div className="rounded-2xl rounded-tl-none px-3 py-2.5 text-xs bg-purple-500/10 border border-purple-500/20 flex-1 text-[var(--text)] leading-relaxed">
                    ¡Hola! Soy Tincho2, tu asesor de trading. Tengo acceso al estado actual del bot y el mercado en tiempo real. ¿En qué te puedo ayudar?
                  </div>
                </div>
                {/* Quick questions */}
                <div className="pl-9 flex flex-wrap gap-1.5">
                  {QUICK_QUESTIONS.map(q => (
                    <button
                      key={q}
                      onClick={() => sendMessage(q)}
                      className="text-[10px] px-2 py-1 rounded-full border border-purple-500/30 text-purple-300/80 hover:bg-purple-500/15 hover:text-purple-200 hover:border-purple-400/50 transition-all"
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
                {msg.role === "assistant" && (
                  <div className="w-7 h-7 rounded-full bg-purple-600/30 flex items-center justify-center text-sm flex-shrink-0 mt-0.5">🤖</div>
                )}
                <div className={`flex flex-col gap-2 max-w-[82%] ${msg.role === "user" ? "items-end ml-auto" : "items-start"}`}>
                  <div
                    className={`rounded-2xl px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap ${
                      msg.role === "user"
                        ? "rounded-tr-none bg-purple-600/25 border border-purple-500/30 text-purple-100"
                        : "rounded-tl-none bg-[var(--bg)] border border-[var(--border)] text-[var(--text)]"
                    }`}
                  >
                    {msg.content}
                  </div>
                  {msg.bullishSymbol && (
                    <button
                      onClick={() => { onBullishRecommend(msg.bullishSymbol!); }}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-green-500/15 border border-green-500/40 text-green-300 text-[11px] font-bold hover:bg-green-500/25 hover:border-green-400/60 transition-all active:scale-95"
                    >
                      🐂 Comprar {msg.bullishSymbol} con BULLISH
                    </button>
                  )}
                  {msg.paramsApplied && (
                    <div className="rounded-xl bg-orange-500/10 border border-orange-500/30 px-3 py-2.5 space-y-1.5">
                      <div className="text-[10px] font-bold text-orange-300 flex items-center gap-1">⚙️ Parámetros actualizados</div>
                      {Object.entries(msg.paramsApplied).map(([k, v]) => (
                        <div key={k} className="flex justify-between text-[10px]">
                          <span className="text-orange-300/70">{PARAM_LABELS[k] ?? k}</span>
                          <span className="font-mono font-semibold text-orange-200">{formatParamValue(k, v)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Typing indicator */}
            {loading && (
              <div className="flex gap-2 items-start">
                <div className="w-7 h-7 rounded-full bg-purple-600/30 flex items-center justify-center text-sm flex-shrink-0 mt-0.5">🤖</div>
                <div className="rounded-2xl rounded-tl-none px-3 py-2.5 bg-[var(--bg)] border border-[var(--border)] flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "0ms" } as React.CSSProperties} />
                  <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "150ms" } as React.CSSProperties} />
                  <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: "300ms" } as React.CSSProperties} />
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
                placeholder="Preguntale algo a Tincho2..."
                disabled={loading}
                className="flex-1 px-3 py-2 rounded-xl bg-white/5 border border-[var(--border)] text-xs text-[var(--text)] placeholder-[var(--muted)] focus:outline-none focus:border-purple-500/50 disabled:opacity-50 transition-all"
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="w-8 h-8 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-all active:scale-95 flex-shrink-0 text-white text-sm"
              >
                ↑
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [portfolio, setPortfolio]   = useState<{ portfolio: Portfolio } | null>(null);
  const [market, setMarket]         = useState<{ market_snapshots: Record<string, MarketSnapshot>; signals: Record<string, Signal> } | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [trades, setTrades]         = useState<Trade[]>([]);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [online, setOnline]         = useState(true);
  const [showBullish, setShowBullish] = useState(false);
  const [bullishPrefill, setBullishPrefill] = useState("");
  const [showBombarda, setShowBombarda] = useState(false);
  const [bombarding, setBombarding] = useState(false);
  const [bombardaResult, setBombardaResult] = useState<BombardaResult | null>(null);
  const [showAiChat, setShowAiChat] = useState(false);
  const [showMarquitos, setShowMarquitos] = useState(false);
  const [marquitosActive, setMarquitosActive] = useState(false);
  const [marquitosState, setMarquitosState] = useState<{
    capital: number; initial_capital: number; total_pnl: number;
    trades_won: number; trades_total: number;
    awaiting_capital?: boolean;
    last_ai_decision?: string;
    position: {
      symbol: string;
      entry_price: number;
      current_price: number;
      take_profit_price: number;
      stop_loss_price: number;
      quantity: number;
      open_time: number;
      pnl: number;
      pnl_pct: number;
      change_pct_24h: number;
      category: string;
      capital_used: number;
    } | null;
  } | null>(null);
  const [params, setParams] = useState<any | null>(null);

  const refresh = useCallback(async () => {
    const [p, m, a, t] = await Promise.all([
      apiFetch<{ portfolio: Portfolio }>("/portfolio"),
      apiFetch<{ market_snapshots: Record<string, MarketSnapshot>; signals: Record<string, Signal> }>("/market-analysis"),
      apiFetch<AgentStatus>("/agent/status"),
      apiFetch<{ trades: Trade[] }>("/trades?limit=15"),
    ]);

    setOnline(!!(p || m || a));
    if (p) setPortfolio(p);
    if (m) setMarket(m);
    if (a) setAgentStatus(a);
    if (t) setTrades(t.trades ?? []);
    setLastUpdate(new Date());
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    // Fetch parámetros actuales
    const fetchParams = async () => {
      try {
        const res = await fetch("/api/parameters");
        if (res.ok) setParams(await res.json());
      } catch {}
    };
    fetchParams();
    const pid = setInterval(fetchParams, 7000);
    return () => { clearInterval(id); clearInterval(pid); };
  }, [refresh]);

  const port = portfolio?.portfolio;
  const snapshots = market?.market_snapshots ?? {};
  const signals = market?.signals ?? {};

  const isTrading = !!(port && port.open_positions > 0);
  const allNoSignal =
    !isTrading &&
    Object.keys(signals).length > 0 &&
    Object.values(signals).every(s => s.signal === "NO_SIGNAL");
  const noSignalReasons = Object.entries(signals)
    .filter(([, s]) => s.signal === "NO_SIGNAL")
    .map(([symbol, s]) => ({ symbol, reason: s.reason }));

  async function handleBombarda() {
    setBombarding(true);
    try {
      const res = await fetch("/api/bombarda", { method: "POST" });
      const data = await res.json();
      setBombardaResult(data as BombardaResult);
    } catch {
      setBombardaResult({ status: "error", closed: [], errors: [{ symbol: "–", error: "No se pudo conectar" }], dry_run: true, message: "Error de conexión" });
    } finally {
      setBombarding(false);
    }
  }

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch("/api/marquitos/status");
        if (res.ok) {
          const data = await res.json();
          setMarquitosActive(!!data.active);
        }
      } catch {}
    };
    fetchStatus();
    const id = setInterval(fetchStatus, 4000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!marquitosActive) { setMarquitosState(null); return; }
    const fetchMarqState = async () => {
      try {
        const res = await fetch("/api/marquitos/state");
        if (res.ok) setMarquitosState(await res.json());
      } catch {}
    };
    fetchMarqState();
    const id = setInterval(fetchMarqState, 3000);
    return () => clearInterval(id);
  }, [marquitosActive]);

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      {/* Header */}
      <header className="border-b border-[var(--border)] px-6 py-4 flex items-center justify-between sticky top-0 z-10 bg-[var(--bg)]/90 backdrop-blur-sm w-full">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-bold text-base select-none">T</div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Tincho Bot</h1>
            <p className="text-xs text-[var(--muted)]">Autonomous Trading Agent</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {agentStatus && (
            <>
              <StatusBadge status={agentStatus.status} />
              <span className="text-xs text-[var(--muted)]">
                {agentStatus.dry_run ? "DRY-RUN" : "LIVE"} · Ciclo #{agentStatus.cycle}
              </span>
            </>
          )}
          {lastUpdate && (
            <span className="text-[11px] text-[var(--muted)] hidden sm:inline">
              actualizado {lastUpdate.toLocaleTimeString("es-AR")}
            </span>
          )}
          <div className={`w-2 h-2 rounded-full ${online ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
        </div>
      </header>

      {/* Parámetros actuales de trading */}
      {params && (
        <div className="w-full px-4 sm:px-6 lg:px-10 xl:px-16 pt-3 pb-1">
          <div className="text-xs text-orange-300 font-mono bg-orange-900/10 border border-orange-500/20 rounded-lg px-4 py-2 mb-2">
            <b>Parámetros actuales:</b> &nbsp;
            leverage: <span className="font-bold">{params.leverage}x</span> &nbsp;|
            max_capital: <span className="font-bold">{(params.max_capital_per_trade * 100).toFixed(1)}%</span> &nbsp;|
            stop_loss: <span className="font-bold">{(params.stop_loss * 100).toFixed(2)}%</span> &nbsp;|
            take_profit: <span className="font-bold">{(params.take_profit * 100).toFixed(2)}%</span> &nbsp;|
            riesgo: <span className="font-bold">{(params.risk_per_trade * 100).toFixed(2)}%</span> &nbsp;|
            timeframe: <span className="font-bold">{params.timeframe}</span> &nbsp;|
            intervalo: <span className="font-bold">{params.analysis_interval_seconds}s</span>
          </div>
        </div>
      )}

      {/* Main content — extra bottom padding for fixed action bar */}
      <main className="w-full px-4 sm:px-6 lg:px-10 xl:px-16 py-6 space-y-6 pb-28">

        {!online && <OfflineBanner />}
        {!!agentStatus?.recovered_positions?.length && (
          <RecoveredPositionsBanner positions={agentStatus.recovered_positions} />
        )}

        {/* ── Marquitos Status + Posición activa ── */}
        {marquitosActive && (
          <div className="space-y-3">
            {/* Status bar */}
            <div className="rounded-2xl border border-red-500/50 bg-red-950/30 px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-3 shadow-lg shadow-red-500/10">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <span className="text-2xl select-none">🔥</span>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-red-300">Marquitos activo</span>
                    <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse inline-block" />
                  </div>
                  {marquitosState?.awaiting_capital && (
                    <div className="text-xs text-orange-300 mt-0.5">⏳ Esperando capital — decile cuánto en el chat</div>
                  )}
                  {marquitosState && !marquitosState.awaiting_capital && !marquitosState.position && (
                    <div className="text-xs text-red-300/70 mt-0.5">🔍 Escaneando mercado...</div>
                  )}
                  {marquitosState?.position && (
                    <div className="text-xs text-orange-200 mt-0.5 font-mono">
                      📈 <span className="font-bold text-orange-300">{marquitosState.position.symbol}</span>
                      {" "}→ TP: +0.8% | SL: -0.3%
                    </div>
                  )}
                </div>
              </div>
              {marquitosState && (
                <div className="flex gap-4 text-xs font-mono text-red-300/80 flex-wrap">
                  <span>Capital: <span className="text-red-200 font-bold">{marquitosState.capital.toFixed(2)} USDT</span></span>
                  <span>PnL: <span className={marquitosState.total_pnl >= 0 ? "text-green-400 font-bold" : "text-red-400 font-bold"}>{marquitosState.total_pnl >= 0 ? "+" : ""}{marquitosState.total_pnl.toFixed(4)} USDT</span></span>
                  <span>Trades: <span className="text-red-200">{marquitosState.trades_won}/{marquitosState.trades_total}</span></span>
                </div>
              )}
            </div>

            {/* Tarjeta de posición activa */}
            {marquitosState?.position && (() => {
              const p = marquitosState.position;
              const pnl = p.pnl ?? 0;
              const pnlPct = p.pnl_pct ?? 0;
              const pnlColor = pnl > 0 ? "text-green-400" : pnl < 0 ? "text-red-400" : "text-slate-400";
              const pnlBg = pnl > 0 ? "bg-green-500/8 border-green-500/25" : pnl < 0 ? "bg-red-500/8 border-red-500/25" : "bg-white/5 border-[var(--border)]";
              const currentPrice = p.current_price ?? p.entry_price;
              const range = p.take_profit_price - p.entry_price;
              const progress = range > 0
                ? Math.max(0, Math.min(100, (currentPrice - p.entry_price) / range * 100))
                : 0;
              const holdSecs = Math.floor((Date.now() / 1000) - p.open_time);
              return (
                <div className="rounded-xl border-2 border-red-500/40 bg-red-950/20 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">🔥</span>
                      <span className="font-bold text-base text-red-200">{p.symbol.replace("USDT", "")}</span>
                      <span className="text-[10px] text-[var(--muted)] font-mono">USDT</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-orange-500/20 text-orange-300 border border-orange-500/30">
                        {p.category === "meme" ? "🎰 MEME" : "ALTCOIN"}
                      </span>
                      <span className="text-[10px] text-[var(--muted)]">+{(p.change_pct_24h ?? 0).toFixed(1)}% 24h</span>
                    </div>
                    <span className="px-2 py-0.5 rounded text-xs font-bold bg-green-500/20 text-green-400 border border-green-500/30">LONG ×40</span>
                  </div>

                  {/* PnL grande */}
                  <div className={`rounded-lg px-3 py-2.5 text-center ${pnl > 0 ? "bg-green-500/12" : pnl < 0 ? "bg-red-500/12" : "bg-white/5"}`}>
                    <div className={`text-2xl font-black font-mono ${pnlColor}`}>
                      {pnl >= 0 ? "+" : ""}{pnl.toFixed(6)}
                      <span className="text-xs font-semibold ml-1">USDT</span>
                    </div>
                    <div className={`text-sm font-semibold ${pnlColor} mt-0.5`}>
                      {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(3)}% desde entrada
                    </div>
                  </div>

                  {/* Precios */}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <div className="text-[var(--muted)] mb-0.5">Precio actual</div>
                      <div className="font-mono font-semibold text-sm">{currentPrice.toFixed(8)}</div>
                    </div>
                    <div>
                      <div className="text-[var(--muted)] mb-0.5">Entrada</div>
                      <div className="font-mono font-semibold text-sm">{p.entry_price.toFixed(8)}</div>
                      <div className="text-[10px] text-[var(--muted)]">{p.quantity} unidades</div>
                    </div>
                  </div>

                  {/* Barra de progreso hacia TP */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-[10px] text-[var(--muted)]">
                      <span>SL <span className="font-mono text-red-400">{p.stop_loss_price.toFixed(8)}</span></span>
                      <span className={`text-[10px] font-semibold ${progress > 50 ? "text-green-400" : "text-slate-400"}`}>{progress.toFixed(0)}% → TP</span>
                      <span>TP <span className="font-mono text-green-400">{p.take_profit_price.toFixed(8)}</span></span>
                    </div>
                    <div className="h-2 bg-slate-700/60 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${progress > 75 ? "bg-green-400" : progress > 40 ? "bg-yellow-400" : "bg-red-400"}`}
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                  </div>

                  <div className="flex justify-between text-[10px] text-[var(--muted)] border-t border-[var(--border)] pt-2">
                    <span>Capital invertido: <span className="font-mono font-semibold text-[var(--text)]">{(p.capital_used ?? 0).toFixed(2)} USDT</span></span>
                    <span>Tiempo: <span className="font-mono">{holdSecs < 60 ? `${holdSecs}s` : `${Math.floor(holdSecs/60)}m ${holdSecs%60}s`}</span></span>
                  </div>
                </div>
              );
            })()}
          </div>
        )}

        {/* ── Alert zone ── */}
        {isTrading && port && (
          <TradingAlert count={port.open_positions} positions={port.positions} />
        )}
        {allNoSignal && (
          <NoSignalAlert reasons={noSignalReasons} />
        )}

        {/* Portfolio Stats */}
        {port && (() => {
          const totalUnrealized = Object.values(port.positions).reduce((sum, pos) => sum + (pos.unrealized_pnl ?? 0), 0);
          const combinedPnl = port.total_pnl + totalUnrealized;
          const hasOpenPositions = port.open_positions > 0;

          // Win Rate en tiempo real: cerrados ganadores + abiertas en ganancia / total
          const openWinning = Object.values(port.positions).filter(pos => (pos.unrealized_pnl ?? 0) > 0).length;
          const liveWinning = port.winning_trades + openWinning;
          const liveTotal = port.total_trades + port.open_positions;
          const liveWinRate = liveTotal > 0 ? liveWinning / liveTotal : 0;

          return (
          <Card title="Portafolio">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-6 lg:gap-8">
              <Stat
                label="Capital"
                value={<span className="font-mono">{port.capital.toFixed(2)} USDT</span>}
                sub={`Inicial: ${port.initial_capital.toFixed(2)}`}
              />
              <Stat
                label="Disponible"
                value={<span className="font-mono">{port.available_capital.toFixed(2)} USDT</span>}
              />
              <Stat
                label="PnL Total"
                value={<PnlValue value={combinedPnl} />}
                sub={hasOpenPositions
                  ? `Realiz: ${port.total_pnl >= 0 ? "+" : ""}${port.total_pnl.toFixed(4)} | Abierto: ${totalUnrealized >= 0 ? "+" : ""}${totalUnrealized.toFixed(4)}`
                  : undefined}
              />
              <Stat
                label="Win Rate"
                value={
                  <span className={liveWinRate >= 0.5 ? "text-green-400" : liveWinRate > 0 ? "text-yellow-400" : "text-red-400"}>
                    {(liveWinRate * 100).toFixed(1)}%
                  </span>
                }
                sub={
                  hasOpenPositions
                    ? `${liveWinning}/${liveTotal} · ${openWinning} abierta${openWinning !== 1 ? "s" : ""} ganando`
                    : `${port.winning_trades}/${port.total_trades} cerrados`
                }
              />
              <Stat label="Posiciones" value={port.open_positions} />
              <Stat label="Total trades" value={port.total_trades} />
            </div>
          </Card>
          );
        })()}

        {/* Open Positions */}
        {port && port.open_positions > 0 && (
          <Card title="Portfolio — Posiciones abiertas">
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              {Object.entries(port.positions).map(([sym, pos]) => {
                const pnl = pos.unrealized_pnl ?? 0;
                const pnlPct = pos.unrealized_pnl_pct ?? 0;
                const currentPrice = pos.current_price ?? pos.entry_price;
                const isProfit = pnl >= 0;
                const pnlColor = pnl > 0 ? "text-green-400" : pnl < 0 ? "text-red-400" : "text-slate-400";
                const pnlBg = pnl > 0 ? "bg-green-500/8 border-green-500/25" : pnl < 0 ? "bg-red-500/8 border-red-500/25" : "bg-white/5 border-[var(--border)]";
                const priceDiff = currentPrice - pos.entry_price;
                // Progreso hacia TP o SL
                const range = pos.direction === "LONG"
                  ? pos.take_profit - pos.entry_price
                  : pos.entry_price - pos.take_profit;
                const progress = pos.direction === "LONG"
                  ? Math.max(0, Math.min(100, (currentPrice - pos.entry_price) / (range || 1) * 100))
                  : Math.max(0, Math.min(100, (pos.entry_price - currentPrice) / (range || 1) * 100));
                return (
                  <div key={sym} className={`rounded-xl border ${pnlBg} p-4 space-y-3`}>
                    {/* Header */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-base">{sym.replace("USDT", "")}</span>
                        <span className="text-[10px] text-[var(--muted)] font-mono">USDT</span>
                      </div>
                      <SignalBadge signal={pos.direction} />
                    </div>

                    {/* P&L grande */}
                    <div className={`rounded-lg px-3 py-2.5 text-center ${pnl > 0 ? "bg-green-500/12" : pnl < 0 ? "bg-red-500/12" : "bg-white/5"}`}>
                      <div className={`text-2xl font-black font-mono ${pnlColor}`}>
                        {pnl >= 0 ? "+" : ""}{pnl.toFixed(4)}
                        <span className="text-xs font-semibold ml-1">USDT</span>
                      </div>
                      <div className={`text-sm font-semibold ${pnlColor} mt-0.5`}>
                        {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}% desde entrada
                      </div>
                    </div>

                    {/* Precios */}
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <div className="text-[var(--muted)] mb-0.5">Precio actual</div>
                        <div className="font-mono font-semibold text-sm">${currentPrice.toLocaleString(undefined, { maximumFractionDigits: 6 })}</div>
                        <div className={`text-[10px] font-mono ${priceDiff >= 0 ? "text-green-400" : "text-red-400"}`}>
                          {priceDiff >= 0 ? "+" : ""}{priceDiff.toFixed(6)}
                        </div>
                      </div>
                      <div>
                        <div className="text-[var(--muted)] mb-0.5">Precio entrada</div>
                        <div className="font-mono font-semibold text-sm">${pos.entry_price.toLocaleString(undefined, { maximumFractionDigits: 6 })}</div>
                        <div className="text-[10px] text-[var(--muted)]">{pos.quantity} unidades</div>
                      </div>
                    </div>

                    {/* Barra de progreso hacia TP */}
                    <div className="space-y-1">
                      <div className="flex justify-between text-[10px] text-[var(--muted)]">
                        <span>SL <span className="font-mono text-red-400">${pos.stop_loss.toLocaleString(undefined, { maximumFractionDigits: 6 })}</span></span>
                        <span className={`text-[10px] font-semibold ${progress > 50 ? "text-green-400" : "text-slate-400"}`}>{progress.toFixed(0)}% → TP</span>
                        <span>TP <span className="font-mono text-green-400">${pos.take_profit.toLocaleString(undefined, { maximumFractionDigits: 6 })}</span></span>
                      </div>
                      <div className="h-1.5 bg-slate-700/60 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-700 ${progress > 75 ? "bg-green-400" : progress > 40 ? "bg-yellow-400" : "bg-red-400"}`}
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>

                    {/* Capital */}
                    <div className="flex justify-between text-[10px] text-[var(--muted)] border-t border-[var(--border)] pt-2">
                      <span>Capital invertido</span>
                      <span className="font-mono font-semibold text-[var(--text)]">{pos.capital_used.toFixed(2)} USDT</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        )}

        {/* Market Analysis */}
        {Object.keys(snapshots).length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {Object.entries(snapshots).map(([sym, snap]) => {
              const sig = signals[sym];
              return (
                <Card key={sym} title={sym}>
                  <div className="space-y-5">
                    <div className="flex items-center justify-between">
                      <span className="text-3xl lg:text-4xl font-mono font-bold">
                        ${snap.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                      <TrendBadge trend={snap.trend} />
                    </div>
                    <RsiBar rsi={snap.rsi} />
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div><span className="text-[var(--muted)]">SMA20: </span><span className="font-mono font-medium">{snap.sma20.toFixed(2)}</span></div>
                      <div><span className="text-[var(--muted)]">SMA50: </span><span className="font-mono font-medium">{snap.sma50.toFixed(2)}</span></div>
                      <div><span className="text-[var(--muted)]">Volumen: </span><span className="font-medium">{snap.volume_trend}</span></div>
                      <div><span className="text-[var(--muted)]">OI: </span><span className="font-medium">{snap.oi_trend}</span></div>
                      <div className="col-span-2">
                        <span className="text-[var(--muted)]">Funding: </span>
                        <span className={`font-mono font-semibold ${snap.funding_rate > 0 ? "text-green-400" : "text-red-400"}`}>
                          {(snap.funding_rate * 100).toFixed(4)}%
                        </span>
                      </div>
                    </div>
                    {sig && (
                      <div className="pt-3 border-t border-[var(--border)]">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm text-[var(--muted)]">Señal actual</span>
                          <SignalBadge signal={sig.signal} />
                        </div>
                        {sig.signal !== "NO_SIGNAL" && (
                          <div className="text-sm text-[var(--muted)] mt-1 leading-relaxed">
                            <span className="text-[var(--text)] font-medium">{sig.strategy}</span> · confianza {(sig.confidence * 100).toFixed(0)}%
                            <div className="mt-1 opacity-70">{sig.reason}</div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        )}

        {/* Trade History */}
        {trades.length > 0 && (
          <Card title="Últimos trades">
            <div className="overflow-x-auto">
              <table className="w-full text-sm lg:text-base">
                <thead>
                  <tr className="text-left text-xs text-[var(--muted)] border-b border-[var(--border)]">
                    <th className="pb-2 pr-4">Par</th>
                    <th className="pb-2 pr-4">Dir.</th>
                    <th className="pb-2 pr-4">Entrada</th>
                    <th className="pb-2 pr-4">Salida</th>
                    <th className="pb-2 pr-4">PnL</th>
                    <th className="pb-2 pr-4">Estrategia</th>
                    <th className="pb-2">Duración</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t, i) => (
                    <tr key={i} className="border-b border-[var(--border)]/50 hover:bg-white/[0.02]">
                      <td className="py-2 pr-4 font-semibold">{t.symbol}</td>
                      <td className="py-2 pr-4"><SignalBadge signal={t.direction} /></td>
                      <td className="py-2 pr-4 font-mono text-xs">${t.entry_price.toLocaleString()}</td>
                      <td className="py-2 pr-4 font-mono text-xs">${t.exit_price.toLocaleString()}</td>
                      <td className="py-2 pr-4">
                        <div><PnlValue value={t.pnl} /></div>
                        <div className={`text-xs font-mono ${t.pnl_pct >= 0 ? "text-green-400/70" : "text-red-400/70"}`}>
                          {t.pnl_pct >= 0 ? "+" : ""}{t.pnl_pct.toFixed(2)}%
                        </div>
                      </td>
                      <td className="py-2 pr-4 text-xs text-[var(--muted)]">{t.strategy}</td>
                      <td className="py-2 text-xs text-[var(--muted)]">
                        {t.duration_seconds < 60 ? `${t.duration_seconds.toFixed(0)}s` : `${(t.duration_seconds / 60).toFixed(1)}m`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {online && trades.length === 0 && port && port.total_trades === 0 && (
          <div className="text-center py-12 text-[var(--muted)]">
            <div className="text-4xl mb-3">📊</div>
            <div className="text-sm">Sin trades aún. El agente está analizando el mercado...</div>
            <div className="text-xs mt-1 opacity-60">Se ejecutará un trade cuando detecte una señal válida.</div>
          </div>
        )}
      </main>

      {/* ── Fixed action bar ── */}
      <div className="fixed bottom-0 left-0 right-0 z-20 border-t border-[var(--border)] bg-[var(--bg)]/95 backdrop-blur-md px-4 py-5">
        <div className="w-full px-2 sm:px-6 lg:px-10 xl:px-16 flex items-center justify-between gap-6">

          {/* BULLISH — botón circular 3D verde */}
          <button
            onClick={() => setShowBullish(true)}
            className="group flex flex-col items-center justify-center gap-1.5 w-32 h-32 sm:w-36 sm:h-36 rounded-full font-black text-white transition-all duration-150 active:scale-95 active:translate-y-1"
            style={{
              background: "radial-gradient(circle at 35% 35%, #4ade80, #16a34a 60%, #14532d)",
              boxShadow: "0 8px 0 #14532d, 0 12px 24px rgba(22,163,74,0.5), inset 0 2px 4px rgba(255,255,255,0.25)",
            } as React.CSSProperties}
          >
            <span className="text-3xl sm:text-4xl drop-shadow">🐂</span>
            <span className="text-sm sm:text-base tracking-wide drop-shadow-md">BULLISH</span>
          </button>

          {/* Info central */}
          <div className="flex-1 text-center text-sm text-[var(--muted)] hidden sm:block">
            {port ? (
              <>
                <div className="text-base font-semibold text-[var(--text)]">{port.available_capital.toFixed(2)} USDT</div>
                <div className="text-xs mt-0.5">{port.open_positions} posición{port.open_positions !== 1 ? "es" : ""} abiertas</div>
              </>
            ) : (
              <span>Conectando...</span>
            )}
          </div>

          {/* BOMBARDA — botón circular 3D rojo */}
          <button
            onClick={() => { setBombardaResult(null); setShowBombarda(true); }}
            className="group flex flex-col items-center justify-center gap-1.5 w-32 h-32 sm:w-36 sm:h-36 rounded-full font-black text-white transition-all duration-150 active:scale-95 active:translate-y-1"
            style={{
              background: "radial-gradient(circle at 35% 35%, #f87171, #dc2626 60%, #7f1d1d)",
              boxShadow: "0 8px 0 #7f1d1d, 0 12px 24px rgba(220,38,38,0.5), inset 0 2px 4px rgba(255,255,255,0.2)",
            } as React.CSSProperties}
          >
            <span className="text-3xl sm:text-4xl drop-shadow">💣</span>
            <span className="text-xs sm:text-sm tracking-wide drop-shadow-md text-center leading-tight">LA<br/>BOMBARDA</span>
          </button>

        </div>
      </div>

      {/* ── Marquitos Chat ── */}
      <>
        {/* Botón flotante rojo a la izquierda */}
        <button
          onClick={() => setShowMarquitos(v => !v)}
          title="Llamar a Marquitos"
          className="fixed bottom-48 left-4 z-40 w-14 h-14 rounded-full shadow-xl transition-all duration-150 active:scale-95 flex items-center justify-center text-2xl relative"
          style={{
            background: showMarquitos
              ? "radial-gradient(circle at 35% 35%, #f87171, #dc2626 60%, #7f1d1d)"
              : "radial-gradient(circle at 35% 35%, #fca5a5, #ef4444 60%, #7f1d1d)",
            boxShadow: "0 6px 0 #7f1d1d, 0 10px 20px rgba(220,38,38,0.5), inset 0 2px 4px rgba(255,255,255,0.2)",
          } as React.CSSProperties}
        >
          {showMarquitos ? "✕" : "⚡"}
          {!showMarquitos && (
            <span className="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-red-300 border-2 border-[var(--bg)] animate-ping" />
          )}
        </button>
        {/* Ventana MarquitosChat */}
        {showMarquitos && (
          <MarquitosChat isOpen={showMarquitos} onClose={() => setShowMarquitos(false)} />
        )}
      </>

      {/* ── Tincho2 Chat ── */}
      <Tincho2Chat
        agentStatus={agentStatus}
        isOpen={showAiChat}
        onToggle={() => setShowAiChat(v => !v)}
        onBullishRecommend={(sym) => { setBullishPrefill(sym); setShowBullish(true); }}
      />

      {/* ── Modals ── */}
      {showBullish && (
        <BullishModal
          availableCapital={port?.available_capital ?? 0}
          initialSymbol={bullishPrefill}
          onClose={() => { setShowBullish(false); setBullishPrefill(""); }}
        />
      )}
      {showBombarda && (
        <BombardaConfirm
          posCount={port?.open_positions ?? 0}
          onClose={() => setShowBombarda(false)}
          onConfirm={handleBombarda}
          loading={bombarding}
          result={bombardaResult}
        />
      )}
    </div>
  );
}
