# Recovery

## Concept

After a crash, recovery uses the log to redo the effects of committed transactions and undo uncommitted ones. Checkpoints limit how much of the log must be scanned.

## Example

The log shows T1 committed and T2 did not before the crash: redo T1's updates and undo T2's.

## Common mistakes

Undoing committed transactions. Forgetting that redo must happen even for pages that might already be on disk (it is idempotent with LSNs).

## Practice question

Given a checkpoint, T1 committed after it, and T2 active at the crash, which transactions are redone and undone?

## Worked solution

<!-- type: solution -->

Redo T1 because it committed and its pages may not be on disk; undo T2 because it never committed.
