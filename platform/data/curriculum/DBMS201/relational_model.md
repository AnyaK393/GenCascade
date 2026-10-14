# Relational model and keys

## Concept

A relation is a set of tuples with named attributes. A candidate key uniquely identifies tuples, the primary key is the chosen one, and a foreign key refers to another relation's key to keep referential integrity.

## Example

In Student(roll_no, email, name) both roll_no and email are candidate keys; Enrols.roll_no is a foreign key to Student.

## Common mistakes

Confusing a superkey with a candidate key (a candidate key is minimal). Allowing NULL in a primary key.

## Practice question

List all candidate keys of R(A, B, C, D) with A -> B, B -> C and C -> D.

## Worked solution

<!-- type: solution -->

The closure of A is {A, B, C, D}, so A is a key. No other single attribute determines A, so A is the only candidate key.
