# Rejected candidates

Written only for rejections the framework can prove from its own tables, with no
judgement involved:

- `redundant-with-evaluator-lexicon` — every proposed word is one the evaluator
  already matches, so the candidate asks for nothing.
- `proposal-reuses-a-failing-cases-own-text` — the proposal quotes the case it came
  from, which would improve that case and nothing else.
- `target-is-frozen-for-this-phase` — the proposal names a path this phase may not
  modify.
- `proposal-adds-nothing` — recorded when a candidate carries an empty addition list
  that no structural reading can justify.

This directory is empty for the Phase R1 run, and that is the expected result rather
than a gap. Every candidate that run produced came from a declared axis, none quoted a
failing case, and none named a frozen path — so none of the four provable grounds
applied. A rejection that needed an opinion would be a decision wearing a rejection's
clothes, and those candidates stay in `pending/` for a human.

The file exists so the directory is present in the repository: git cannot track an
empty directory, and the layout the framework documents should be the layout a reader
finds.
