'use client';

import React from 'react';
import { BarChart3, Magnet, Newspaper, RefreshCw, Sparkles } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ReferenceDot } from 'recharts';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { API_BASE } from '../lib/api';
import { fmtUsd, signalText, DIR_COLOR } from '../lib/format';
import { SymbolContext } from '../lib/context';
import { sec } from '../lib/sections';
import { SectionHead, AiReview, InfoTip } from './shared';

function NewsCard({ c, compact, onAnchor, pinned }) {
  const ai = c.ai || {};
  const dir = ai.direction || 'neutral';
  const th = ai.time_horizons || {};
  const fi = c.forecast_impact || {};
  const vBadge = c.verification === 'Confirmed' ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
    : c.verification === 'Unconfirmed' ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
    : 'border-slate-700 bg-slate-800/60 text-slate-300';
  const sources = c.sources && c.sources.length ? c.sources : [{ source: c.source, link: c.link, credibility: c.credibility }];
  const PinBtn = onAnchor ? (
    <button onClick={() => onAnchor(c)} title="Pin this story on the price chart"
      className={`inline-flex min-h-[28px] shrink-0 items-center gap-1 rounded-lg border px-2 py-1 text-[10px] font-semibold ${pinned ? 'border-sky-500/50 bg-sky-500/20 text-sky-200' : 'border-slate-700 bg-slate-800/60 text-slate-300 hover:border-sky-500/40 hover:text-sky-300'}`}>
      <Magnet className="h-3 w-3" />{pinned ? 'Pinned' : 'Pin to chart'}
    </button>
  ) : null;
  if (compact) {
    return (
      <Card className={`border-0 bg-slate-900 p-3.5 ring-1 ${pinned ? 'ring-sky-500/40' : 'ring-slate-800'}`}>
        <div className="flex items-center gap-2">
          <span className={`rounded border px-2 py-1 text-[11px] font-semibold uppercase ${DIR_COLOR[dir]}`}>{dir}</span>
          <a href={c.link} target="_blank" rel="noreferrer" className="flex-1 truncate text-sm font-semibold text-slate-100 hover:text-sky-300">{c.title}</a>
          {PinBtn}
          <span className="shrink-0 rounded-full bg-sky-500/10 px-2 py-1 text-[11px] font-bold text-sky-400">Impact {c.impact}</span>
        </div>
      </Card>
    );
  }
  return (
    <Card className={`border-0 bg-slate-900 p-5 ring-1 ${pinned ? 'ring-sky-500/40' : 'ring-slate-800'}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded bg-slate-800 px-2 py-0.5 font-medium text-slate-300">{c.source}</span>
        {c.verification && <span className={`rounded border px-2 py-0.5 font-semibold ${vBadge}`}>{c.verification}</span>}
        {c.n_sources > 1 && <span className="rounded bg-slate-800/60 px-2 py-0.5 text-slate-400">{c.n_sources} sources</span>}
        <span className={`rounded border px-2 py-0.5 font-semibold uppercase ${DIR_COLOR[dir]}`}>{dir}</span>
        <span className="ml-auto rounded-full bg-sky-500/10 px-2 py-0.5 font-bold text-sky-400">Impact {c.impact} · {c.impact_label}</span>
        {PinBtn}
      </div>
      <a href={c.link} target="_blank" rel="noreferrer" className="mt-2 block text-base font-semibold text-slate-100 hover:text-sky-300">{c.title}</a>
      <p className="mt-2 text-sm text-slate-300">{ai.summary}</p>
      {ai.why_it_matters && <p className="mt-2 text-sm text-slate-400"><span className="font-semibold text-slate-300">Why it matters: </span>{ai.why_it_matters}</p>}
      <div className="mt-3 flex items-center gap-1.5">
        <div className="flex h-2 flex-1 overflow-hidden rounded-full bg-slate-800">
          <div className="h-full bg-emerald-400" style={{ width: `${ai.bullish_pct || 0}%` }} />
          <div className="h-full bg-slate-500" style={{ width: `${ai.neutral_pct || 0}%` }} />
          <div className="h-full bg-red-400" style={{ width: `${ai.bearish_pct || 0}%` }} />
        </div>
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-slate-500"><span className="text-emerald-400">▲ {ai.bullish_pct || 0}%</span><span>neutral {ai.neutral_pct || 0}%</span><span className="text-red-400">▼ {ai.bearish_pct || 0}%</span></div>
      {fi.note && (
        <div className={`mt-3 rounded-lg border p-2.5 text-xs ${fi.nudge_pts > 0 ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-300' : fi.nudge_pts < 0 ? 'border-red-500/20 bg-red-500/5 text-red-300' : 'border-slate-800 bg-slate-950/40 text-slate-400'}`}>
          <span className="font-semibold">Effect on CryptoMarkAI forecast: </span>{fi.note}{fi.horizons?.length ? ` (${fi.horizons.join(', ')})` : ''}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
        {th.immediate && <span className="rounded border border-slate-800 px-1.5 py-0.5 text-slate-400">Now: <span className={signalText(th.immediate === 'bullish' ? 'Bullish' : th.immediate === 'bearish' ? 'Bearish' : 'Neutral')}>{th.immediate}</span></span>}
        {th.seven_day && <span className="rounded border border-slate-800 px-1.5 py-0.5 text-slate-400">7d: {th.seven_day}</span>}
        {th.long_term && <span className="rounded border border-slate-800 px-1.5 py-0.5 text-slate-400">Long: {th.long_term}</span>}
        {(ai.categories || []).slice(0, 3).map((cat, i) => <span key={i} className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-400">{String(cat).replace(/_/g, ' ')}</span>)}
        {ai.confidence != null && <span className="ml-auto text-slate-500">confidence {Math.round((ai.confidence || 0) * 100)}%</span>}
      </div>
      {sources.length > 1 && (
        <div className="mt-3 border-t border-slate-800 pt-2">
          <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">Reported by {sources.length} sources</p>
          <div className="flex flex-wrap gap-2">
            {sources.map((s, i) => (
              <a key={i} href={s.link} target="_blank" rel="noreferrer" className="rounded bg-slate-800/60 px-2 py-0.5 text-[11px] text-slate-400 hover:text-sky-300">{s.source} ↗</a>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

// ---- News-to-Chart Anchor: drops a marker on the 90d price chart at a story's date ----
function NewsPriceChart({ ohlc, anchor, onClear, chartRef }) {
  const data = React.useMemo(() => {
    const n = ohlc.length;
    const today = new Date();
    return ohlc.map((o, i) => {
      const dt = new Date(today.getTime() - (n - 1 - i) * 86400000);
      return { t: o.t, c: o.c, key: dt.toISOString().slice(0, 10) };
    });
  }, [ohlc]);
  const info = React.useMemo(() => {
    if (!anchor || !anchor.published || data.length === 0) return null;
    const nd = new Date(anchor.published);
    if (isNaN(nd.getTime())) return null;
    const ndKey = nd.toISOString().slice(0, 10);
    let idx = data.findIndex((p) => p.key === ndKey);
    let approx = false;
    if (idx === -1) {
      approx = true;
      let best = 0, bestDiff = Infinity;
      data.forEach((p, i) => { const diff = Math.abs(new Date(p.key).getTime() - nd.getTime()); if (diff < bestDiff) { bestDiff = diff; best = i; } });
      idx = best;
    }
    return { idx, x: data[idx].t, y: data[idx].c, approx, date: ndKey };
  }, [anchor, data]);
  const dir = anchor ? ((anchor.ai || {}).direction || 'neutral') : 'neutral';
  const dotColor = dir === 'bullish' ? '#34d399' : dir === 'bearish' ? '#f87171' : '#38bdf8';
  return (
    <Card ref={chartRef} className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <BarChart3 className="h-5 w-5 text-sky-400" />
        <h3 className="flex items-center gap-1 font-semibold text-slate-100">Price context (90d)<InfoTip below text="Tap any story's 'Pin to chart' to drop a marker at the day that news broke, so you can see how price moved around it." /></h3>
        {anchor ? (
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-[11px] text-slate-400 sm:inline">Pinned: {info ? info.date : '—'}{info && info.approx ? ' (nearest)' : ''}</span>
            <button onClick={onClear} className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-[11px] font-semibold text-slate-300 hover:bg-slate-700">Clear marker</button>
          </div>
        ) : <span className="ml-auto text-[11px] text-slate-500">No story pinned — tap “Pin to chart” on any story below</span>}
      </div>
      {anchor && (
        <div className="mb-2 flex items-start gap-2 rounded-lg border p-2.5 text-xs" style={{ borderColor: dotColor + '55', background: dotColor + '11' }}>
          <span className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase" style={{ color: dotColor, background: dotColor + '22' }}>{dir}</span>
          <a href={anchor.link} target="_blank" rel="noreferrer" className="flex-1 text-slate-200 hover:text-sky-300">{anchor.title}</a>
          <span className="shrink-0 font-bold text-sky-400">Impact {anchor.impact}</span>
        </div>
      )}
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="t" stroke="#64748b" fontSize={10} minTickGap={40} tickLine={false} />
            <YAxis stroke="#64748b" fontSize={10} domain={['auto', 'auto']} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} width={44} tickLine={false} />
            <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }} formatter={(v) => [fmtUsd(v), 'Close']} />
            <Line type="monotone" dataKey="c" stroke="#38bdf8" strokeWidth={1.6} dot={false} />
            {info && <ReferenceLine x={info.x} stroke={dotColor} strokeDasharray="4 3" />}
            {info && <ReferenceDot x={info.x} y={info.y} r={6} fill={dotColor} stroke="#0b1220" strokeWidth={2} isFront
              label={{ value: `Impact ${anchor.impact}`, position: 'top', fill: dotColor, fontSize: 10, fontWeight: 700 }} />}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}


function NewsSection({ news, status, onRefresh, refreshing, ohlc }) {
  const [filter, setFilter] = React.useState('all');
  const [density, setDensity] = React.useState('expanded');
  const [anchor, setAnchor] = React.useState(null);
  const chartRef = React.useRef(null);
  const symbol = React.useContext(SymbolContext);
  const pinToChart = (c) => {
    setAnchor(c);
    setTimeout(() => chartRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 60);
  };
  if (status !== 'ready' || !news) {
    return (
      <div className="space-y-5">
        <SectionHead icon={Newspaper} title={`${symbol} News`} blurb={sec('news').blurb} coin={symbol} />
        <Card className="flex items-center justify-center gap-3 border-0 bg-slate-900 p-16 ring-1 ring-slate-800">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-700 border-t-sky-400" />
          <span className="text-slate-400">{status === 'error' ? 'News engine error — try refresh.' : 'Gathering headlines & generating AI summaries…'}</span>
        </Card>
      </div>
    );
  }
  const b = news.briefing || {};
  const cards = (news.cards || []).filter((c) => filter === 'all' || (c.ai || {}).direction === filter);
  const biasColor = b.bias === 'Moderately Bullish' ? 'text-emerald-400' : b.bias === 'Moderately Bearish' ? 'text-red-400' : 'text-amber-400';
  return (
    <div className="space-y-5">
      <SectionHead icon={Newspaper} title={`${symbol} News`} blurb={sec('news').blurb} coin={symbol} />
      <AiReview section="news" text="Albert is reviewing today’s news…" voice />
      <Card className="border-0 bg-gradient-to-br from-violet-500/10 to-slate-900 p-6 ring-1 ring-violet-500/25">
        <div className="mb-3 flex items-center gap-2"><Sparkles className="h-5 w-5 text-violet-400" /><h3 className="flex items-center gap-1 font-semibold text-slate-100">Daily AI Briefing<InfoTip below text={`A plain-English summary of the day's most important ${symbol} news, written by the AI, with the likely market impact of each story.`} /></h3><span className="ml-auto text-[11px] text-slate-500">{news.model}</span></div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="rounded-lg bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">Market News Bias</p><p className={`text-lg font-bold ${biasColor}`}>{b.bias}</p></div>
          <div className="rounded-lg bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">Stories</p><p className="text-lg font-bold text-white">{b.total}</p></div>
          <div className="rounded-lg bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">High-Impact</p><p className="text-lg font-bold text-white">{b.major_stories}</p></div>
          <div className="rounded-lg bg-slate-950/40 p-3"><p className="text-[11px] text-slate-400">Next Event</p><p className="text-sm font-bold text-white">{b.next_event ? `${b.next_event.event}` : '—'}</p></div>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3"><p className="text-[11px] font-semibold uppercase text-emerald-400">Top Tailwind</p><p className="mt-1 text-sm text-slate-300">{b.top_tailwind}</p></div>
          <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3"><p className="text-[11px] font-semibold uppercase text-red-400">Top Risk</p><p className="mt-1 text-sm text-slate-300">{b.top_risk}</p></div>
        </div>
      </Card>
      {ohlc && ohlc.length > 0 && <NewsPriceChart ohlc={ohlc} anchor={anchor} onClear={() => setAnchor(null)} chartRef={chartRef} />}
      <div className="flex flex-wrap items-center gap-2">
        {['all', 'bullish', 'bearish', 'mixed', 'neutral'].map((f) => (
          <button key={f} onClick={() => setFilter(f)} className={`min-h-[40px] rounded-lg px-3 py-1.5 text-xs font-medium capitalize ${filter === f ? 'bg-sky-500/15 text-sky-300' : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'}`}>{f}</button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <div className="flex items-center rounded-lg border border-slate-800 bg-slate-900 p-0.5" role="group" aria-label="Feed density">
            <button onClick={() => setDensity('compact')} className={`min-h-[36px] rounded-md px-3 py-1 text-xs font-semibold ${density === 'compact' ? 'bg-sky-500/15 text-sky-300' : 'text-slate-400 hover:text-slate-200'}`}>Compact</button>
            <button onClick={() => setDensity('expanded')} className={`min-h-[36px] rounded-md px-3 py-1 text-xs font-semibold ${density === 'expanded' ? 'bg-sky-500/15 text-sky-300' : 'text-slate-400 hover:text-slate-200'}`}>Expanded</button>
          </div>
          <Button onClick={onRefresh} disabled={refreshing} size="sm" className="min-h-[40px] gap-2 bg-slate-800 text-slate-100 hover:bg-slate-700"><RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />Refresh</Button>
        </div>
      </div>
      <div className={density === 'compact' ? 'space-y-2' : 'grid grid-cols-1 gap-4 lg:grid-cols-2'}>
        {cards.map((c, i) => <NewsCard key={i} c={c} compact={density === 'compact'} onAnchor={ohlc && ohlc.length > 0 ? pinToChart : null} pinned={anchor && anchor.title === c.title} />)}
      </div>
      {cards.length === 0 && <p className="text-sm text-slate-500">No stories match this filter.</p>}
    </div>
  );
}

/* ----------------------------- CryptoMarkAI ----------------------------- */

export default NewsSection;
