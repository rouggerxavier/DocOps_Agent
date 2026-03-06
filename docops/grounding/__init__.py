"""Semantic grounding: extract factual claims and verify evidence support.

Public API
----------
- :func:`~docops.grounding.claims.extract_claims` — split answer into claims
- :func:`~docops.grounding.support.check_support` — SUPPORTED/NOT_SUPPORTED/UNCLEAR
- :func:`~docops.grounding.support.compute_support_rate` — aggregate over all claims
"""
