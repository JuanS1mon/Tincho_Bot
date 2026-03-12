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
    <div className={`rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 ${className}`}>
      <h2 className="text-xs font-semibold uppercase tracking-widest text-[var(--muted)] mb-4">{title}</h2>
      {children}
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div>
      <div className="text-xs text-[var(--muted)] mb-0.5">{label}</div>
      <div className="text-lg font-semibold leading-tight">{value}</div>
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
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${rsi}%` }} />
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

// ── Main Dashboard ────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [portfolio, setPortfolio]   = useState<{ portfolio: Portfolio } | null>(null);
  const [market, setMarket]         = useState<{ market_snapshots: Record<string, MarketSnapshot>; signals: Record<string, Signal> } | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [trades, setTrades]         = useState<Trade[]>([]);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [online, setOnline]         = useState(true);

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

  return (
    <div className="min-h-screen" style={{ background: "var(--bg)" }}>
      {/* Header */}
      <header className="border-b border-[var(--border)] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-bold text-sm">T</div>
          <div>
            <h1 className="text-base font-semibold tracking-tight">Tincho Bot</h1>
            <p className="text-[11px] text-[var(--muted)]">Autonomous Trading Agent</p>
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
            <span className="text-[11px] text-[var(--muted)]">
              actualizado {lastUpdate.toLocaleTimeString("es-AR")}
            </span>
          )}
          <div className={`w-2 h-2 rounded-full ${online ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">

        {!online && <OfflineBanner />}

        {/* Portfolio Stats */}
        {port && (
          <Card title="Portafolio">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-6">
              <Stat
                label="Capital"
                value={<span className="font-mono">{port.capital.toFixed(2)} USDT</span>}
                sub={`Inicial: ${port.initial_capital.toFixed(2)}`}
              />
              <Stat
                label="Capital disponible"
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
              <Stat
                label="Posiciones abiertas"
                value={port.open_positions}
              />
              <Stat
                label="Total trades"
                value={port.total_trades}
              />
            </div>
          </Card>
        )}

        {/* Open Positions */}
        {port && port.open_positions > 0 && (
          <Card title="Posiciones abiertas">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(snapshots).map(([sym, snap]) => {
              const sig = signals[sym];
              return (
                <Card key={sym} title={sym}>
                  <div className="space-y-4">
                    {/* Price row */}
                    <div className="flex items-center justify-between">
                      <span className="text-2xl font-mono font-bold">
                        ${snap.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                      <TrendBadge trend={snap.trend} />
                    </div>

                    {/* RSI */}
                    <RsiBar rsi={snap.rsi} />

                    {/* Grid metrics */}
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

                    {/* Signal */}
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
              <table className="w-full text-sm">
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
                      <td className="py-2 pr-4">
                        <SignalBadge signal={t.direction} />
                      </td>
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
                        {t.duration_seconds < 60
                          ? `${t.duration_seconds.toFixed(0)}s`
                          : `${(t.duration_seconds / 60).toFixed(1)}m`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {/* Empty state */}
        {online && trades.length === 0 && port && port.total_trades === 0 && (
          <div className="text-center py-12 text-[var(--muted)]">
            <div className="text-4xl mb-3">📊</div>
            <div className="text-sm">Sin trades aún. El agente está analizando el mercado...</div>
            <div className="text-xs mt-1">Se ejecutará un trade cuando detecte una señal válida (PULLBACK o BREAKOUT).</div>
          </div>
        )}
      </main>
    </div>
  );
}
