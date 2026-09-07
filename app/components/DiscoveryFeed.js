'use client';
import React from 'react';
import { API_BASE, getPid } from '../lib/api';
import { Compass, Loader2, Info, RefreshCw, Star, Activity, X, BellRing } from 'lucide-react';
import JourneyModal from './JourneyModal';

const fmtUsd = (n) => (n == null ? '—' : n >= 1e9 ? '$' + (n / 1e9).toFixed(1) + 'B' : n >= 1e6 ? '$' + (n / 1e6).toFixed(1) + 'M' : '$' + Number(n).toLocaleString());
const fmtPx = (n) => (n == null ? '—' : n >= 1 ? '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 }) : '$' + Number(n).toPrecision(4));

const CALL_COLOR = {
  BUY: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
  HOLD: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
  SELL: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
  WAIT: 'bg-slate-700/40 text-slate-300 border-slate-600',
};
const DQ_COLOR = {
  GOOD: 'text-emerald-300', NO_MARKET: 'text-slate-500', STABLE: 'text-slate-500',
  INCOMPLETE: 'text-amber-400', STALE_DATA: 'text-amber-400',
};
const INELIG_LABEL = {
  NOT_IN_APPROVED_UNIVERSE: 'Not in your approved universe', EXCLUDED_BY_MANDATE: 'Excluded by your mandate',
  MANDATE_INCOMPLETE: 'Set your mandate first', STALE_DATA: 'No usable market data',
};

function PinButton({ pinned, onToggle, size = 'h-3.5 w-3.5' }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onToggle(); }}
      title={pinned ? 'Unpin from watchlist' : 'Pin to watchlist'}
      className={`rounded p-0.5 transition ${pinned ? 'text-amber-300' : 'text-slate-600 hover:text-amber-300'}`}
    >
      <Star className={size} fill={pinned ? 'currentColor' : 'none'} />
    </button>
  );
}

function Row({ a, pinned, onTogglePin, onJourney }) {
  const [open, setOpen] = React.useState(false);
  const overLine = a.opportunityScore != null && a.opportunityScore >= a.buyThreshold;
  return (
    <>
      <tr className="cursor-pointer border-t border-slate-800/60 hover:bg-slate-900/40" onClick={() => setOpen(!open)}>
        <td className="py-1.5 pl-2 pr-1"><PinButton pinned={pinned} onToggle={() => onTogglePin(a.symbol)} /></td>
        <td className="pr-2 text-[11px] text-slate-500">#{a.rank ?? '—'}</td>
        <td className="pr-2"><span className="font-semibold text-slate-200">{a.symbol}</span> <span className="text-[10px] text-slate-500">{fmtUsd(a.marketCapUsd)}</span></td>
        <td className="pr-2">{a.opportunityScore != null ? <span className={overLine ? 'font-bold text-emerald-300' : 'text-slate-300'}>{a.opportunityScore}</span> : <span className="text-slate-600">n/a</span>}</td>
        <td className="pr-2 text-[11px] text-slate-500">{a.confidence != null ? a.confidence + '%' : '—'}</td>
        <td className="pr-2 text-[11px]"><span className={a.liquidity === 'PASS' ? 'text-emerald-400' : 'text-slate-500'}>{a.liquidity}</span> · <span className={DQ_COLOR[a.dataQuality] || 'text-slate-400'}>{a.dataQuality}</span></td>
        <td className="pr-2 text-[11px]">{a.eligible ? <span className="text-emerald-400">YES</span> : <span className="text-slate-500">NO</span>}</td>
        <td className="pr-3"><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${CALL_COLOR[a.albertCall] || CALL_COLOR.WAIT}`}>{a.albertCall}</span></td>
      </tr>
      {open && (
        <tr className="border-t border-slate-800/40 bg-slate-950/40"><td colSpan={8} className="px-3 py-2">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] sm:grid-cols-4">
            <div><span className="text-slate-500">Price</span><div className="text-slate-200">{fmtPx(a.priceUsd)}</div></div>
            <div><span className="text-slate-500">24h volume</span><div className="text-slate-200">{fmtUsd(a.volume24hUsd)}</div></div>
            <div><span className="text-slate-500">Score vs BUY line</span><div className={overLine ? 'text-emerald-300' : 'text-slate-300'}>{a.opportunityScore != null ? `${a.opportunityScore} vs ${a.buyThreshold}` : 'not scored'}</div></div>
            <div><span className="text-slate-500">Tradable venue</span><div className="text-slate-200">{a.tradable ? 'Coinbase / Kraken' : 'none (not scored)'}</div></div>
          </div>
          <div className="mt-2 flex items-start gap-1 rounded-lg border border-slate-800 bg-slate-900/40 p-2 text-[11px] text-slate-400">
            <Info className="mt-0.5 h-3 w-3 shrink-0" />
            <div>
              {a.albertCall === 'BUY' && <span className="text-emerald-300">Interesting AND eligible — final sizing/tranches live in the Command Centre.</span>}
              {a.albertCall !== 'BUY' && !a.eligible && <span>What would change this: <span className="text-slate-300">{INELIG_LABEL[a.ineligibilityReason] || a.ineligibilityReason}</span>. Discovery shows what looks interesting; eligibility decides what you may buy.</span>}
              {a.albertCall !== 'BUY' && a.eligible && a.opportunityScore != null && !overLine && <span>Eligible, but opportunity score {a.opportunityScore} is below the {a.buyThreshold} BUY line for this regime.</span>}
              {a.albertCall === 'HOLD' && a.held && <span> You already hold this — position management lives in the Command Centre.</span>}
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button onClick={(e) => { e.stopPropagation(); onJourney(a.symbol); }} className="flex items-center gap-1 rounded-full border border-sky-500/40 bg-sky-500/10 px-2.5 py-1 text-[11px] font-semibold text-sky-300 hover:bg-sky-500/20"><Activity className="h-3 w-3" />View decision journey</button>
            <button onClick={(e) => { e.stopPropagation(); onTogglePin(a.symbol); }} className={`flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${pinned ? 'border-amber-500/40 bg-amber-500/10 text-amber-300' : 'border-slate-700 text-slate-300 hover:bg-slate-800'}`}><Star className="h-3 w-3" fill={pinned ? 'currentColor' : 'none'} />{pinned ? 'Pinned to watchlist' : 'Pin to watchlist'}</button>
          </div>
        </td></tr>
      )}
    </>
  );
}

function WatchlistAlerts({ alerts, onDismiss, onJourney }) {
  if (!alerts || alerts.length === 0) return null;
  const arrow = (c) => (c === 'BUY' ? 'text-emerald-300' : c === 'SELL' ? 'text-rose-300' : c === 'HOLD' ? 'text-sky-300' : 'text-slate-300');
  return (
    <div className="mb-3 rounded-xl border border-sky-500/30 bg-sky-500/[0.07] p-2.5">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-sky-200">
          <BellRing className="h-3.5 w-3.5" />Watchlist moves ({alerts.length})
        </span>
        <button onClick={onDismiss} className="text-[10px] font-semibold text-slate-400 hover:text-white">Dismiss all</button>
      </div>
      <div className="space-y-1">
        {alerts.map((a) => (
          <button key={a.id} onClick={() => onJourney && onJourney(a.symbol)} className="flex w-full items-center gap-1.5 text-left text-[12px] hover:opacity-90">
            <span className="font-semibold text-slate-200">{a.symbol}</span>
            <span className="text-slate-500">call flipped</span>
            <span className={`font-bold ${arrow(a.fromCall)}`}>{a.fromCall}</span>
            <span className="text-slate-500">→</span>
            <span className={`font-bold ${arrow(a.toCall)}`}>{a.toCall}</span>
            {a.toCall === 'BUY' && !a.eligible && <span className="ml-1 rounded-full border border-slate-600 px-1.5 text-[9px] text-slate-400">still gated</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

function WatchlistStrip({ assets, onUnpin, onJourney }) {
  if (!assets || assets.length === 0) return null;
  return (
    <div className="mb-3 rounded-xl border border-amber-500/25 bg-amber-500/[0.05] p-2.5">
      <div className="mb-1.5 flex items-center gap-1.5">
        <Star className="h-3.5 w-3.5 text-amber-300" fill="currentColor" />
        <span className="text-[11px] font-bold uppercase tracking-wide text-amber-200">Your watchlist ({assets.length})</span>
        <span className="text-[10px] text-slate-500">— pinning is a bookmark, not permission to buy</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {assets.map((a) => (
          <div key={a.symbol} className="group flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-900/60 py-0.5 pl-2 pr-1 text-[11px]">
            <span className="font-semibold text-slate-200">{a.symbol}</span>
            {a.opportunityScore != null && <span className="text-slate-500">{a.opportunityScore}</span>}
            <span className={`rounded-full border px-1.5 py-0 text-[9px] font-bold ${CALL_COLOR[a.albertCall] || CALL_COLOR.WAIT}`}>{a.albertCall || '—'}</span>
            <button onClick={() => onJourney(a.symbol)} title="View journey" className="text-slate-500 hover:text-sky-300"><Activity className="h-3 w-3" /></button>
            <button onClick={() => onUnpin(a.symbol)} title="Unpin" className="text-slate-600 hover:text-rose-300"><X className="h-3 w-3" /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function DiscoveryFeed() {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [pinned, setPinned] = React.useState([]);         // array of symbols
  const [watchAssets, setWatchAssets] = React.useState([]); // enriched pinned assets
  const [journeyFor, setJourneyFor] = React.useState(null);
  const [alerts, setAlerts] = React.useState([]);   // unseen call-flip alerts
  const pollRef = React.useRef(null);

  const load = React.useCallback(() => {
    const pid = getPid();
    fetch(`${API_BASE}/v1/albert/discovery?pid=${encodeURIComponent(pid || '')}`, { cache: 'no-store' })
      .then((r) => r.json()).then((j) => {
        setData(j); setLoading(false);
        if (j.status === 'building' && !pollRef.current) {
          pollRef.current = setInterval(load, 8000);
        } else if (j.status === 'ready' && pollRef.current) {
          clearInterval(pollRef.current); pollRef.current = null;
        }
      }).catch(() => setLoading(false));
  }, []);

  const loadWatchlist = React.useCallback(() => {
    const pid = getPid();
    if (!pid) return;
    fetch(`${API_BASE}/v1/albert/watchlist?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' })
      .then((r) => r.json()).then((j) => {
        setPinned(j.symbols || []); setWatchAssets(j.assets || []);
        // watchlist GET also detects flips; now pull any unseen call-flip alerts.
        return fetch(`${API_BASE}/v1/albert/watchlist/alerts?pid=${encodeURIComponent(pid)}`, { cache: 'no-store' });
      }).then((r) => r && r.json()).then((j) => { if (j) setAlerts(j.alerts || []); }).catch(() => {});
  }, []);

  const dismissAlerts = React.useCallback(() => {
    const pid = getPid();
    setAlerts([]);
    if (pid) fetch(`${API_BASE}/v1/albert/watchlist/alerts/ack`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pid }) }).catch(() => {});
  }, []);

  React.useEffect(() => {
    load(); loadWatchlist();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [load, loadWatchlist]);

  const pinnedSet = React.useMemo(() => new Set(pinned), [pinned]);

  const togglePin = React.useCallback((symbol) => {
    const pid = getPid();
    if (!pid) return;
    const isPinned = pinnedSet.has(symbol);
    // optimistic
    setPinned((prev) => isPinned ? prev.filter((s) => s !== symbol) : [symbol, ...prev]);
    const req = isPinned
      ? fetch(`${API_BASE}/v1/albert/watchlist/${encodeURIComponent(symbol)}?pid=${encodeURIComponent(pid)}`, { method: 'DELETE' })
      : fetch(`${API_BASE}/v1/albert/watchlist`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pid, symbol }) });
    req.then((r) => r.json()).then((j) => { if (j.symbols) setPinned(j.symbols); loadWatchlist(); }).catch(() => loadWatchlist());
  }, [pinnedSet, loadWatchlist]);

  const assets = data?.assets || [];
  return (
    <div className="rounded-2xl border border-violet-500/20 bg-gradient-to-b from-violet-500/[0.06] to-slate-900/40 p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Compass className="h-4 w-4 text-violet-300" />
          <h3 className="text-base font-bold text-white">Top-100 Discovery</h3>
        </div>
        <button onClick={() => { load(); loadWatchlist(); }} className="flex items-center gap-1 rounded-full border border-slate-700 px-2.5 py-1 text-[11px] text-slate-300 hover:bg-slate-800"><RefreshCw className="h-3 w-3" />Refresh</button>
      </div>
      <p className="mb-2 text-[11px] text-slate-400">What looks interesting across the live market-cap top 100. <span className="text-slate-500">Discovery is not permission to buy — eligibility &amp; sizing stay in the Command Centre.</span></p>

      <WatchlistAlerts alerts={alerts} onDismiss={dismissAlerts} onJourney={setJourneyFor} />
      <WatchlistStrip assets={watchAssets} onUnpin={togglePin} onJourney={setJourneyFor} />

      {(loading || data?.status === 'building') && assets.length === 0 ? (
        <div className="flex items-center gap-2 py-8 text-[12px] text-slate-400"><Loader2 className="h-3.5 w-3.5 animate-spin" />Scanning the live top-100 universe…</div>
      ) : assets.length === 0 ? (
        <p className="py-6 text-center text-[12px] text-slate-500">Discovery feed unavailable right now.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-500">
            <span>Regime <b className="text-slate-300">{data.regime}</b></span>
            <span>BUY line <b className="text-slate-300">{data.buyThreshold}</b></span>
            <span>Liquidity floor <b className="text-slate-300">{fmtUsd(data.liquidityMinUsd)}</b></span>
            {data.stale && <span className="text-amber-400">refreshing…</span>}
          </div>
          <div className="mt-2 overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full text-left text-[12px]">
              <thead><tr className="bg-slate-900/60 text-[10px] uppercase text-slate-500">
                <th className="py-1.5 pl-2 pr-1"></th><th className="pr-2">Rank</th><th className="pr-2">Asset</th><th className="pr-2">Score</th>
                <th className="pr-2">Conf</th><th className="pr-2">Liquidity / Data</th><th className="pr-2">Eligible</th><th className="pr-3">Call</th>
              </tr></thead>
              <tbody>{assets.map((a) => <Row key={a.symbol + a.rank} a={a} pinned={pinnedSet.has(a.symbol)} onTogglePin={togglePin} onJourney={setJourneyFor} />)}</tbody>
            </table>
          </div>
          <p className="mt-1.5 text-[10px] text-slate-600">Source {data.source} · {data.count} assets · engine {data.engineVersion} · advisory / paper only.</p>
        </>
      )}

      {journeyFor && <JourneyModal asset={journeyFor} onClose={() => setJourneyFor(null)} />}
    </div>
  );
}
