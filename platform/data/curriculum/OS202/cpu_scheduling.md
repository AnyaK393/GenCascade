# CPU scheduling

## Concept

The scheduler picks the next ready process. FCFS is simple but suffers the convoy effect, SJF minimises average waiting time but needs burst estimates, and round robin with a time quantum gives fair response times.

## Example

Bursts P1 = 24, P2 = 3, P3 = 3 under FCFS give waiting times 0, 24 and 27 (average 17); SJF gives 6, 0 and 3 (average 3).

## Common mistakes

Mixing up waiting time (time in the ready queue) and turnaround time (completion minus arrival). Choosing a huge quantum, which turns round robin into FCFS.

## Practice question

Compute the average waiting time for round robin with q = 4 and bursts 24, 3, 3 arriving at 0.

## Worked solution

<!-- type: solution -->

Gantt chart: P1 0-4, P2 4-7, P3 7-10, then P1 to 30. Waiting times are P1 6, P2 4, P3 7, so the average is 17/3 ≈ 5.67.
