"""Phase E — paper-only Execution Safety Layer (Paper Order Manager).

Hard architectural line (never violated):
  DecisionSnapshot -> frozen OrderIntent -> Confirmation -> Paper Order -> Fill/Reconciliation
The LLM is entirely OUTSIDE this state machine. Albert may READ intents/fills/
rejections and explain them, but can never create/confirm/execute/cancel/amend.
"""
