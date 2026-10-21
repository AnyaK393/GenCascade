# SQL basics

## Concept

SQL queries are built from SELECT (columns), FROM (tables), WHERE (row filter), GROUP BY (groups), HAVING (group filter) and ORDER BY. Aggregates such as COUNT and AVG summarise groups.

## Example

SELECT dept, AVG(salary) FROM emp GROUP BY dept HAVING AVG(salary) > 50000;

## Common mistakes

Using WHERE to filter on an aggregate (use HAVING). Selecting a column that is neither grouped nor aggregated. Comparing with = NULL instead of IS NULL.

## Practice question

Find the departments with more than 5 employees.

## Worked solution

<!-- type: solution -->

SELECT dept FROM emp GROUP BY dept HAVING COUNT(*) > 5;
