# Indexing and B+ trees

## Concept

An index speeds up lookups by keeping keys in a search structure, usually a B+ tree whose leaves are linked for range scans. A clustered index orders the table itself; secondary indexes point to rows.

## Example

An index on emp(salary) lets WHERE salary BETWEEN 40000 AND 50000 descend the tree once and then scan the linked leaves.

## Common mistakes

Indexing every column, which slows writes. Expecting an index on (a, b) to help a query that filters only on b.

## Practice question

Which index helps SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at?

## Worked solution

<!-- type: solution -->

A composite index on (customer_id, created_at): it finds customer 42 and returns rows already in date order.
