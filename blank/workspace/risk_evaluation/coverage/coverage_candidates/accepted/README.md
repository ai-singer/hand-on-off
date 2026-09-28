# Accepted candidates

This directory is written by a human, never by the framework.

A candidate may move here only after it has been scored against a benchmark that did
not exist when the candidate was proposed. Before that measurement, accepting a
candidate would be asserting an improvement nobody has observed — and the coverage
framework exists precisely because that assertion kept being made without evidence.

To accept a candidate:

1. Copy its JSON here unchanged.
2. Set `"status": "accepted"`.
3. Record a `ReviewDecision` naming the reviewer, the decision and the rationale.
4. Score the change against a new benchmark and record the result alongside it.

Candidate ids are stable. The framework will not reuse or overwrite a file in this
directory; if an id collides, the run fails loudly rather than overwriting a decision.
