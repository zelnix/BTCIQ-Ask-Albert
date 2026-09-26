# Queued spec — Ask Albert Two-Stream Dashboard & What-if Forecast (v1.0, 25 Sep 2026)

Source artifact (uploaded by the user, fetch again if needed):
https://customer-assets-cm19k8pv.emergentagent.net/job_quant-features/artifacts/jcv8cyk6_Ask_Albert_Two_Stream_Dashboard_Developer_Instructions.md

STATUS: NOT STARTED. Queued immediately after M-G (unified strategy/paper journey).

## The ask in one paragraph
Rebuild **Albert Home** around **two streams** joined by Albert's executive briefing:
(1) **Market & Opportunities** — direction/trend, who is moving the market (ETFs, institutions,
whales, miners, retail), BTC-vs-altcoin spot turnover share (24h/7d/30d), sector leadership and
prioritised forward research findings; (2) **Portfolio Performance · Paper Trading** — the selected
paper account, equity/cash/drawdown, per-strategy net results and anything needing review.
The hero visual is a **TradingView-style "what-if" forecast chart**: observed history to a visible
"Scenario starts" boundary, then TWO conditional paths (bullish + bearish) from one shared anchor
price, default horizon 7 days, with a **BTC-season / altcoin-season / mixed** lens. Desktop-first
(1920 reference, then 1366, 1024, tablet landscape/portrait).

## Non-negotiables pulled from the doc
- Albert is a **companion, not a broker**. No live-order/transmit language, no invented 20-year
  trading history, no profit promises. Paper trading only.
- **The concept's numbers are demo fixtures and must never ship as production forecasts.** Either
  reuse an approved scenario service or build a **versioned scenario provider separate from the LLM
  and the paper engine**, with declared inputs, horizon, minimum sample, uncertainty method and
  explicit unavailable states. First defensible candidate: comparable historical-window analysis
  (point-in-time features only), labelled "conditional historical scenarios". Walk-forward /
  chronological holdout evaluation, no look-ahead, compare against a no-change baseline.
- **No LLM-generated numbers**, ever. No probability/confidence percentages unless the service
  supplies a defined, evaluated interpretation.
- Two separate concepts: **Market assessment** (evidence-derived phase, read-only, versioned rule)
  vs **What-if season lens** (user assumption). A manual lens must never overwrite the assessment,
  strategy rules, account mode or execution eligibility.
- Coin switching is **atomic**: title, asset id, units, history, anchor, both paths, drivers,
  evidence, ARIA text and generated chat context change together. Never relabel BTC paths as SOL.
  Reject out-of-order responses using the full selection key. Unsupported asset -> "unavailable",
  never a silent BTC fallback.
- **Knowledge types** must stay distinct: OBSERVED_FACT / REPORTED_FACT / SYSTEM_ASSESSMENT /
  ALBERT_INTERPRETATION / WHAT_IF_ASSUMPTION / UNKNOWN. Not one confidence score.
- Every material claim carries evidence refs + source time + availableAt + coverage + limitations,
  and a **precise** deep link (the exact strategy version / proposal / fill / snapshot), not a
  Technical Centre landing page. Server-approved links only; ownership re-checked server-side.
- Money: decimal strings, `equity = cash + marked positions`,
  `available = max(0, cash - protected reserve - committed)`. Never recompute money in the frontend
  or the explanation layer. Don't double-count fees. Don't treat USD and USDC as identical.
- Volume shares: USD-equivalent **spot turnover share** over a documented, versioned universe; ETH
  sits in the altcoin bucket; exclude stablecoin-only pairs; keep derivatives and market-cap
  dominance separate; unavailable (not 0%/100%) when the denominator is missing.
- Chart interaction must never create a proposal, order, fill, stop, mode or strategy change.
- Existing Technical Centre screens/routes stay reachable and unchanged.

## Suggested contracts (map to the repo, extend — do not fork new services)
- `GET /api/v1/albert/state-of-play?paperAccountId=` extended with briefing.claims, attention,
  market.{direction,participants,spotVolumeShares,sectors,researchFindings,phaseAssessment},
  paper.{account,mode,runtimeState,equity,performance,strategyAttribution,positions,proposals},
  `capabilities` (research vs forecast vs paper-execution are NOT the same), `evidenceIndex`.
- `POST /api/v1/albert/scenario-outlooks/preview` -> `ScenarioOutlook` (meta, selectionKey,
  modelVersion, baseline, phase{assessed,mode,applied}, history, scenarios[{side,status,points,
  drivers[{use:MODEL_INPUT|CONTEXT_ONLY}],invalidation,uncertainty,probability}]). Preview only —
  it must not mutate anything.
- `GET /api/v1/albert/evidence/{evidenceId}` owner-scoped for private records.
- Ask Albert extended with a bounded `context` object (stateId, accountId, strategyId+version,
  outlookId, claimId, evidenceRefs), re-resolved and ownership-checked server-side.

## Work packages from the doc
- **A** — inventory the repo and produce a truthful reuse/extend/build/unavailable mapping; extend
  state-of-play with per-section provenance; implement only what the data supports; establish the
  scenario-provider contract and keep demo fixtures isolated.
- **B** — build the desktop-first shell, briefing, two streams, the chart, atomic selection,
  evidence panels and contextual Ask Albert.
- **C** — contract/accounting/ownership/async/strategy-integrity checks, connected read-only
  journey, paper workflows against existing modes, screenshots at 1920/1366/1024/tablet, existing
  regression gates, and a handoff stating exactly what is connected vs degraded vs unavailable.

## OPEN CONFLICT TO RESOLVE WITH THE USER BEFORE BUILDING
Section 2.2 of this document says **preserve all three modes, including Observe**. The user's
immediately preceding instruction (implemented as M-G) **removed Observe** and collapsed the
journey into build -> save -> start paper trading with per-strategy Review/Autopilot and a
per-strategy wallet. Ask which wins; the M-G behaviour is the more recent verbal instruction and is
already shipped, so the default assumption is: keep Observe retired, treat legacy OBSERVE wallets as
"not trading", and read the rest of the document as authoritative.

Also worth confirming: the doc's "selected paper account" header control conflicts with M-G's
per-strategy wallets (there is no single account to select any more). Proposed resolution: the
Portfolio stream shows the aggregate across strategy wallets, with a strategy selector instead of an
account selector.
