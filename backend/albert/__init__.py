"""Albert trading-adviser domain package.

Surgical extraction of the deterministic Albert engine out of the ~12k-line
server.py monolith (Phase D0). Behaviour is preserved 1:1 with the original
server.py implementation. Market-data + portfolio helpers still live in
server.py and are injected at runtime via `albert.deps.configure(...)` to avoid
a circular import.

Layout:
  albert/deps.py                 - dependency-injection container
  albert/engine/constants.py     - engine version + thresholds/universe
  albert/engine/regime.py        - deterministic BULL/RANGE/BEAR regime
  albert/engine/scoring.py       - transparent 0-100 opportunity score
  albert/engine/decision.py      - full deterministic decision snapshot
"""
