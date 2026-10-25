# Self-check answers

Answers to the six questions in the guide. Same numbering.

1. **Pitfall #1.** It would have recorded `A3-other / alice → 200` and certified the flaw as the expected behaviour: from then on, the fix would have turned that cell red. The expected answers come from the rules written before the code — here the function `expected(row, caller)`, written from `RULES.md` and cross-checked against the hand-written `MATRIX.md` — never from what the application answers.

2. **Pitfall #1.** If the owner decides `200` is right, the rule is wrong, not the test: change `RULES.md` first (the rule and its reason), then the matrix and `expected()` so they follow the new rule, then rerun. Editing the expected value alone to match the application turns the test into a recording of the code.

3. **Pitfall #2.** `A3-other`: alice, a member, asks for loan 2, which belongs to bob. The functional cases only ask for one's own loan, or are made by roles that may see every loan, so they cannot catch a missing ownership check. The owner must not be a caller because the flaw is about reading an object you do *not* own; the target has to be someone else's object, asked for by a member who is not its owner.

4. **Pitfall #2.** A `403` confirms that loan 2 exists; `404` makes someone else's loan indistinguishable from no loan, so a member learns nothing about other members. The script calls `GET /loans/99` as alice and checks that the code *and* the body are identical to the answer for `/loans/2`.

5. **Pitfall #3.** Break one check on purpose (not committed), write down which cells must turn red, run, then restore and run again. Distrust the script if nothing turns red, or if cells other than the predicted ones turn red: either the script tests nothing there, or the prediction or the rules are wrong.

6. **Pitfall #4.** A librarian was allowed to delete a book: the data is probably changed — book 6 gone from the catalogue. The report stops at the status code because the witnesses (here the catalogue read back as adam) only run when the status code matches; the cell is red either way, but the damage is not described. Check the data by hand, or make `run_cell` run `write_effect` in both branches.
