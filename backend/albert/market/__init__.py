"""Albert market-streams layer (N-A).

Provenance-first market analysis for the two-stream dashboard. Every function here
returns an authoritative RESULT plus its own ResultMeta: what was measured, over what
period, from which snapshot, how complete the coverage was and what it cannot tell you.

Hard rules for this package:
  * It computes; it never explains. No LLM, no prose generation, no invented numbers.
  * An absent input produces MISSING / UNSUPPORTED / UNKNOWN - never a zero dressed up
    as an answer, and never a silent substitute for a different asset.
  * Every rule that has thresholds carries a VERSION string, because a product rule is
    not a law of markets.
"""
