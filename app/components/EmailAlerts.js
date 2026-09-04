'use client';

import React from 'react';
import { Mail, Send, Trash2, Plus, Clock, ShieldCheck, Loader2, AlertCircle, CheckCircle2, Lock } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { API_BASE } from '../lib/api';

export default function EmailAlerts() {
  const [pass, setPass] = React.useState('');
  const [loaded, setLoaded] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [cfg, setCfg] = React.useState(null);
  const [recips, setRecips] = React.useState([]);
  const [email, setEmail] = React.useState('');
  const [name, setName] = React.useState('');
  const [testTo, setTestTo] = React.useState('');
  const [msg, setMsg] = React.useState(null);
  const [busy, setBusy] = React.useState('');
  const [sev, setSev] = React.useState([]);

  const post = async (path, body) => {
    const r = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passcode: pass, ...(body || {}) }),
    });
    return r.json();
  };

  const load = React.useCallback(async (p) => {
    setLoading(true); setMsg(null);
    try {
      const r = await fetch(`${API_BASE}/v1/email/recipients/list`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passcode: p }),
      });
      const j = await r.json();
      if (j.status === 'ok') {
        setCfg({ from: j.from, configured: j.configured, digest_time: j.digest_time, digest_tz: j.digest_tz, weekly_day: j.weekly_day, weekly_time: j.weekly_time });
        setRecips(j.recipients || []);
        setSev(j.instant_severities || []);
        setLoaded(true);
      } else {
        setLoaded(false);
        setMsg({ type: 'err', text: j.message || 'Unlock failed — check the admin passcode.' });
      }
    } catch (e) {
      setMsg({ type: 'err', text: 'Network error while loading recipients.' });
    }
    setLoading(false);
  }, []);

  React.useEffect(() => {
    if (typeof window !== 'undefined') {
      const p = window.localStorage.getItem('btciq_admin_passcode') || '';
      if (p) { setPass(p); load(p); }
    }
  }, [load]);

  const addRecipient = async () => {
    if (!email.trim()) return;
    setBusy('add'); setMsg(null);
    const j = await post('/v1/email/recipients', { email: email.trim(), name: name.trim() });
    if (j.status === 'ok') { setRecips(j.recipients || []); setEmail(''); setName(''); setMsg({ type: 'ok', text: 'Recipient added.' }); }
    else setMsg({ type: 'err', text: j.message || 'Could not add recipient.' });
    setBusy('');
  };

  const removeRecipient = async (addr) => {
    setBusy('del:' + addr); setMsg(null);
    const j = await post('/v1/email/recipients/delete', { email: addr });
    if (j.status === 'ok') { setRecips(j.recipients || []); setMsg({ type: 'ok', text: 'Recipient removed.' }); }
    else setMsg({ type: 'err', text: j.message || 'Could not remove recipient.' });
    setBusy('');
  };

  const sendTest = async () => {
    setBusy('test'); setMsg(null);
    const j = await post('/v1/email/test', testTo.trim() ? { to: testTo.trim() } : {});
    setMsg({ type: j.status === 'ok' ? 'ok' : 'err', text: j.message || (j.status === 'ok' ? 'Test sent.' : 'Send failed.') });
    setBusy('');
  };

  const sendDigest = async () => {
    setBusy('digest'); setMsg(null);
    const j = await post('/v1/email/digest/send-now', {});
    setMsg({ type: j.status === 'ok' ? 'ok' : 'err', text: j.message || (j.status === 'ok' ? 'Digest sent.' : 'Send failed.') });
    setBusy('');
  };

  const sendInstant = async () => {
    setBusy('instant'); setMsg(null);
    const j = await post('/v1/email/instant/send-now', {});
    setMsg({ type: j.status === 'ok' ? 'ok' : 'err', text: j.message || (j.status === 'ok' ? 'Done.' : 'Send failed.') });
    setBusy('');
  };

  const sendWeekly = async () => {
    setBusy('weekly'); setMsg(null);
    const j = await post('/v1/email/weekly/send-now', {});
    setMsg({ type: j.status === 'ok' ? 'ok' : 'err', text: j.message || (j.status === 'ok' ? 'Weekly recap sent.' : 'Send failed.') });
    setBusy('');
  };

  const toggleSev = async (s) => {
    const next = sev.includes(s) ? sev.filter((x) => x !== s) : [...sev, s];
    setSev(next); setBusy('sev'); setMsg(null);
    const j = await post('/v1/email/settings', { instant_severities: next });
    if (j.status === 'ok') { setSev(j.instant_severities || next); setMsg({ type: 'ok', text: 'Instant-alert threshold updated.' }); }
    else setMsg({ type: 'err', text: j.message || 'Could not update threshold.' });
    setBusy('');
  };

  return (
    <Card className="border-0 bg-slate-900 p-6 ring-1 ring-slate-800">
      <h3 className="mb-1 flex items-center gap-2 font-semibold text-white">
        <Mail className="h-4 w-4 text-amber-400" />Email alert digest
      </h3>
      <p className="mb-4 text-xs leading-relaxed text-slate-500">
        A daily brief of CryptoMarkAI alerts, price and Albert&rsquo;s outlook, emailed to the addresses below.
        High-severity alerts are also sent the moment they trigger. Requires the admin passcode (saved above).
        Sends automatically each day{cfg ? ` at ${cfg.digest_time} ${cfg.digest_tz}` : ''}.
      </p>

      {!loaded && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Lock className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
            <input
              type="password" value={pass} onChange={(e) => setPass(e.target.value)}
              placeholder="Admin passcode"
              onKeyDown={(e) => { if (e.key === 'Enter') load(pass); }}
              className="w-56 rounded-lg border border-slate-700 bg-slate-950/60 py-2 pl-8 pr-3 text-sm text-slate-100 focus:border-amber-500/50 focus:outline-none"
            />
          </div>
          <Button onClick={() => load(pass)} disabled={loading || !pass} className="min-h-[40px] bg-amber-500 text-slate-950 hover:bg-amber-400">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Unlock'}
          </Button>
        </div>
      )}

      {loaded && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs">
            {cfg?.configured
              ? <span className="inline-flex items-center gap-1 font-semibold text-emerald-400"><ShieldCheck className="h-3.5 w-3.5" />Resend connected</span>
              : <span className="inline-flex items-center gap-1 font-semibold text-red-400"><AlertCircle className="h-3.5 w-3.5" />Not configured</span>}
            <span className="text-slate-600">·</span>
            <span className="text-slate-400">From <span className="text-slate-200">{cfg?.from}</span></span>
            <span className="text-slate-600">·</span>
            <span className="inline-flex items-center gap-1 text-slate-400"><Clock className="h-3.5 w-3.5" />{cfg?.digest_time} {cfg?.digest_tz}</span>
          </div>

          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Instant-alert threshold
              <span className="font-normal normal-case text-slate-500">— email the moment these fire</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {[['critical', 'Critical'], ['high', 'High'], ['medium', 'Medium'], ['low', 'Low']].map(([k, label]) => {
                const on = sev.includes(k);
                return (
                  <button key={k} onClick={() => toggleSev(k)} disabled={busy === 'sev'}
                    className={`min-h-[36px] rounded-full px-3 text-xs font-semibold ring-1 transition ${on ? 'bg-amber-500/20 text-amber-300 ring-amber-500/40' : 'bg-slate-950/40 text-slate-400 ring-slate-700 hover:text-slate-200'}`}>
                    {on ? '\u2713 ' : ''}{label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Recipients ({recips.length})</div>
            {recips.length === 0 && <p className="text-xs text-slate-500">No recipients yet — add one below.</p>}
            <div className="space-y-2">
              {recips.map((r) => (
                <div key={r.email} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm text-slate-100">{r.email}</div>
                    {r.name && <div className="truncate text-[11px] text-slate-500">{r.name}</div>}
                  </div>
                  <button
                    onClick={() => removeRecipient(r.email)} disabled={busy === 'del:' + r.email}
                    className="ml-3 inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-red-500/10 hover:text-red-400"
                    aria-label={`Remove ${r.email}`}
                  >
                    {busy === 'del:' + r.email ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label className="mb-1 block text-[11px] font-medium text-slate-400">Email address</label>
              <input
                type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com"
                className="w-56 rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 focus:border-amber-500/50 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-medium text-slate-400">Name (optional)</label>
              <input
                type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane"
                className="w-40 rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 focus:border-amber-500/50 focus:outline-none"
              />
            </div>
            <Button onClick={addRecipient} disabled={busy === 'add' || !email.trim()} className="min-h-[40px] bg-sky-500 hover:bg-sky-400">
              {busy === 'add' ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Plus className="mr-1 h-4 w-4" />Add</>}
            </Button>
          </div>

          <div className="flex flex-wrap items-end gap-2 border-t border-slate-800 pt-4">
            <div>
              <label className="mb-1 block text-[11px] font-medium text-slate-400">Send a test to (optional)</label>
              <input
                type="email" value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder="defaults to whole list"
                className="w-56 rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 focus:border-amber-500/50 focus:outline-none"
              />
            </div>
            <Button onClick={sendTest} disabled={busy === 'test'} variant="outline" className="min-h-[40px] border-slate-700 bg-slate-950/40 text-slate-200 hover:bg-slate-800">
              {busy === 'test' ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Mail className="mr-1 h-4 w-4" />Send test</>}
            </Button>
            <Button onClick={sendDigest} disabled={busy === 'digest' || recips.length === 0} className="min-h-[40px] bg-amber-500 text-slate-950 hover:bg-amber-400">
              {busy === 'digest' ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Send className="mr-1 h-4 w-4" />Send digest now</>}
            </Button>
            <Button onClick={sendInstant} disabled={busy === 'instant' || recips.length === 0} variant="outline" className="min-h-[40px] border-red-500/30 bg-red-500/5 text-red-300 hover:bg-red-500/10">
              {busy === 'instant' ? <Loader2 className="h-4 w-4 animate-spin" /> : <><AlertCircle className="mr-1 h-4 w-4" />Send high-priority alerts</>}
            </Button>
            <Button onClick={sendWeekly} disabled={busy === 'weekly' || recips.length === 0} variant="outline" className="min-h-[40px] border-sky-500/30 bg-sky-500/5 text-sky-300 hover:bg-sky-500/10">
              {busy === 'weekly' ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Send className="mr-1 h-4 w-4" />Send weekly recap</>}
            </Button>
          </div>
        </div>
      )}

      {msg && (
        <div className={`mt-4 inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium ${msg.type === 'ok' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
          {msg.type === 'ok' ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}{msg.text}
        </div>
      )}
    </Card>
  );
}
