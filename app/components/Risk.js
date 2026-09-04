'use client';

import React from 'react';
import { ShieldAlert } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { fmtUsd } from '../lib/format';
import { sec } from '../lib/sections';
import { SectionHead, AiReview, InfoTip, DemoBadge } from './shared';

const riskStateColor = (s) => ({ Low: 'text-emerald-400', Normal: 'text-lime-400', Deep: 'text-emerald-400',
  Elevated: 'text-amber-400', High: 'text-orange-400', Thin: 'text-orange-400', Extreme: 'text-red-400' }[s] || 'text-slate-300');

function RiskSection({ d }) {
  const r = d.risk;
  if (!r) return <ComingSoonSection section={sec('risk')} />;
  const lvlColor = riskStateColor(r.level);
  return (
    <div className="space-y-5">
      <SectionHead icon={ShieldAlert} title="Ask Albert Risk" blurb={sec('risk').blurb} coin={d.symbol || 'BTC'} />
      <AiReview section="risk" text="Albert is reviewing current risk…" voice />
      <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
        <div className="flex flex-wrap items-center gap-6">
          <div>
            <p className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-slate-400">Overall Risk Level<InfoTip below text={`How turbulent ${(d.symbol || 'BTC')} is right now on a 0–100 scale. It measures the size of the swings, not the direction — high risk can happen in both up and down markets.`} /></p>
            <p className={`text-4xl font-black ${lvlColor}`}>{r.level}</p>
            <p className="text-xs text-slate-500">score {r.score}/100 · direction-independent</p>
          </div>
          <div className="flex-1">
            <div className="flex gap-1">
              {r.state_scale.map((s) => (
                <div key={s} className={`flex-1 rounded py-1 text-center text-[10px] font-semibold ${s === r.level ? `${riskStateColor(s)} bg-slate-800 ring-1 ring-slate-600` : 'text-slate-600'}`}>{s}</div>
              ))}
            </div>
            <p className="mt-3 text-xs italic text-slate-500">{r.note}</p>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <p className="mb-3 flex items-center gap-1 text-sm font-semibold text-white">Expected Move<InfoTip below text="A statistical range of where price could sit over each window, based on recent volatility. It's a likely band, not a target — price can still break out of it." /></p>
          {['24H', '7D', '30D'].map((h) => {
            const e = r.expected_move[h];
            return (
              <div key={h} className="mb-2 flex items-center justify-between text-sm">
                <span className="text-slate-400">{h}</span>
                <span className="font-mono text-slate-200">±{e.pct}% · {fmtUsd(e.low)}–{fmtUsd(e.high)}</span>
              </div>
            );
          })}
          <p className="mt-2 text-[11px] text-slate-500">Realised vol ≈ {r.realised_vol_annual}% annualised ({r.vol_percentile}th pct)</p>
        </Card>
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <p className="mb-3 flex items-center gap-1 text-sm font-semibold text-white">Key Zones<InfoTip below text="The nearest notable price levels above and below where reactions are more likely (support/resistance) and the % distance to each from spot." /></p>
          {r.upside_zone && <div className="mb-2 rounded-lg border border-red-500/20 bg-red-500/5 p-2.5 text-sm"><p className="text-[11px] text-slate-400">{r.upside_zone.label}</p><p className="font-mono font-bold text-red-300">{fmtUsd(r.upside_zone.price)} <span className="text-[11px] font-normal text-slate-500">+{r.upside_zone.distance_pct}%</span></p></div>}
          {r.downside_zone && <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5 text-sm"><p className="text-[11px] text-slate-400">{r.downside_zone.label}</p><p className="font-mono font-bold text-emerald-300">{fmtUsd(r.downside_zone.price)} <span className="text-[11px] font-normal text-slate-500">-{r.downside_zone.distance_pct}%</span></p></div>}
          {!r.upside_zone && !r.downside_zone && <p className="text-sm text-slate-500">No clear zones detected right now.</p>}
        </Card>
        <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
          <p className="mb-3 flex items-center gap-1 text-sm font-semibold text-white">Environment<InfoTip below text="Background conditions that can amplify risk: how much big scheduled macro events loom, and how uncertain/stale the underlying data feeds are." /></p>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-slate-400">Macro-event risk</span><span className={riskStateColor(r.macro_event_risk)}>{r.macro_event_risk}</span></div>
            <div className="flex justify-between"><span className="text-slate-400">Data uncertainty</span><span className={riskStateColor(r.data_uncertainty)}>{r.data_uncertainty}</span></div>
          </div>
          <p className="mt-2 text-[11px] text-slate-500">{r.macro_note}</p>
        </Card>
      </div>

      <Card className="border-0 bg-slate-900 p-5 ring-1 ring-slate-800">
        <div className="mb-3 flex items-center gap-2"><h3 className="flex items-center gap-1 text-sm font-semibold text-white">Risk Drivers<InfoTip below text="The individual factors feeding the risk score (volatility, leverage, liquidity, macro). Each shows its current state; items tagged Inactive are placeholders until a paid feed is added." /></h3><span className="text-[11px] text-slate-500">real + inactive</span></div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {r.drivers.map((dr, i) => (
            <div key={i} className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 p-2.5 text-sm">
              <span className="flex-1 text-slate-300">{dr.name}</span>
              {dr.demo && <DemoBadge />}
              <span className={`font-semibold ${riskStateColor(dr.state)}`}>{dr.state}</span>
              <span className="w-40 truncate text-right text-[11px] text-slate-500">{dr.value}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-slate-600">Metrics tagged Inactive (implied volatility, leverage/funding, liquidation clusters, order-book depth) are placeholders until a paid derivatives/order-book feed is connected. All other metrics are computed from real market data.</p>
      </Card>
    </div>
  );
}


export default RiskSection;
