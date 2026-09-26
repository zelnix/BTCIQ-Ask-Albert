"""N-C / N-D / N-E / N-F acceptance harness (live, unmocked).

Checks the properties the two-stream dashboard specification cares about most:

  * the headline band comes from ONE immutable provider snapshot and is suppressed
    entirely when the band is not calibrated;
  * the middle path is never presented as a forecast;
  * market leadership is observed and read-only, no longer a what-if control;
  * research findings are real hypotheses with confirm/invalidate conditions, a horizon
    and an outcome history - and miners stay explicitly unsupported;
  * every statement resolves to the exact snapshot it was made from, owner-scoped;
  * the preview mutates nothing.
"""
import json
import os
import sys
import time
import uuid

import requests

BASE = os.environ.get('NC_BASE', 'http://localhost:8001/api')
TOKEN = os.environ.get('NC_TOKEN', 'sop_e2e_session_token_0001')
S = requests.Session()
S.headers.update({'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
PASS, FAIL = [], []


def chk(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print(('  PASS  ' if cond else '  FAIL  ') + name
          + ((' :: ' + str(extra)[:300]) if extra and not cond else ''))


def get(p, timeout=180):
    r = S.get(BASE + p, timeout=timeout)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa
        return r.status_code, {'raw': r.text[:300]}


def post(p, b=None, timeout=180):
    r = S.post(BASE + p, data=json.dumps(b or {}), timeout=timeout)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa
        return r.status_code, {'raw': r.text[:300]}


# Stream 1 is measured in a background warmer by design. Wait for a real reading rather
# than asserting against a cold start.
print('== warming stream 1 ==')
streams = {}
for attempt in range(12):
    sc, streams = get('/v1/albert/market-streams')
    if sc == 200 and (streams.get('phaseAssessment') or {}).get('phase') not in (None, 'UNKNOWN'):
        break
    time.sleep(10)
print('   phase =', (streams.get('phaseAssessment') or {}).get('phase'),
      '| universe =', (streams.get('universe') or {}).get('status'))

print('== N-C scenario band contract ==')
sc, o = post('/v1/albert/scenario-outlooks/preview', {'assetId': 'BTC', 'horizon': 'P7D'})
chk('preview 200', sc == 200, (sc, o))
band = (o or {}).get('band') or {}
chk('band block present', bool(band), o)
chk('band carries an immutable snapshot id', str(band.get('snapshotId') or '').startswith('snap_'), band)
chk('band evidence deep link points at the same snapshot',
    band.get('snapshotId') and band.get('snapshotId') in str(band.get('evidenceDeepLink')), band)
chk('outlook snapshotId equals the band snapshotId',
    o.get('snapshotId') == band.get('snapshotId'), (o.get('snapshotId'), band.get('snapshotId')))

if band.get('available'):
    lo, hi, hz = band.get('lowerPct'), band.get('upperPct'), band.get('horizonDays')
    chk('lower bound is below the upper bound', lo is not None and hi is not None and lo < hi, band)
    chk('horizon days match the requested horizon', hz == 7, hz)
    chk('statement is built from the same bounds',
        band.get('statement') == ('Comparable past conditions produced %+.1f%% to %+.1f%% over %d days.'
                                  % (lo, hi, hz)), band.get('statement'))
    chk('band label is the required not-a-forecast label',
        band.get('label') == 'Historical scenario range — not a forecast', band.get('label'))
    chk('median path has one point per horizon day', len(band.get('medianPath') or []) == hz,
        len(band.get('medianPath') or []))
    chk('median is labelled as a historical median, not an expectation',
        'median path from matched periods' in str(band.get('medianLabel')).lower(),
        band.get('medianLabel'))
    chk('median caveat states it carries no measured skill',
        'no measured skill' in str(band.get('medianCaveat')).lower(), band.get('medianCaveat'))
    chk('percentiles are the 20th and 80th',
        (band.get('percentiles') or {}).get('bearish') == 20
        and (band.get('percentiles') or {}).get('bullish') == 80, band.get('percentiles'))
    chk('predictive validation is NOT claimed', band.get('predictiveValidation') is False, band)
    chk('band calibration is reported separately and is true', band.get('bandCalibrated') is True, band)
    chk('validation headline leads with NOT A FORECAST',
        str(band.get('validationHeadline') or '').startswith('NOT A FORECAST'),
        band.get('validationHeadline'))
    chk('required label is "Conditional historical scenario"',
        band.get('labelRequirement') == 'Conditional historical scenario', band.get('labelRequirement'))
    chk('coverage rate is published', isinstance(band.get('coverageRate'), (int, float)), band)
    chk('evaluation point count is published', (band.get('evaluationPoints') or 0) >= 60, band)
    chk('matched day count is published', (band.get('matchedDays') or 0) >= 40, band)
    chk('distinct episode count is published alongside the day count',
        (band.get('independentEpisodes') or 0) > 0, band)
    chk('no probability is asserted on either side',
        all(s.get('probability') is None for s in (o.get('scenarios') or [])), o.get('scenarios'))
    chk('band edge prices bracket the anchor price',
        float(band['lowerPrice']) < float(band['anchorPrice']) < float(band['upperPrice']), band)
else:
    chk('unavailable band names a reason code', bool(band.get('reasonCode')), band)
    chk('unavailable band suppresses every figure',
        band.get('lowerPct') is None and band.get('upperPct') is None
        and band.get('medianPct') is None, band)

print('== N-C market leadership is read-only, not a control ==')
ph = (o or {}).get('phase') or {}
chk('leadership block is flagged read-only', ph.get('readOnly') is True, ph)
chk('leadership is NOT offered as a control', ph.get('controlOffered') is False, ph)
chk('a retired-lens reason code is given',
    ph.get('controlReasonCode') == 'PHASE_LENS_RETIRED_AS_CONTROL', ph)
chk('leadership is labelled a market leadership assessment',
    ph.get('label') == 'Market leadership assessment', ph)
chk('the assessed phase is a real value', ph.get('assessed') in
    ('BTC_LED', 'ALTCOIN_LED', 'MIXED', 'UNKNOWN'), ph)
sc, r = post('/v1/albert/scenario-outlooks/preview',
             {'assetId': 'BTC', 'horizon': 'P7D', 'phaseMode': 'ASSESSED',
              'phaseOverride': 'BTC_LED'})
chk('an override on the assessed mode is still rejected 422', sc == 422, (sc, r))

print('== N-C atomic selection ==')
sc, o14 = post('/v1/albert/scenario-outlooks/preview', {'assetId': 'ETH', 'horizon': 'P14D'})
chk('a different asset and horizon answer 200', sc == 200, sc)
chk('selection key binds asset, quote, horizon and mode',
    str(o14.get('selectionKey', '')).startswith('ETH|USD|P14D|ASSESSED|'), o14.get('selectionKey'))
chk('the response asset matches the request', o14.get('assetId') == 'ETH', o14.get('assetId'))
chk('horizon days follow the requested horizon', o14.get('horizonDays') == 14, o14.get('horizonDays'))
if (o14.get('band') or {}).get('available') and band.get('available'):
    chk('a different selection produces a different snapshot',
        o14['band']['snapshotId'] != band['snapshotId'],
        (o14['band']['snapshotId'], band['snapshotId']))
sc, bad = post('/v1/albert/scenario-outlooks/preview', {'assetId': 'NOTACOIN', 'horizon': 'P7D'})
chk('an unsupported asset answers 200 with an explicit gap', sc == 200, sc)
chk('an unsupported asset returns no scenario path', (bad.get('scenarios') or []) == [], bad.get('scenarios'))
chk('an unsupported asset never substitutes BTC', bad.get('assetId') == 'NOTACOIN'
    and not bad.get('history'), bad.get('assetId'))
chk('an unsupported asset publishes no band figures',
    (bad.get('band') or {}).get('available') is False
    and (bad.get('band') or {}).get('lowerPct') is None, bad.get('band'))

print('== N-D two-stream state of play ==')
sc, sop = get('/v1/albert/state-of-play')
chk('state of play 200', sc == 200, sc)
br = (sop or {}).get('briefing') or {}
claims = br.get('claims') or []
chk('the briefing is composed of bound claims', len(claims) >= 3, len(claims))
chk('every claim declares a knowledge kind',
    all(c.get('kind') in ('OBSERVED_FACT', 'REPORTED_FACT', 'SYSTEM_ASSESSMENT',
                          'ALBERT_INTERPRETATION', 'WHAT_IF_ASSUMPTION', 'UNKNOWN')
        for c in claims), [c.get('kind') for c in claims])
chk('every claim links to an immutable snapshot',
    all(any(str(r).startswith('snap_') for r in (c.get('evidenceRefs') or []))
        for c in claims), [c.get('evidenceRefs') for c in claims])
chk('every claim deep link addresses its snapshot',
    all('evidence=snap_' in str(c.get('deepLink')) for c in claims),
    [c.get('deepLink') for c in claims])
chk('the aggregate across ring-fenced wallets is present',
    bool(((sop.get('paperAggregate') or {}).get('totals'))), sop.get('paperAggregate'))
chk('the aggregate explains that there is no shared account to select',
    'ring-fenced' in str((sop.get('paperAggregate') or {}).get('note')),
    (sop.get('paperAggregate') or {}).get('note'))
chk('capabilities still report research, forecast and paper execution separately',
    all(k in (sop.get('capabilities') or {}) for k in ('research', 'forecast', 'paperExecution')),
    list((sop.get('capabilities') or {}).keys()))

print('== N-D stream 1 sections each carry provenance ==')
# Re-read Stream 1 immediately before the section checks: the warm loop above only waits
# for a leadership reading, and the optional feeds can land a beat later.
for _ in range(6):
    _sc, _fresh = get('/v1/albert/market-streams')
    if _sc == 200 and (((_fresh.get('spotVolumeShares') or {}).get('windows') or {})
                       .get('24h') or {}).get('status') in ('FRESH', 'PARTIAL'):
        streams = _fresh
        break
    time.sleep(10)

for name in ('direction', 'phaseAssessment', 'spotVolumeShares', 'sectors', 'participants'):
    sect = streams.get(name) or {}
    chk('%s carries a snapshot id' % name,
        str(sect.get('snapshotId') or '').startswith('snap_'), sect.get('snapshotId'))
vol = streams.get('spotVolumeShares') or {}
w24 = (vol.get('windows') or {}).get('24h') or {}
w7 = (vol.get('windows') or {}).get('7d') or {}
w30 = (vol.get('windows') or {}).get('30d') or {}
chk('the 24h turnover window is measured', w24.get('status') in ('FRESH', 'PARTIAL'), w24.get('status'))
chk('the 7d window is honestly PARTIAL with its coverage named',
    w7.get('status') == 'PARTIAL' and w7.get('daysCovered') is not None
    and w7.get('daysRequired') == 7, w7)
chk('the 30d window is honestly PARTIAL with its coverage named',
    w30.get('status') == 'PARTIAL' and w30.get('daysRequired') == 30, w30)
sec = streams.get('sectors') or {}
conc = [s for s in (sec.get('sectors') or []) if s.get('concentrated')]
if conc:
    lim = str(conc[0].get('limitation') or '')
    chk('a concentrated sector states its concentration as a real percentage',
        '%' in lim and not lim.startswith('Turnover is 0.'), lim)
    chk('a concentrated sector is never labelled leading',
        'LEADING' not in str(conc[0].get('label', '')).upper(), conc[0].get('label'))
parts = streams.get('participants') or {}
miners = [p for p in (parts.get('participants') or []) if p.get('participant') == 'Miners']
chk('miners remain explicitly unsupported',
    (not miners) or miners[0].get('status') == 'UNSUPPORTED', miners)

print('== N-E research findings ==')
sc, rf = get('/v1/albert/research-findings')
chk('research findings 200', sc == 200, sc)
chk('research findings are no longer unsupported', rf.get('status') != 'UNSUPPORTED', rf.get('status'))
findings = rf.get('findings') or []
chk('at least three findings are surfaced', len(findings) >= 3, len(findings))
valid_pri = {'AVOID_FOR_NOW', 'CONSIDER_PAPER_TEST', 'INVESTIGATE', 'WATCH', 'INSUFFICIENT_EVIDENCE'}
chk('every finding uses the declared priority ladder',
    all(f.get('priority') in valid_pri for f in findings), [f.get('priority') for f in findings])
chk('findings are ordered highest priority first',
    [f.get('priority') for f in findings]
    == sorted((f.get('priority') for f in findings),
              key=lambda p: ['AVOID_FOR_NOW', 'CONSIDER_PAPER_TEST', 'INVESTIGATE',
                             'WATCH', 'INSUFFICIENT_EVIDENCE'].index(p)),
    [f.get('priority') for f in findings])
hyp = [f for f in findings if f.get('status') == 'OPEN']
chk('open findings exist', len(hyp) >= 2, len(hyp))
chk('every open finding declares a confirm condition', all(f.get('confirmIf') for f in hyp), hyp[:1])
chk('every open finding declares an invalidate condition', all(f.get('invalidateIf') for f in hyp), hyp[:1])
chk('every open finding declares a horizon', all((f.get('horizonDays') or 0) > 0 for f in hyp), hyp[:1])
chk('every open finding records when it must resolve by', all(f.get('resolveBy') for f in hyp), hyp[:1])
chk('every open finding carries a machine-checkable measure',
    all((f.get('measure') or {}).get('name') for f in hyp), hyp[:1])
chk('every finding links to its supporting snapshot',
    all(str(f.get('snapshotId') or '').startswith('snap_') for f in findings),
    [f.get('snapshotId') for f in findings])
chk('a finding without a falsifiable condition is NOT scored as a hypothesis',
    all(f.get('status') == 'NO_HYPOTHESIS'
        for f in findings if f.get('priority') == 'INSUFFICIENT_EVIDENCE'),
    [(f.get('priority'), f.get('status')) for f in findings])
chk('miner research is reported as insufficient evidence, not inferred',
    any(f.get('key') == 'miner-holdings' and f.get('priority') == 'INSUFFICIENT_EVIDENCE'
        for f in findings), [f.get('key') for f in findings])
chk('a scorecard of resolved outcomes is published', isinstance(rf.get('scorecard'), dict), rf.get('scorecard'))
chk('a confirmation rate is withheld until hypotheses resolve',
    (rf['scorecard'].get('resolved') or 0) > 0 or rf['scorecard'].get('confirmedRate') is None,
    rf.get('scorecard'))
chk('no finding text is attributed to the language model',
    'no text or number here is produced by the language model'
    in ' '.join(rf.get('limitations') or []).lower(), rf.get('limitations'))

if hyp:
    fid = hyp[0]['findingId']
    sc, one = get('/v1/albert/research-findings/%s' % fid)
    chk('a single finding resolves with its full record', sc == 200, (sc, one))
    f1 = (one or {}).get('finding') or {}
    chk('the record carries its observation history', isinstance(f1.get('observations'), list),
        f1.get('observations'))
    chk('the frozen hypothesis is returned, not a rewritten one',
        f1.get('hypothesis') == hyp[0]['hypothesis'], (f1.get('hypothesis'), hyp[0]['hypothesis']))
    chk('the record embeds the snapshot it was opened from', bool(one.get('finding', {}).get('snapshotId')), one)
sc, nf = get('/v1/albert/research-findings/rf_doesnotexist')
chk('an unknown finding id is 404', sc == 404, sc)

print('== N-F evidence resolution and Ask Albert context ==')
if band.get('snapshotId'):
    sc, ev = get('/v1/albert/evidence/%s' % band['snapshotId'])
    chk('the band snapshot resolves', sc == 200, (sc, ev))
    chk('the resolved snapshot is the scenario band', ev.get('kind') == 'scenarioBand', ev.get('kind'))
    chk('the resolved snapshot repeats the SAME bounds the headline used',
        (ev.get('payload') or {}).get('lowerPct') == band.get('lowerPct')
        and (ev.get('payload') or {}).get('upperPct') == band.get('upperPct'),
        (ev.get('payload') or {}).get('lowerPct'))
    chk('a market snapshot is scoped MARKET, not to an owner', ev.get('scope') == 'MARKET', ev.get('scope'))
sc, ev404 = get('/v1/albert/evidence/snap_%s' % uuid.uuid4().hex[:16])
chk('an unknown evidence id is 404', sc == 404, sc)
owner_claim = next((c for c in claims if c.get('claimId') == 'briefing.portfolio'), None)
if owner_claim:
    sid = [r for r in owner_claim['evidenceRefs'] if str(r).startswith('snap_')][-1]
    sc, oev = get('/v1/albert/evidence/%s' % sid)
    chk('an owner snapshot resolves for its owner', sc == 200, sc)
    chk('an owner snapshot is scoped OWNER', oev.get('scope') == 'OWNER', oev.get('scope'))

print('== N-F the preview mutates nothing ==')
sc, ov1 = get('/v1/albert/paper/overview')
before = json.dumps((ov1 or {}).get('totals'))
for _ in range(2):
    post('/v1/albert/scenario-outlooks/preview', {'assetId': 'BTC', 'horizon': 'P30D'})
get('/v1/albert/research-findings')
sc, ov2 = get('/v1/albert/paper/overview')
chk('no proposal, order or wallet change results from previewing',
    json.dumps((ov2 or {}).get('totals')) == before,
    (before, json.dumps((ov2 or {}).get('totals'))))

print('== N-F Ask Albert accepts a bounded, re-resolved context ==')
sc, ans = post('/v1/albert/ask',
               {'message': 'What does this scenario range mean for me?',
                'session_id': 'nc_test_' + uuid.uuid4().hex[:6],
                'context': {'snapshotId': band.get('snapshotId'), 'stateId': sop.get('stateId')}},
               timeout=180)
if sc == 200 and ans.get('status') == 'ready':
    chk('the answer confirms the context was resolved server-side',
        ans.get('resolvedContext') is True, ans)
    chk('the answer is bound to its own evidence snapshot',
        str(ans.get('answerSnapshotId') or '').startswith('snap_'), ans.get('answerSnapshotId'))
    chk('the scenario band was consulted as a read function',
        any('scenario' in str(x) for x in (ans.get('contextFunctions') or [])),
        ans.get('contextFunctions'))
    if ans.get('answerSnapshotId'):
        sc2, aev = get('/v1/albert/evidence/%s' % ans['answerSnapshotId'])
        chk('the answer evidence set resolves for its owner', sc2 == 200, sc2)
        chk('the answer evidence set is owner-scoped', aev.get('scope') == 'OWNER', aev.get('scope'))
else:
    print('  SKIP  Ask Albert turn (model not configured here): %s %s'
          % (sc, str(ans)[:120]))

sc, ans2 = post('/v1/albert/ask',
                {'message': 'Summarise my state.', 'session_id': 'nc_test_ctx',
                 'context': {'snapshotId': 'snap_notarealsnapshotid'}}, timeout=180)
if sc == 200 and ans2.get('status') == 'ready':
    chk('an unknown context id does not leak or fabricate a record',
        not any(e.get('sourceId') == 'snap_notarealsnapshotid' for e in (ans2.get('evidence') or [])),
        ans2.get('evidence'))

print('\n== summary ==')
print('PASS %d  FAIL %d' % (len(PASS), len(FAIL)))
if FAIL:
    print('failed:')
    for f in FAIL:
        print('  -', f)
sys.exit(1 if FAIL else 0)
