# Joins

## Concept

A join combines rows from two tables on a condition. An inner join keeps only matching pairs, a left outer join keeps every left row (with NULLs when unmatched), and a cross join gives every pair.

## Example

Student LEFT JOIN Enrols ON Student.id = Enrols.sid lists every student, including those with no enrolment.

## Common mistakes

Forgetting the join condition, which produces a Cartesian product. Filtering the right table in WHERE after a LEFT JOIN, which turns it back into an inner join.

## Practice question

List students who are not enrolled in any course.

## Worked solution

<!-- type: solution -->

SELECT s.* FROM Student s LEFT JOIN Enrols e ON s.id = e.sid WHERE e.sid IS NULL;
