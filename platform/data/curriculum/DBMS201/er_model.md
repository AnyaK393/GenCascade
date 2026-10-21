# Entity-relationship model

## Concept

The ER model describes data as entities (things), attributes (their properties) and relationships between them, with cardinalities such as 1:1, 1:N and M:N. It is the design step before tables.

## Example

Student and Course with an M:N relationship Enrols, which has the attribute grade.

## Common mistakes

Putting a relationship attribute (grade) on one entity. Forgetting weak entities that depend on an owner, such as Dependent on Employee.

## Practice question

Map the M:N relationship Enrols(Student, Course, grade) to tables.

## Worked solution

<!-- type: solution -->

Create Enrols(student_id, course_id, grade) with a composite primary key (student_id, course_id) and foreign keys to Student and Course.
