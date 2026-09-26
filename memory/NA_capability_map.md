# Phase N-A — Capability map (Package A deliverable)

Honest mapping of the Two-Stream Dashboard spec onto what this repository can actually
do. **Nothing here is marked present because a UI label exists.** Every row was checked
against a live, unmocked response.

Verified on 26 Sep 2026 against `GET /api/v1/albert/market-streams`,
`GET /api/v1/albert/state-of-play`, `GET /api/v1/albert/scenario-outlooks/capability`.

## Legend
`REUSE` existing service used unchanged · `EXTEND` existing service wrapped with
provenance/breadth · `BUILT` new in N-A · `GAP` returns an explicit unavailable reason ·
`N-x` scheduled for a later phase.

## Stream 1 — Market & Opportunities

| Spec requirement | Verdict | Source of truth | Honest limits now reported |
|---|---|---|---|
| §5.1 Market direction & trend | REUSE + provenance | canonical regime store (`albert_regime`) | FRESH/STALE from `asOf`; invalidation text; "aggregation time is not proof every input is fresh" |
| §5.2 ETFs | REUSE | `etf_flows_feed` (Farside/bitbo) | `REPORTED_FACT`, reporting day named, issuer coverage listed, explicitly not sub-daily |
| §5.2 Institutions | REUSE | `leverage_feed` (OKX positioning/OI/funding) | `REPORTED_FACT`; stated as **derivatives positioning on a narrow venue set, not measured institutional spot exposure**; explicitly warns ETF flows must not be added as a second independent institutional signal |
| §5.2 Whales | REUSE | labelled large-holder balances (`whales_feed`) | balances `OBSERVED_FACT`, **`intent: UNKNOWN`**; custody/exchange entities separated from non-custodial; unlabelled holders invisible |
| §5.2 Miners | **GAP** | — | `UNSUPPORTED / NO_MINER_HOLDINGS_COVERAGE`. Hashrate exists but is not holdings evidence, so no miner conclusion is offered |
| §5.2 Retail | EXTEND (proxy) | Fear & Greed + exchange balances | `INFERRED`; bounded to the last 20 observations with the span named; states proxies are **not capital flow** |
| §5.3 BTC-vs-alt volume 24h | BUILT | `albert/market/volume.py` over the documented universe | `FRESH`. Spot turnover share only; stablecoins excluded from both buckets; ETH in the altcoin bucket; derivatives and market-cap dominance kept separate |
| §5.3 the same for 7d / 30d | BUILT, **PARTIAL by nature** | daily write-once samples in `market_turnover_daily` | The aggregator publishes only a rolling 24h figure, so multi-day windows are the **mean of daily samples**, reported `PARTIAL` with `daysCovered/daysRequired` until 7 and 30 days accrue. Stated plainly, never summed into a fake window total |
| §5.4 Sector leadership | EXTEND | `_sector_strength()` + `ALERT_SECTORS` | Versioned single-label taxonomy (mutually exclusive but **covers only mapped assets, not the whole market**); per-sector participation + turnover concentration; a one-token sector is labelled `CONCENTRATED`, never "leading" |
| §5.5 Forward research findings | **GAP → N-E** | — | `UNSUPPORTED / RESEARCH_FINDING_STORE_NOT_IMPLEMENTED`. A news feed is deliberately **not** substituted for research conclusions with persisted hypotheses and outcome history |
| §6.3 Market assessment (phase) | BUILT | `albert/market/phase.py` | Versioned rule (`market-phase-v1`) on **relative performance + breadth** over the documented universe. Turnover deliberately excluded so volume alone cannot declare an altcoin season. `MIXED` and `UNKNOWN` are real results. Thresholds disclosed as a product rule, not a market law |

Live sample: universe FRESH, 72 eligible altcoins, 12 stablecoins and 15 illiquid assets
excluded; phase `ALTCOIN_LED` (47/72 = 65% breadth, median alt +5.4pts vs BTC);
24h share BTC 0.4197 / alt 0.5803; sectors — Payments correctly `CONCENTRATED`
(XRP = 69.6% of sector turnover) rather than "leading".

## Stream 2 — Portfolio Performance · Paper Trading

| Spec requirement | Verdict | Notes |
|---|---|---|
| §7.1 canonical account values | REUSE | `_paper_dashboard_payload` is the single money path; nothing is recomputed in the frontend or the explanation layer |
| §7.1 equity / available-cash invariants | REUSE | already enforced in `albert/paper/core.py` with decimal precision |
| §7.1 "selected paper account" header | **SUPERSEDED** | M-G gave every strategy its own ring-fenced wallet, so there is no shared account to select. `state-of-play.paperAggregate` sums the wallets; the UI gets an **All strategies / individual strategy** filter instead (user decision 2a) |
| §7.2 per-strategy attribution | REUSE | attribution is by strategy-owned wallet, ledger and lots — never by splitting P&L across current weights |
| §7.2 backtest vs forward paper kept apart | REUSE | separate stores; the strategy card shows them in separate blocks |
| §7.4 modes | REUSE, **Observe retired** | Review-and-approve / Autopilot only (user decision 1a). Legacy `OBSERVE` wallets read as "not trading" and every new route rejects `OBSERVE` with 422 |

## Central chart — what-if forecast

| Spec requirement | Verdict | Notes |
|---|---|---|
| §6.1 observed history to a "Scenario starts" boundary | BUILT | real closed daily candles; the forming candle is trimmed |
| §6.1 shared anchor price + source time | BUILT | `baseline.observationId / observedAt / price` |
| §6.1 two conditional paths | **GAP → N-B** | `scenarios: []` with `UNSUPPORTED / SCENARIO_PROVIDER_NOT_IMPLEMENTED` |
| §6.2 coin selection, no BTC substitution | BUILT | an asset without candle coverage returns `MISSING / NO_OBSERVED_HISTORY`; BTC is never substituted |
| §6.3 assessed phase vs what-if lens | BUILT | `phase.mode = ASSESSED\|WHAT_IF`, `phase.applied` separate from `phase.assessed`; `phaseOverride` with `ASSESSED` is rejected 422 |
| §6.5 numeric generation | **N-B** | `SCENARIO_PROVIDER = None`; the endpoint guarantees no LLM numbers and no demo fixtures |
| §10.3 preview must not mutate | BUILT | read-only; creates no proposal, order or strategy change |

## New contracts shipped in N-A

- `GET  /api/v1/albert/market-streams?participants=0|1` — Stream 1 with per-section `ResultMeta`
- `GET  /api/v1/albert/scenario-outlooks/capability` — declares what the forecast layer can/cannot do
- `POST /api/v1/albert/scenario-outlooks/preview` — real history + honest scenario state
- `GET  /api/v1/albert/state-of-play` — now also carries `marketStreams` (cheap facts only),
  `capabilities` and `paperAggregate`

New modules: `backend/albert/market/{meta,universe,volume,phase,participants,sectors}.py`.
New collection: `market_turnover_daily` (write-once per UTC day).
Touched: `_discovery_universe_rows` and `assemble_core` now carry 7d/30d changes (additive).

## Material findings the user should know

1. **7d/30d turnover shares will be `PARTIAL` for up to 30 days.** No provider available
   here publishes multi-day spot turnover totals, so the windows fill in as daily samples
   accrue. The alternative — summing a rolling 24h number seven times — would be wrong.
2. **Miner analysis is not possible** without a miner wallet-classification dataset. It
   returns `UNSUPPORTED` rather than inferring miner behaviour from hashrate.
3. **Research findings need a hypothesis store** (original conclusion, confirm/invalidate
   conditions, and the outcome when the view changes). That is N-E, not a news relabel.
4. **Forecast ≠ research ≠ paper-executable.** `capabilities` reports the three separately:
   12 assets researchable, 0 forecastable today, 12 paper-executable.
5. **`capabilities.research.status` reads `MISSING` on a cold start** for ~10s while the
   Discovery universe rebuilds in the background. This is deliberate: the request never
   blocks on the rebuild and never serves a stale snapshot as fresh.

None of these are blockers for N-B. Proceeding.

---

# Phase N-B — Scenario provider (built, evaluated, NOT validated as a forecast)

`backend/albert/market/scenario.py`, model version `historical-analog-scenario-v1`.
Registered as `SCENARIO_PROVIDER`. Lives outside the language model and the paper engine.

## Method
Comparable-historical-window analysis. Today's conditions are described by six **strictly
trailing** features (20d and 60d momentum, 20d realised volatility, drawdown from the 90d
high, distance from the 50d average, Wilder RSI). Features are divided by **fixed declared
constants**, never z-scored against the series, because a full-series z-score leaks the
future into the past. The most similar historical days are found with a weighted
Euclidean distance, **purged** of anything within ±horizon of today, and restricted to days
whose full forward window already happened. Bullish/bearish paths are the **80th/20th
percentiles** of those realised forward returns, anchored to the last closed candle.

History source: `fetch_yahoo_series(<TICKER>-USD, rng='5y')` for 12 mapped assets. The
exchange feed used elsewhere retains only ~260 candles, which produced a 40-day match set
collapsing into **3** overlapping episodes; the 5-year record gives a 1,728-day pool and a
172-day match set across **20 distinct episodes**. Episode count is reported alongside the
day count so the raw number cannot imply more evidence than exists.

## Walk-forward result (BTC, 7-day horizon, 61 chronological checks)
| Metric | Value | Reading |
|---|---|---|
| Interval coverage | **65.6%** vs 60% target | the band is well calibrated, slightly conservative |
| Median abs. error | 3.859% | |
| No-change baseline | 3.943% | |
| **Skill vs no-change** | **+0.021** | **statistically meaningless** |
| Regime coverage | 19 up / 11 down / 31 flat | |

## The material finding
**The band is trustworthy; the middle path is not.** A +0.02 skill score over 61 checks is
noise, so the provider is gated: `SCENARIO_MIN_SKILL = 0.10` and
`SCENARIO_MIN_EVAL_POINTS = 60` must BOTH be met before anything may be called tested.
Current state is `CALIBRATED_NO_MATERIAL_SKILL`, and every single preview response carries:

- `validation.predictiveValidation: false`
- `validation.bandCalibrated: true`
- `validation.labelRequirement: "Conditional historical scenario"`
- a headline beginning **"NOT A FORECAST."**

**Consequence for N-C/N-D:** the chart must lead with the *range* (the band comparable past
conditions produced) and must not present the middle path as Albert's expectation. The
"NOT A FORECAST" headline and the evaluation link belong on the chart itself, not buried
under More details.

## Also true of this provider
- The **season lens is not a model input** (`assumptionEvaluated: false`,
  `PHASE_CONDITIONING_NOT_IN_MODEL`). Changing it does not move the paths, and the response
  says so rather than implying the assumption was evaluated. Conditioning on historical
  phase would need historical altcoin-breadth labels, which do not exist here.
- `probability` is always `null` — no calibrated interpretation exists, so none is asserted.
- An unmapped asset returns `MISSING / NO_OBSERVED_HISTORY` with zero paths and **no BTC
  substitution**.
- The preview is read-only: no proposal, order, fill, stop, mode or strategy change.

Harness: `backend/scripts/na_nb_test.py` — **65/65 pass** live and unmocked.
