import {
  LayoutDashboard, Target, Scale, BarChart3, Globe, History, Waves, Fish, Landmark,
  Gauge, Newspaper, ShieldAlert, CalendarClock, Trophy, MessageCircle, Bell, Activity,
  Database, Cpu, ShieldCheck, Sparkles, CandlestickChart, ClipboardList, Info,
} from 'lucide-react';

const SECTIONS = [
  { id: 'briefing', label: 'Albert\u2019s Morning Brief', icon: Sparkles,
    blurb: 'Your one-screen executive briefing: market bias, price, Albert’s read, the levels that matter, live sentiment and the decision engine — each card drills into the full analysis.' },
  { id: 'ask', label: 'Ask Albert', icon: MessageCircle,
    blurb: 'Chat with Albert, Ask Albert’s HuCentAI Quant Analyst, in plain English — "Why did the score fall?", "What could move Bitcoin next?" — grounded strictly in the live dashboard numbers. He never invents data.' },
  { id: 'overview', label: 'Overview', icon: LayoutDashboard,
    blurb: 'Your 10-second snapshot of Bitcoin right now: the price, the market "mood", one simple score, the near-term odds, how risky things are and how sure the model is. Start here.' },
  { id: 'forecasts', label: 'Forecasts', icon: Target,
    blurb: 'BitMarkAI’s probability-based price forecasts from 1 week to 5 years — always shown as odds and price ranges (bull / base / bear), never a single guaranteed number. Longer horizons show wider uncertainty.' },
  { id: 'compare', label: 'Compare Coins', icon: Scale,
    blurb: 'Run the same quant engine across Bitcoin, Ethereum and Solana side by side — score, market mood, near-term odds and key levels — so you can see how the majors stack up. Each coin computes its own model on first view, then caches.' },
  { id: 'market-intel', label: 'Market Intelligence', icon: BarChart3,
    blurb: 'The technical picture behind the score: chart structure and key levels, where Bitcoin sits in its 4-year cycle, and the raw indicators the model reads.' },
  { id: 'crossmarket', label: 'Cross-Market', icon: Globe,
    blurb: 'How this coin stacks up against traditional markets — S&P 500, Nasdaq, Dow, Nikkei, European indices, Gold and the US Dollar. See rebased performance, returns, correlation (is crypto moving with stocks or breaking away?) and volatility.' },
  { id: 'analogs', label: 'Happening Again', icon: History,
    blurb: "Finds which past Bitcoin trend episode today's conditions most resemble — using macro rates, the US dollar, equity & gold correlation, volatility, drawdown, momentum and halving-cycle position — then shows what happened next. Adjust the sliders to weight what matters to you. Educational pattern-matching, not a prediction." },
  { id: 'smartmoney', label: 'Smart Money', icon: Waves,
    blurb: 'On-chain "smart money" behaviour — valuation (MVRV, SOPR), network activity, holder accumulation and sentiment. Powered by real on-chain data (BGeometrics, blockchain.com, Glassnode) and Fear & Greed.' },
  { id: 'whales', label: 'Whale Watch', icon: Fish,
    blurb: 'Live balances of the largest, publicly-labeled Bitcoin wallets — major exchanges, ETF/treasury custody, governments and famous whales. Track who is accumulating or distributing, with balances fetched live on-chain. Names are curated from public labels.' },
  { id: 'institutional', label: 'Institutional & Derivatives', icon: Landmark,
    blurb: 'Institutional & derivatives footprint — futures open interest, funding, long/short positioning and taker flow (live via OKX), plus REAL US spot Bitcoin ETF net flows (live via Farside/bitbo).' },
  { id: 'leverage', label: 'Leverage', icon: Gauge,
    blurb: 'Long & short positioning, market leverage and liquidation pressure — is leverage high or low, are traders leaning long or short, and where is the greater squeeze/liquidation risk right now.' },
  { id: 'macro', label: 'Macro & Policy', icon: Globe,
    blurb: 'Are global money conditions helping or hurting Bitcoin? Central-bank policy, a liquidity gauge, cross-market correlations and a regulation tracker.' },
  { id: 'news', label: 'News', icon: Newspaper,
    blurb: 'The news, explained: what happened, why it matters for Bitcoin, the likely direction and an impact score — with links to the original source.' },
  { id: 'risk', label: 'Risk', icon: ShieldAlert,
    blurb: 'How bumpy conditions are right now — kept separate from direction. Expected move, key support/resistance zones, event risk and data reliability. A positive outlook can still be high risk.' },
  { id: 'events', label: 'Events', icon: CalendarClock,
    blurb: 'A countdown calendar of the macro, derivatives and on-chain events that could move Bitcoin next — each with importance and expected volatility.' },
  { id: 'performance', label: 'Performance', icon: Trophy,
    blurb: 'The receipts. Every forecast is logged before the outcome is known and graded when it matures — accuracy, calibration and an honest scoreboard, plus the data-trust log. Nothing is hidden.' },
  { id: 'timemachine', label: 'Bitcoin Time Machine', icon: History,
    blurb: 'Replay any day in Bitcoin’s history: see exactly what the model would have predicted then, what actually happened next, and the price path around it — using only the information available at the time.' },
  { id: 'alerts', label: 'Alerts', icon: Bell,
    blurb: 'A running feed of what just changed and what is coming: regime shifts, decision changes, data-trust drops and upcoming high-impact events.' },
  { id: 'network', label: 'Network & Sentiment', icon: Activity,
    blurb: 'Is the network healthy and how does the crowd feel? Live hashrate, mining difficulty, mempool congestion & fees, plus the Crypto Fear & Greed Index with Albert’s read on crowd extremes.' },
  { id: 'dataaudit', label: 'Data Audit', icon: Database,
    blurb: 'Where every number comes from and how much to trust it. A trust-scored composite Bitcoin price (median of Coinbase, Kraken, OKX, CoinGecko with outlier detection), broader cross-asset context, global news tone (GDELT) and US macro (FRED) — each tagged HIGH / MEDIUM / LOW confidence. No fabricated data.' },
  { id: 'settings', label: 'Settings', icon: Cpu,
    blurb: 'Admin passcode for manual forecast runs, plus Ask Albert’s about & compliance information. (Live data-source status now lives in the Admin screen.)' },
  { id: 'admin', label: 'Admin', icon: ShieldCheck,
    blurb: 'Integrations, data-source freshness, usage, costs and system health for the Ask Albert platform.' },
];

// Legacy section metadata for sub-panels that are now grouped under the new nav
// (their components still look up a blurb/label by id).
const LEGACY_SECTIONS = [
  { id: 'bitmark', label: 'BitMarkAI', icon: Sparkles,
    blurb: 'BitMarkAI is Ask Albert’s adaptive Bitcoin Price Prediction Engine — probability-based forecasts from one week to five years. Each horizon is weighted differently, updated weekly, on demand, or when a major event hits — and every change is explained. It never gives a single guaranteed price.' },
  { id: 'chart', label: 'Chart Intelligence', icon: CandlestickChart,
    blurb: 'An automatic read of the daily chart in plain language: support and resistance zones, trend, breakouts and momentum — plus how often similar setups played out historically.' },
  { id: 'cycle', label: 'Cycle', icon: Globe,
    blurb: 'Where Bitcoin sits in its ~4-year halving cycle and how money is rotating across the wider crypto market (BTC dominance). Context, not a price rule.' },
  { id: 'policy', label: 'Macro & Policy', icon: Landmark,
    blurb: 'Are global money conditions helping or hurting Bitcoin? Central-bank policy, a liquidity gauge, cross-market correlations and a regulation tracker that separates proposals from enacted law.' },
  { id: 'analysis', label: 'Indicators', icon: BarChart3,
    blurb: 'The evidence behind the score: each indicator category, the raw values the model reads, and which ones matter most right now.' },
  { id: 'scorecard', label: 'Prediction Ledger', icon: ClipboardList,
    blurb: 'Every forecast is permanently logged before the outcome is known, then graded when it matures — directional accuracy, Brier score, error and calibration by horizon. Nothing is deleted.' },
  { id: 'trust', label: 'Data Trust', icon: ShieldCheck,
    blurb: 'Where every number comes from: the source, how fresh it is, and how reliable. If a live feed goes stale the odds are automatically toned down.' },
];
const sec = (id) => SECTIONS.find(s => s.id === id)
  || LEGACY_SECTIONS.find(s => s.id === id)
  || { id, label: id, icon: Info, blurb: '' };

// Sections that are Bitcoin-specific and hidden from the nav when an altcoin is selected.
const BTC_ONLY_SECTIONS = ['smartmoney', 'whales', 'macro', 'events', 'timemachine', 'leverage', 'network', 'dataaudit', 'admin'];
// Sections removed from the app entirely (superseded by the global coin picker).
const REMOVED_SECTIONS = ['compare'];

export { SECTIONS, LEGACY_SECTIONS, sec, BTC_ONLY_SECTIONS, REMOVED_SECTIONS };
