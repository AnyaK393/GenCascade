# Normalization

## Concept

Normalization removes redundancy using functional dependencies. 1NF needs atomic values, 2NF removes partial dependencies on a composite key, 3NF removes transitive dependencies, and BCNF requires every determinant to be a superkey.

## Example

Enrols(sid, cid, sname, grade) with sid -> sname violates 2NF because sname depends on only part of the key.

## Common mistakes

Decomposing without checking that the join is lossless. Assuming 3NF and BCNF are always the same.

## Practice question

Decompose R(sid, cid, sname, grade) with key (sid, cid) and sid -> sname into BCNF.

## Worked solution

<!-- type: solution -->

Split into Student(sid, sname) and Enrols(sid, cid, grade). Both are in BCNF and the join on sid is lossless.
