"""Token ratio learner plugin — per-model chars/token ratio learning.

Provides ``count_tokens()`` using learned ratios, falling back to a safe
overestimate when no ratio has been learned yet for a given model.
"""
