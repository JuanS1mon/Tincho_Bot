"use client";

import { useEffect, useState, useCallback } from "react";

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
  quantity: number;
  capital_used: number;
  stop_loss: number;
  take_profit: number;
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

// ── Trading alert ─────────────────────────────────────────────────────────────

function TradingAlert({ count, positions }: { count: number; positions: Record<string, Position> }) {
  const symbols = Object.keys(positions).join(", ");
  return (
    <div className="rounded-xl border border-green-500/40 bg-green-500/10 overflow-hidden">
      <div className="flex items-center gap-4 p-4">
        <div className="flex-shrink-0">
          <img src="/trading.gif" alt="Operando" className="h-16 w-16 rounded-lg object-cover" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-bold bg-green-500/20 text-green-300 border border-green-500/40 animate-pulse">
              🚀 OPERANDO
            </span>
            <span className="text-sm font-semibold text-green-400">
              {count} posición{count !== 1 ? "es" : ""} activa{count !== 1 ? "s" : ""}
            </span>
          </div>
          <p className="text-xs text-green-300/70 truncate font-mono">{symbols}</p>
        </div>
      </div>
    </div>
  );
}

// ── No-signal alert ───────────────────────────────────────────────────────────

function NoSignalAlert({ reasons }: { reasons: { symbol: string; reason: string }[] }) {
  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 overflow-hidden">
      <div className="flex gap-4 p-4">
        <div className="flex-shrink-0">
          <img src="/no-trading.gif" alt="Sin operaciones" className="h-16 w-16 rounded-lg object-cover" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
              ⏸ SIN SEÑAL
            </span>
            <span className="text-xs text-amber-400/60">Monitoreando mercado</span>
          </div>
          <div className="space-y-0.5">
            {reasons.map(({ symbol, reason }) => (
              <p key={symbol} className="text-xs text-amber-200/60 leading-snug">
                <span className="text-amber-300/80 font-medium">{symbol}:</span> {reason}
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

function BullishModal({ availableCapital, onClose }: { availableCapital: number; onClose: () => void }) {
  const [symbol, setSymbol] = useState("");
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

// ── Main Dashboard ────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [portfolio, setPortfolio]   = useState<{ portfolio: Portfolio } | null>(null);
  const [market, setMarket]         = useState<{ market_snapshots: Record<string, MarketSnapshot>; signals: Record<string, Signal> } | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [trades, setTrades]         = useState<Trade[]>([]);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [online, setOnline]         = useState(true);
  const [showBullish, setShowBullish] = useState(false);
  const [showBombarda, setShowBombarda] = useState(false);
  const [bombarding, setBombarding] = useState(false);
  const [bombardaResult, setBombardaResult] = useState<BombardaResult | null>(null);

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
    return () => clearInterval(id);
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

      {/* Main content — extra bottom padding for fixed action bar */}
      <main className="w-full px-4 sm:px-6 lg:px-10 xl:px-16 py-6 space-y-6 pb-28">

        {!online && <OfflineBanner />}

        {/* ── Alert zone ── */}
        {isTrading && port && (
          <TradingAlert count={port.open_positions} positions={port.positions} />
        )}
        {allNoSignal && (
          <NoSignalAlert reasons={noSignalReasons} />
        )}

        {/* Portfolio Stats */}
        {port && (
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
                value={<PnlValue value={port.total_pnl} />}
              />
              <Stat
                label="Win Rate"
                value={
                  <span className={port.win_rate >= 0.5 ? "text-green-400" : "text-red-400"}>
                    {(port.win_rate * 100).toFixed(1)}%
                  </span>
                }
                sub={`${port.winning_trades}/${port.total_trades} trades`}
              />
              <Stat label="Posiciones" value={port.open_positions} />
              <Stat label="Total trades" value={port.total_trades} />
            </div>
          </Card>
        )}

        {/* Open Positions */}
        {port && port.open_positions > 0 && (
          <Card title="Posiciones abiertas">
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              {Object.entries(port.positions).map(([sym, pos]) => (
                <div key={sym} className="rounded-lg border border-[var(--border)] p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{sym}</span>
                    <SignalBadge signal={pos.direction} />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div><span className="text-[var(--muted)]">Entrada: </span><span className="font-mono">${pos.entry_price.toLocaleString()}</span></div>
                    <div><span className="text-[var(--muted)]">Cantidad: </span><span className="font-mono">{pos.quantity}</span></div>
                    <div><span className="text-[var(--muted)]">SL: </span><span className="font-mono text-red-400">${pos.stop_loss.toLocaleString()}</span></div>
                    <div><span className="text-[var(--muted)]">TP: </span><span className="font-mono text-green-400">${pos.take_profit.toLocaleString()}</span></div>
                    <div><span className="text-[var(--muted)]">Capital: </span><span className="font-mono">{pos.capital_used.toFixed(2)} USDT</span></div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Market Analysis */}
        {Object.keys(snapshots).length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
            {Object.entries(snapshots).map(([sym, snap]) => {
              const sig = signals[sym];
              return (
                <Card key={sym} title={sym}>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-2xl lg:text-3xl font-mono font-bold">
                        ${snap.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                      <TrendBadge trend={snap.trend} />
                    </div>
                    <RsiBar rsi={snap.rsi} />
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div><span className="text-[var(--muted)]">SMA20: </span><span className="font-mono">{snap.sma20.toFixed(2)}</span></div>
                      <div><span className="text-[var(--muted)]">SMA50: </span><span className="font-mono">{snap.sma50.toFixed(2)}</span></div>
                      <div><span className="text-[var(--muted)]">Volumen: </span><span>{snap.volume_trend}</span></div>
                      <div><span className="text-[var(--muted)]">OI: </span><span>{snap.oi_trend}</span></div>
                      <div className="col-span-2">
                        <span className="text-[var(--muted)]">Funding: </span>
                        <span className={`font-mono ${snap.funding_rate > 0 ? "text-green-400" : "text-red-400"}`}>
                          {(snap.funding_rate * 100).toFixed(4)}%
                        </span>
                      </div>
                    </div>
                    {sig && (
                      <div className="pt-2 border-t border-[var(--border)]">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-[var(--muted)]">Señal actual</span>
                          <SignalBadge signal={sig.signal} />
                        </div>
                        {sig.signal !== "NO_SIGNAL" && (
                          <div className="text-xs text-[var(--muted)] mt-1 leading-relaxed">
                            <span className="text-[var(--text)]">{sig.strategy}</span> · confianza {(sig.confidence * 100).toFixed(0)}%
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
      <div className="fixed bottom-0 left-0 right-0 z-20 border-t border-[var(--border)] bg-[var(--bg)]/95 backdrop-blur-md px-4 py-3">
        <div className="w-full px-2 sm:px-6 lg:px-10 xl:px-16 flex items-center gap-3">
          {/* BULLISH */}
          <button
            onClick={() => setShowBullish(true)}
            className="flex-1 sm:flex-none sm:w-48 flex items-center justify-center gap-2 py-3 px-5 rounded-xl bg-green-600/20 hover:bg-green-600/35 border border-green-500/40 text-green-400 font-bold text-sm transition-all hover:scale-[1.02] active:scale-95"
          >
            🐂 <span>BULLISH</span>
          </button>

          <div className="flex-1 text-center text-xs text-[var(--muted)] hidden sm:block">
            {port ? (
              <span>{port.available_capital.toFixed(2)} USDT disponibles · {port.open_positions} posición{port.open_positions !== 1 ? "es" : ""}</span>
            ) : (
              <span>Conectando...</span>
            )}
          </div>

          {/* BOMBARDA */}
          <button
            onClick={() => { setBombardaResult(null); setShowBombarda(true); }}
            className="flex-1 sm:flex-none sm:w-48 flex items-center justify-center gap-2 py-3 px-5 rounded-xl bg-red-600/20 hover:bg-red-600/35 border border-red-500/50 text-red-400 font-black text-sm transition-all hover:scale-[1.02] active:scale-95 shadow-lg shadow-red-500/10"
          >
            💣 <span>LA BOMBARDA</span>
          </button>
        </div>
      </div>

      {/* ── Modals ── */}
      {showBullish && (
        <BullishModal
          availableCapital={port?.available_capital ?? 0}
          onClose={() => setShowBullish(false)}
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
