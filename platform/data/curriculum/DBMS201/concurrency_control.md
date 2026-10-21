# Concurrency control

## Concept

Concurrency control keeps interleaved transactions equivalent to some serial order. Two-phase locking (a growing phase, then a shrinking phase) guarantees conflict serializability; strict 2PL holds write locks until commit.

## Example

T1 reads X and T2 writes X before T1 writes X: a lost update, which 2PL prevents because T2 must wait for T1's lock.

## Common mistakes

Releasing a lock and then acquiring another, which breaks 2PL. Forgetting that 2PL can deadlock and needs detection or timeouts.

## Practice question

Is the schedule r1(A) w2(A) w1(A) conflict serializable?

## Worked solution

<!-- type: solution -->

No. w2(A) after r1(A) gives the edge T1 -> T2, and w1(A) after w2(A) gives T2 -> T1. The precedence graph has a cycle.
