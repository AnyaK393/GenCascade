# Process synchronization

## Concept

When threads share data, a race condition occurs if the result depends on timing. A critical section must provide mutual exclusion, progress and bounded waiting; mutexes, semaphores and monitors provide it.

## Example

Two threads run count++ (load, add, store) concurrently; both load 5 and both store 6, so one update is lost.

## Common mistakes

Forgetting to release a lock on an error path. Using a semaphore initialised to the wrong value. Busy-waiting on a single-core machine.

## Practice question

Solve the bounded-buffer producer-consumer problem with semaphores.

## Worked solution

<!-- type: solution -->

Use empty = N, full = 0 and mutex = 1. The producer waits on empty and mutex, adds, then signals mutex and full; the consumer waits on full and mutex, removes, then signals mutex and empty.
