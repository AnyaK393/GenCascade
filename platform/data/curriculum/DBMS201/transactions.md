# Transactions and ACID

## Concept

A transaction is a unit of work that is atomic (all or nothing), consistent, isolated from concurrent transactions and durable once committed. Logs (write-ahead logging) make atomicity and durability possible.

## Example

Transferring money: debit A and credit B in one transaction, so a crash in between rolls both back.

## Common mistakes

Thinking COMMIT only means success: durability means it survives a crash after commit. Mixing up consistency (rules hold) with isolation (no interference).

## Practice question

Explain which ACID property write-ahead logging provides and how.

## Worked solution

<!-- type: solution -->

Atomicity and durability: log records are forced to disk before data pages, so undo can roll back uncommitted work and redo can replay committed work after a crash.
