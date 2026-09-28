"""Tests for the Risk Coverage Expansion Framework (`risk_evaluation/coverage/`).

Every module here is read-only with respect to the framework it measures: nothing in
this package writes to `risk_evaluation/coverage/`, to the frozen evaluator, or to any
benchmark. The only writes any test performs go to a `tempfile` directory of its own.
"""
