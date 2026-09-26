"""The documented market universe - one definition, versioned, used by every share and
phase calculation so two panels can never quietly disagree about what "the market" is.

It is built from the existing top-100 market-cap Discovery snapshot (CoinGecko), then
filtered. The filters matter more than the ranking:

  * Stablecoins are excluded from BOTH buckets. A stablecoin used as a quote asset is
    not a third kind of volume, and its turnover is not a directional market opinion.
  * Wrapped and liquid-staking derivatives are excluded because their turnover is the
    SAME underlying asset counted a second time.
  * Assets below the liquidity floor are excluded so a thin listing cannot swing a share.

Everything excluded is counted and disclosed - coverage you cannot see is coverage you
cannot trust.
"""
from albert.market import meta as M

UNIVERSE_VERSION = 'market-universe-v1'
LIQUIDITY_MIN_USD = 10_000_000.0
TOP_N = 100

STABLES = {'USDT', 'USDC', 'DAI', 'USD', 'TUSD', 'FDUSD', 'BUSD', 'USDE', 'USDS',
           'PYUSD', 'USDD', 'FRAX', 'LUSD', 'GUSD', 'EURS', 'EURC', 'USD1', 'USDF',
           'RLUSD', 'USDY', 'SUSDE', 'SUSDS', 'USDX', 'BUIDL', 'USTC'}

# Wrapped / staked / restaked representations of an asset already in the universe.
WRAPPED = {'WBTC', 'WETH', 'WBETH', 'STETH', 'WSTETH', 'CBETH', 'RETH', 'WEETH',
           'EZETH', 'RSETH', 'METH', 'SOLVBTC', 'LBTC', 'CBBTC', 'TBTC', 'BTCB',
           'WBNB', 'WHYPE', 'JITOSOL', 'MSOL', 'JUPSOL', 'BSC-USD', 'WSOL',
           'BNSOL', 'STBTC', 'CLBTC', 'SUSDS'}


def _f(v):
    try:
        if v is None:
            return None
        return float(v)
    except Exception:  # noqa
        return None


def build(core):
    """Project a Discovery snapshot into the documented universe.

    Returns a dict with `status`, the BTC row, the eligible altcoin rows, the exclusion
    tally and full provenance. `status` is MISSING when there is no snapshot at all -
    the caller must not invent one.
    """
    if not core or not (core.get('assets') or []):
        return {'status': M.MISSING, 'reasonCode': 'NO_UNIVERSE_SNAPSHOT',
                'universeVersion': UNIVERSE_VERSION, 'btc': None, 'alts': [],
                'excluded': {}, 'snapshotId': None, 'source': None,
                'sourceTimestamp': None, 'count': 0,
                'limitations': ['The market-cap universe snapshot is not available yet.']}

    excluded = {'stablecoin': 0, 'wrapped': 0, 'illiquid': 0, 'incompleteData': 0}
    btc = None
    alts = []
    for a in (core.get('assets') or [])[:TOP_N]:
        sym = (a.get('symbol') or '').upper()
        if not sym:
            continue
        vol = _f(a.get('volume24hUsd'))
        mcap = _f(a.get('marketCapUsd'))
        row = {'symbol': sym, 'name': a.get('name'), 'rank': a.get('rank'),
               'marketCapUsd': mcap, 'priceUsd': _f(a.get('priceUsd')),
               'volume24hUsd': vol,
               'change24hPct': _f(a.get('change24hPct')),
               'change7dPct': _f(a.get('change7dPct')),
               'change30dPct': _f(a.get('change30dPct'))}
        if sym == 'BTC':
            btc = row
            continue
        if sym in STABLES:
            excluded['stablecoin'] += 1
            continue
        if sym in WRAPPED:
            excluded['wrapped'] += 1
            continue
        if vol is None or mcap is None:
            excluded['incompleteData'] += 1
            continue
        if vol < LIQUIDITY_MIN_USD:
            excluded['illiquid'] += 1
            continue
        alts.append(row)

    src_ts = core.get('sourceTimestamp')
    limitations = [
        'Universe is the top %d assets by market capitalisation from a single aggregator '
        '(%s); assets outside it are not measured.' % (TOP_N, core.get('source') or 'unknown'),
        'Stablecoins (%d), wrapped or staked representations (%d), assets below the '
        '$%s 24h liquidity floor (%d) and assets with incomplete data (%d) are excluded '
        'from the altcoin bucket.' % (excluded['stablecoin'], excluded['wrapped'],
                                      format(int(LIQUIDITY_MIN_USD), ','),
                                      excluded['illiquid'], excluded['incompleteData']),
        'The aggregator reports turnover across the venues it tracks; the individual '
        'venue list is not enumerable from this feed, so venue coverage cannot be shown.',
    ]
    return {
        'status': M.FRESH if btc and alts else M.PARTIAL,
        'reasonCode': None if (btc and alts) else 'THIN_UNIVERSE',
        'universeVersion': UNIVERSE_VERSION, 'btc': btc, 'alts': alts,
        'excluded': excluded, 'eligibleAltCount': len(alts),
        'snapshotId': core.get('universeSnapshotId'), 'source': core.get('source'),
        'sourceTimestamp': src_ts, 'count': len(core.get('assets') or []),
        'liquidityMinUsd': LIQUIDITY_MIN_USD, 'limitations': limitations,
        'evidenceRef': M.evidence_ref('universe', UNIVERSE_VERSION,
                                      core.get('universeSnapshotId')),
    }
