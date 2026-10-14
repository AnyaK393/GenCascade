# Threads

## Concept

Threads are units of execution inside one process: they share code, data and open files but each has its own stack and registers. They are cheaper to create and switch than processes.

## Example

A web server creates a thread per request; all threads read the same cache in shared memory.

## Common mistakes

Assuming shared data is safe without synchronisation. Confusing the user-level and kernel-level thread models (many-to-one cannot use multiple cores).

## Practice question

Why can a many-to-one thread model not speed up a CPU-bound program on a multicore machine?

## Worked solution

<!-- type: solution -->

All user threads map to one kernel thread, so the kernel schedules only one of them at a time on one core.
