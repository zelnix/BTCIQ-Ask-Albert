"""Who is moving the market - participant cohorts, with their evidence limits intact.

"Who is leading" means market PARTICIPANTS, not whichever token happens to be up. Five
cohorts are reported, and each one is allowed to say it does not know.

The discipline that matters here:
  * A wallet transfer is not a purchase. Balance changes are OBSERVED; intent is UNKNOWN.
  * ETF flows and derivatives positioning are NOT two independent institutional signals -
    double-counting them would manufacture agreement that does not exist.
  * Daily-reported evidence is never dressed up as live.
  * No cohort is given a "percentage of market control", and overlapping cohorts are
    never summed.
  * Miner holdings have no coverage in this system, so that row returns UNKNOWN rather
    than a proxy pretending to be a measurement.
"""
from albert.market import meta as M

PARTICIPANTS_RULE_VERSION = 'participants-v1'
NON_CUSTODIAL_WHALE_CATEGORIES = ('Whale', 'Individual', 'Unknown', 'Government', 'Miner')
RETAIL_FLOW_OBSERVATIONS = 20   # trailing on-chain balance observations for the proxy


def _row(participant, *, finding, kind, status, source_period=None, as_of=None,
         limitation=None, evidence_refs=None, reason_code=None, detail=None):
    return {'participant': participant, 'finding': finding, 'kind': kind,
            'status': status, 'sourcePeriod': source_period, 'asOf': as_of,
            'limitation': limitation, 'reasonCode': reason_code,
            'evidenceRefs': list(evidence_refs or []), 'detail': detail or {}}


def _etfs(etf):
    if not etf or etf.get('status') != 'ready' or not (etf.get('daily') or []):
        return _row('ETFs', finding='US spot ETF flow reporting is not available right now.',
                    kind=M.UNKNOWN_KIND, status=M.MISSING, reason_code='NO_ETF_FEED',
                    limitation='The flow provider returned nothing, so no ETF conclusion '
                               'can be drawn either way.')
    daily = etf['daily']
    latest = daily[0]
    total = latest.get('total')
    if total is None:
        return _row('ETFs', finding='The latest ETF reporting day has no usable total.',
                    kind=M.UNKNOWN_KIND, status=M.PARTIAL, reason_code='ETF_TOTAL_MISSING',
                    limitation='Per-issuer rows were present but the day total was absent.')
    sign = 1 if total > 0 else (-1 if total < 0 else 0)
    streak = 0
    for d in daily:
        t = d.get('total')
        if t is None or (1 if t > 0 else (-1 if t < 0 else 0)) != sign or sign == 0:
            break
        streak += 1
    flows = latest.get('flows') or {}
    movers = sorted(((k, v) for k, v in flows.items() if v), key=lambda kv: -abs(kv[1]))[:3]
    word = 'net inflows' if sign > 0 else ('net outflows' if sign < 0 else 'no net flow')
    finding = ('US spot Bitcoin ETFs reported %s of $%.1fm on %s%s.'
               % (word, abs(total), latest.get('date'),
                  '' if streak <= 1 else ', the %s consecutive reporting day in that direction' % _ord(streak)))
    if movers:
        finding += ' Largest contributors: %s.' % ', '.join(
            '%s $%.1fm' % (k, v) for k, v in movers)
    return _row('ETFs', finding=finding, kind=M.REPORTED_FACT, status=M.FRESH,
                source_period='Reporting day %s (daily, published with a lag)' % latest.get('date'),
                as_of=latest.get('date'),
                limitation='Issuer coverage is limited to the %d funds this provider tracks '
                           '(%s) and flows are reported daily - they are not live and must '
                           'not be read sub-daily.'
                           % (len(etf.get('issuers') or []), ', '.join((etf.get('issuers') or [])[:6])),
                evidence_refs=[M.evidence_ref('etf', latest.get('date'), total)],
                detail={'netFlowUsdMillions': total, 'consecutiveDays': streak,
                        'unit': etf.get('unit'), 'reportingDate': latest.get('date')})


def _ord(n):
    return {1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth'}.get(n, '%dth' % n)


def _institutions(lev):
    if not lev or lev.get('status') != 'ready':
        return _row('Institutions', finding='No institutional positioning evidence is available.',
                    kind=M.UNKNOWN_KIND, status=M.MISSING, reason_code='NO_POSITIONING_FEED',
                    limitation='Reported exposure feeds were unavailable.')
    pos = lev.get('positioning') or {}
    oi = lev.get('open_interest') or {}
    fund = lev.get('funding') or {}
    long_pct = pos.get('long_pct')
    oi_usd = oi.get('value_usd')
    oi_chg = oi.get('change_tf_pct')
    if long_pct is None and oi_usd is None:
        return _row('Institutions', finding='Positioning was returned but is empty.',
                    kind=M.UNKNOWN_KIND, status=M.PARTIAL, reason_code='POSITIONING_EMPTY',
                    limitation='Neither account positioning nor open interest was usable.')
    bits = []
    if long_pct is not None:
        bits.append('%.1f%% of tracked accounts are positioned long (%s)'
                    % (long_pct, (pos.get('trend') or 'trend unknown').lower()))
    if oi_usd is not None:
        bits.append('open interest is $%.2fbn%s'
                    % (oi_usd / 1e9,
                       '' if oi_chg is None else ' (%+.1f%% over the timeframe)' % oi_chg))
    if fund.get('rate') is not None:
        bits.append('funding is %.4f%% (%s)' % (fund['rate'], (fund.get('bias') or 'neutral').lower()))
    venues = [e.get('name') for e in (fund.get('exchanges') or []) if e.get('name')]
    return _row('Institutions', finding='On the venues tracked, ' + '; '.join(bits) + '.',
                kind=M.REPORTED_FACT, status=M.FRESH,
                source_period='%s timeframe, as of %s' % (lev.get('timeframe'), lev.get('as_of')),
                as_of=lev.get('as_of'),
                limitation='This is exchange-reported DERIVATIVES positioning from a narrow '
                           'venue set (%s), not measured institutional spot exposure, and '
                           'reported filings lag. ETF flows are the same participant story '
                           'seen from a different feed - the two must not be added together '
                           'as independent institutional demand.'
                           % (', '.join(venues) or 'venue list unavailable'),
                evidence_refs=[M.evidence_ref('positioning', lev.get('as_of'), long_pct, oi_usd)],
                detail={'longPct': long_pct, 'shortPct': pos.get('short_pct'),
                        'openInterestUsd': oi_usd, 'openInterestChangePct': oi_chg,
                        'fundingRate': fund.get('rate'), 'venues': venues})


def _whales(wh):
    whales = (wh or {}).get('whales') or []
    if not whales:
        return _row('Whales', finding='Large-holder balances are not available right now.',
                    kind=M.UNKNOWN_KIND, status=M.MISSING, reason_code='NO_WHALE_FEED',
                    limitation='The labelled large-holder feed returned nothing.')
    moved = [w for w in whales if (w.get('change_7d') or 0) != 0]
    cust_delta = sum((w.get('change_7d') or 0) for w in whales
                     if (w.get('category') or '') not in NON_CUSTODIAL_WHALE_CATEGORIES)
    own_delta = sum((w.get('change_7d') or 0) for w in whales
                    if (w.get('category') or '') in NON_CUSTODIAL_WHALE_CATEGORIES)
    top = sorted(moved, key=lambda w: -abs(w.get('change_7d') or 0))[:3]
    if not moved:
        finding = ('None of the %d labelled large holders changed balance over the last 7 '
                   'days of observations.' % len(whales))
        status = M.FRESH
    else:
        finding = ('%d of %d labelled large holders changed balance over 7 days: custody and '
                   'exchange entities %+.0f BTC, non-custodial holders %+.0f BTC.'
                   % (len(moved), len(whales), cust_delta, own_delta))
        if top:
            finding += ' Largest movements: %s.' % ', '.join(
                '%s %+.0f BTC' % (w.get('name'), w.get('change_7d') or 0) for w in top)
        status = M.FRESH
    return _row('Whales', finding=finding, kind=M.OBSERVED_FACT, status=status,
                source_period='Rolling 7-day balance change from on-chain observations',
                as_of=(whales[0] or {}).get('updated'),
                limitation='Balances are observed; INTENT IS NOT. A transfer is not '
                           'automatically a purchase or a sale, exchange and custody '
                           'addresses represent many underlying owners, and only publicly '
                           'labelled addresses are covered - unlabelled holders are invisible.',
                evidence_refs=[M.evidence_ref('whales', (whales[0] or {}).get('updated'), len(moved))],
                detail={'holdersTracked': len(whales), 'holdersMoved': len(moved),
                        'custodialDelta7dBtc': round(cust_delta, 2),
                        'nonCustodialDelta7dBtc': round(own_delta, 2),
                        'intent': 'UNKNOWN'})


def _miners(net):
    hashrate = (net or {}).get('hashrate') or (net or {}).get('hashrate_eh')
    detail = {'hashrate': hashrate} if hashrate else {}
    return _row('Miners', finding='Albert cannot assess miner behaviour: this system has no '
                                  'miner wallet classification or miner flow coverage.',
                kind=M.UNKNOWN_KIND, status=M.UNSUPPORTED,
                reason_code='NO_MINER_HOLDINGS_COVERAGE',
                source_period=None,
                limitation='Network hashrate is available as context but it is not evidence '
                           'of miner holdings or distribution, so no miner conclusion is '
                           'offered rather than inferring one from an unrelated metric.',
                detail=detail)


def _retail(fg, xflows):
    parts, refs, status = [], [], M.MISSING
    val = (fg or {}).get('value')
    if val is not None:
        wk = (fg or {}).get('week_ago')
        parts.append('the Fear & Greed index reads %d (%s)%s'
                     % (val, (fg or {}).get('label') or 'unlabelled',
                        '' if wk is None else ', against %d a week ago' % wk))
        refs.append(M.evidence_ref('feargreed', (fg or {}).get('ts'), val))
        status = M.FRESH
    series = (xflows or {}).get('series') or []
    # Bound the proxy to a RECENT window and state the span. Comparing the first and
    # last points of a multi-year series would dress up a historical drift as a
    # current retail signal.
    window = series[-RETAIL_FLOW_OBSERVATIONS:] if len(series) >= 2 else []
    if len(window) >= 2:
        first, last = window[0], window[-1]
        delta = (last.get('balance') or 0) - (first.get('balance') or 0)
        parts.append('tracked exchange balances moved %+.0f BTC across the last %d '
                     'observations (%s to %s)'
                     % (delta, len(window), first.get('date'), last.get('date')))
        refs.append(M.evidence_ref('exchflows', last.get('date'), round(delta, 1)))
        status = M.FRESH if status == M.FRESH else M.PARTIAL
    if not parts:
        return _row('Retail', finding='No usable retail proxy is available right now.',
                    kind=M.UNKNOWN_KIND, status=M.MISSING, reason_code='NO_RETAIL_PROXY',
                    limitation='Both the sentiment index and the exchange-balance proxy '
                               'were unavailable.')
    return _row('Retail', finding='Using defined proxies, ' + '; '.join(parts) + '.',
                kind='INFERRED', status=status,
                source_period='Sentiment index: daily. Exchange balances: irregular '
                              'on-chain observations.',
                as_of=(window[-1].get('date') if window else None),
                limitation='These are PROXIES, not capital flow. A sentiment index and an '
                           'aggregate exchange balance do not measure smaller investors '
                           'buying or selling, and neither one can be attributed to retail '
                           'with certainty.',
                evidence_refs=refs,
                detail={'fearGreed': val, 'fearGreedLabel': (fg or {}).get('label')})


def assess(*, etf=None, leverage=None, whales=None, network=None, fear_greed=None,
           exchange_flows=None):
    """Build all five cohort rows. Every input is optional; a missing input degrades one
    row and leaves the rest intact."""
    rows = [_etfs(etf), _institutions(leverage), _whales(whales), _miners(network),
            _retail(fear_greed, exchange_flows)]
    known = [r for r in rows if r['status'] in (M.FRESH, M.PARTIAL)]
    return {'ruleVersion': PARTICIPANTS_RULE_VERSION,
            'status': M.FRESH if len(known) == len(rows) else (M.PARTIAL if known else M.MISSING),
            'cohortsReported': len(known), 'cohortsTotal': len(rows),
            'participants': rows,
            'limitations': ['Cohorts overlap and are never summed; no cohort is assigned a '
                            'share of market control.',
                            'Each row carries its own evidence class and reporting period - '
                            'they are not comparable on a single confidence scale.']}
