# Query processing and optimization

## Concept

The optimizer turns SQL into a plan of relational operators and chooses join orders and algorithms (nested loop, hash join, sort-merge) by estimated cost, using statistics such as table sizes and selectivity.

## Example

Joining a 10-row table to a 1-million-row table: a nested loop with an index on the large table beats a full hash join.

## Common mistakes

Applying filters after joins instead of pushing selections down. Trusting stale statistics that mislead the optimizer.

## Practice question

Why push selections below joins in a query plan?

## Worked solution

<!-- type: solution -->

Filtering first shrinks the inputs to the join, so the expensive join processes fewer rows. The result is unchanged because selection commutes with join.
