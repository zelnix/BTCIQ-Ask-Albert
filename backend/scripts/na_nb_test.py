"""N-A + N-B acceptance harness (live, unmocked).

Checks the two-stream market contracts and the scenario provider for the properties the
specification cares about most: that nothing is fabricated, that every gap names itself,
and that an unvalidated model cannot present itself as a forecast.
"""
import json
import os
import sys
import uuid

import requests

BASE = os.environ.get('NA_BASE', 'http://localhost:8001/api')
TOKEN = os.environ.get('NA_TOKEN', 'sop_e2e_session_token_0001')
S = requests.Session()
S.headers.update({'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
PASS, FAIL = [], []


def chk(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print(('  PASS  ' if cond else '  FAIL  ') + name
          + ((' :: ' + str(extra)[:260]) if extra and not cond else ''))


def get(p):
    r = S.get(BASE + p, timeout=180)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa
        return r.status_code, {'raw': r.text[:200]}


def post(p, b=None):
    r = S.post(BASE + p, data=json.dumps(b or {}), timeout=180)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa
        return r.status_code, {'raw': r.text[:200]}


print('== N-A market contracts ==')
# The universe snapshot rebuilds in a background thread by design (a request never blocks
# on it), so warm the cache and wait for it rather than asserting against a cold start.
import time as _t
for _try in range(8):
    get('/v1/albert/market-streams?participants=0')
    _sc, _probe = get('/v1/albert/market-streams?participants=0')
    if (_probe.get('universe') or {}).get('status') != 'MISSING':
        break
    _t.sleep(6)
sc, ms = get('/v1/albert/market-streams')
chk('market-streams returns ready', sc == 200 and ms.get('status') == 'ready', (sc, ms))
chk('every section carries its own ResultMeta',
    all(k in (ms.get('meta') or {}) for k in
        ('direction', 'phaseAssessment', 'spotVolumeShares', 'participants', 'sectors',
         'researchFindings')), list((ms.get('meta') or {}).keys()))
uni = ms.get('universe') or {}
chk('universe is versioned and discloses exclusions',
    uni.get('universeVersion') and isinstance(uni.get('excluded'), dict), uni)
chk('universe discloses its limitations', len(uni.get('limitations') or []) >= 2, uni)

ph = ms.get('phaseAssessment') or {}
chk('phase is one of the four allowed values',
    ph.get('phase') in ('BTC_LED', 'ALTCOIN_LED', 'MIXED', 'UNKNOWN'), ph.get('phase'))
chk('phase carries a versioned rule', ph.get('ruleVersion'), ph)
chk('phase discloses thresholds as a product rule', ph.get('thresholds'), ph)
chk('phase states what would invalidate it or why it is unknown',
    bool(ph.get('invalidation')) or ph.get('phase') == 'UNKNOWN', ph)
chk('phase excludes turnover from the classification',
    any('turnover' in l.lower() for l in (ph.get('limitations') or []))
    or ph.get('phase') == 'UNKNOWN', ph.get('limitations'))

vol = ms.get('spotVolumeShares') or {}
w = vol.get('windows') or {}
chk('all three volume windows are present', set(w.keys()) == {'24h', '7d', '30d'}, list(w.keys()))
for name in ('24h', '7d', '30d'):
    win = w.get(name) or {}
    ok_shares = (win.get('btcShare') is None and win.get('altShare') is None) or (
        abs(float(win['btcShare']) + float(win['altShare']) - 1.0) < 1e-6)
    chk('%s shares sum to 1 or are honestly absent' % name, ok_shares, win)
    chk('%s reports its own coverage' % name,
        'daysCovered' in win and 'daysRequired' in win, win)
    chk('%s never reports 0%%/100%% for a missing denominator' % name,
        not (win.get('status') == 'MISSING' and win.get('btcShare') is not None), win)
chk('multi-day windows disclose they are daily samples',
    any('daily sample' in l.lower() for l in ((w.get('7d') or {}).get('limitations') or []))
    or (w.get('7d') or {}).get('status') == 'MISSING', (w.get('7d') or {}).get('limitations'))

parts = {p['participant']: p for p in ((ms.get('participants') or {}).get('participants') or [])}
chk('all five participant cohorts are reported',
    set(parts.keys()) == {'ETFs', 'Institutions', 'Whales', 'Miners', 'Retail'}, list(parts))
chk('miners honestly report no coverage',
    (parts.get('Miners') or {}).get('status') == 'UNSUPPORTED'
    and (parts.get('Miners') or {}).get('reasonCode') == 'NO_MINER_HOLDINGS_COVERAGE',
    parts.get('Miners'))
chk('whale intent is UNKNOWN, not inferred as buying',
    (parts.get('Whales') or {}).get('kind') in ('OBSERVED_FACT', 'UNKNOWN')
    and 'intent' in str(parts.get('Whales')).lower(), parts.get('Whales'))
chk('ETF evidence is REPORTED with a named reporting period',
    (parts.get('ETFs') or {}).get('kind') in ('REPORTED_FACT', 'UNKNOWN')
    and ((parts.get('ETFs') or {}).get('sourcePeriod') or
         (parts.get('ETFs') or {}).get('status') == 'MISSING'), parts.get('ETFs'))
chk('institutions warn against double-counting ETF flows',
    'must not be added together' in ((parts.get('Institutions') or {}).get('limitation') or '')
    or (parts.get('Institutions') or {}).get('status') == 'MISSING', parts.get('Institutions'))
chk('retail is INFERRED from named proxies, not presented as flow',
    (parts.get('Retail') or {}).get('kind') in ('INFERRED', 'UNKNOWN'), parts.get('Retail'))

secs = ms.get('sectors') or {}
chk('sectors are versioned and disclose taxonomy coverage',
    secs.get('ruleVersion') and len(secs.get('limitations') or []) >= 2, secs.get('limitations'))
chk('a one-token sector is labelled CONCENTRATED, not leading',
    all((not s.get('concentrated')) or s.get('label') == 'CONCENTRATED'
        for s in (secs.get('sectors') or [])),
    [(s['sector'], s['label'], s['concentrated']) for s in (secs.get('sectors') or [])])

rf = ms.get('researchFindings') or {}
chk('research findings honestly report the gap instead of recycling news',
    rf.get('status') == 'UNSUPPORTED' and not rf.get('findings'), rf)

caps = ms.get('capabilities') or {}
chk('research, forecast and paper-execution capability are reported separately',
    all(k in caps for k in ('research', 'forecast', 'paperExecution')), list(caps))

print('\n== N-B scenario provider ==')
sc, cap = get('/v1/albert/scenario-outlooks/capability')
chk('provider is registered with a model version',
    cap.get('providerRegistered') and cap.get('modelVersion'), cap)
chk('capability declares the features and minimum sample',
    cap.get('features') and cap.get('minimumSample'), cap)
chk('capability states the phase lens is not a model input',
    (cap.get('phaseConditioning') or {}).get('supported') is False, cap.get('phaseConditioning'))

sc, o = post('/v1/albert/scenario-outlooks/preview', {'assetId': 'BTC', 'horizon': 'P7D'})
chk('BTC preview succeeds', sc == 200 and o.get('meta', {}).get('status') == 'FRESH', (sc, o.get('meta')))
chk('history is real observed candles', len(o.get('history') or []) > 30, len(o.get('history') or []))
chk('both paths are returned', len(o.get('scenarios') or []) == 2,
    [s['side'] for s in (o.get('scenarios') or [])])
base = o.get('baseline') or {}
chk('a shared anchor price and source time are present',
    base.get('price') and base.get('observedAt'), base)
if len(o.get('scenarios') or []) == 2:
    bull = [s for s in o['scenarios'] if s['side'] == 'BULLISH'][0]
    bear = [s for s in o['scenarios'] if s['side'] == 'BEARISH'][0]
    chk('both paths start from the same anchor day',
        bull['points'][0]['time'] == bear['points'][0]['time'],
        (bull['points'][0]['time'], bear['points'][0]['time']))
    chk('path length matches the horizon',
        len(bull['points']) == o['horizonDays'] == 7, len(bull['points']))
    chk('future times strictly increase',
        all(bull['points'][i]['time'] < bull['points'][i + 1]['time']
            for i in range(len(bull['points']) - 1)), 'non-monotonic times')
    chk('bullish endpoint is above bearish endpoint',
        float(bull['endpoint']['price']) > float(bear['endpoint']['price']),
        (bull['endpoint'], bear['endpoint']))
    chk('no calibrated probability is asserted',
        bull.get('probability') is None and bear.get('probability') is None, 'probability present')
    chk('uncertainty is labelled a spread of past outcomes, not a confidence interval',
        'NOT a confidence interval' in (bull.get('uncertainty') or {}).get('details', ''),
        bull.get('uncertainty'))
    chk('each path states what would invalidate it', len(bull.get('invalidation') or []) >= 2, bull)
    chk('model inputs and context-only drivers are distinguished',
        any(d['use'] == 'MODEL_INPUT' for d in bull['drivers'])
        and any(d['use'] == 'CONTEXT_ONLY' for d in bull['drivers']),
        [(d['driverId'], d['use']) for d in bull['drivers']])

samp = o.get('sample') or {}
chk('matched sample size and independent episodes are both disclosed',
    samp.get('sampleSize') and samp.get('independentEpisodes'), samp)
chk('the candidate pool is a multi-year record', (samp.get('candidatePool') or 0) > 1000, samp)

val = o.get('validation') or {}
chk('the response carries the model\u2019s own walk-forward verdict', val.get('status'), val)
chk('an unvalidated model is NOT labelled a forecast',
    val.get('predictiveValidation') is True or 'NOT A FORECAST' in (val.get('headline') or ''),
    val.get('headline'))
chk('the label requirement matches the validation state',
    (val.get('labelRequirement') == 'Conditional historical scenario')
    == (not val.get('predictiveValidation')), val)

print('\n== N-B honesty guarantees ==')
sc, o2 = post('/v1/albert/scenario-outlooks/preview', {'assetId': 'NOTACOIN', 'horizon': 'P7D'})
chk('an unsupported asset returns unavailable',
    o2.get('meta', {}).get('reasonCode') == 'NO_OBSERVED_HISTORY', o2.get('meta'))
chk('an unsupported asset gets NO paths and NO BTC substitution',
    not o2.get('scenarios') and not o2.get('history') and o2.get('assetId') == 'NOTACOIN', o2.get('assetId'))

sc, r = post('/v1/albert/scenario-outlooks/preview',
             {'assetId': 'BTC', 'horizon': 'P7D', 'phaseMode': 'ASSESSED',
              'phaseOverride': 'ALTCOIN_LED'})
chk('an override with phaseMode=ASSESSED is rejected', sc == 422, (sc, r))
sc, r = post('/v1/albert/scenario-outlooks/preview', {'assetId': 'BTC', 'horizon': 'P99D'})
chk('an unsupported horizon is rejected', sc == 422, (sc, r))
sc, r = post('/v1/albert/scenario-outlooks/preview',
             {'assetId': 'BTC', 'horizon': 'P7D', 'phaseMode': 'WHAT_IF',
              'phaseOverride': 'ALTCOIN_LED'})
chk('a what-if lens is accepted', sc == 200, (sc, r.get('meta')))
chk('the what-if lens does NOT overwrite the assessed phase',
    (r.get('phase') or {}).get('applied') == 'ALTCOIN_LED'
    and (r.get('phase') or {}).get('assessed') != 'ALTCOIN_LED'
    or (r.get('phase') or {}).get('assessed') == 'ALTCOIN_LED', r.get('phase'))
chk('the what-if lens admits it was not numerically evaluated',
    (r.get('phase') or {}).get('assumptionEvaluated') is False, r.get('phase'))
chk('the selection key binds asset, quote, horizon, mode and override',
    all(t in (r.get('selectionKey') or '') for t in ('BTC', 'USD', 'P7D', 'WHAT_IF', 'ALTCOIN_LED')),
    r.get('selectionKey'))

sc, ev = get('/v1/albert/scenario-outlooks/evaluation?assetId=BTC&horizon=P7D')
res = (ev.get('result') or {}) if ev.get('status') == 'ready' else {}
chk('walk-forward evaluation is available or honestly computing',
    ev.get('status') in ('ready', 'computing'), ev.get('status'))
if res.get('ok'):
    chk('evaluation is compared against a no-change baseline',
        res.get('baselineMedianAbsErrorPct') is not None, res)
    chk('evaluation reports regime coverage and sample size',
        res.get('regimeCoverage') and res.get('evaluationPoints'), res)

print('\n== state-of-play integration ==')
sc, sop = get('/v1/albert/state-of-play')
chk('state-of-play carries the market stream facts', bool(sop.get('marketStreams')), list(sop))
chk('state-of-play carries capability truth', bool(sop.get('capabilities')), list(sop))
chk('state-of-play carries the aggregate across strategy wallets',
    bool((sop.get('paperAggregate') or {}).get('totals')), (sop.get('paperAggregate') or {}).get('totals'))
chk('the aggregate explains there is no shared account to select',
    'no shared paper' in ((sop.get('paperAggregate') or {}).get('note') or '').lower(),
    (sop.get('paperAggregate') or {}).get('note'))

print('\n== %d passed, %d failed ==' % (len(PASS), len(FAIL)))
if FAIL:
    print('FAILED: ' + ', '.join(FAIL))
sys.exit(1 if FAIL else 0)
