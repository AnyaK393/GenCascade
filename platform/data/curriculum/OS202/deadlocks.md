# Deadlocks

## Concept

A deadlock needs four conditions at once: mutual exclusion, hold and wait, no preemption and circular wait. Systems prevent one condition, avoid unsafe states (the Banker's algorithm), or detect and recover.

## Example

T1 holds lock A and waits for B while T2 holds B and waits for A: a circular wait.

## Common mistakes

Thinking a cycle always means deadlock (true only with single-instance resources). Confusing prevention (break a condition) with avoidance (stay in safe states).

## Practice question

With Available = (3, 3, 2), decide whether a given Banker's state is safe.

## Worked solution

<!-- type: solution -->

Repeatedly find a process whose Need <= Available, pretend it finishes and add its Allocation to Available. If every process can finish, the state is safe and that order is a safe sequence.
