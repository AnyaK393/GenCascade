# Virtual memory and page replacement

## Concept

Virtual memory loads pages on demand, so a process can be larger than RAM. A page fault brings a page in, evicting another by a replacement policy (FIFO, LRU, optimal). Too little memory leads to thrashing.

## Example

Reference string 7 0 1 2 0 3 with 3 frames under FIFO: 7, 0 and 1 fault, 2 evicts 7, 0 hits, and 3 evicts 0.

## Common mistakes

Assuming more frames always means fewer faults (Belady's anomaly can occur with FIFO). Confusing LRU (least recently used) with FIFO (oldest loaded).

## Practice question

Count LRU page faults for 1 2 3 4 1 2 5 1 2 3 4 5 with 3 frames.

## Worked solution

<!-- type: solution -->

Track recency: 1, 2, 3 and 4 fault (4 evicts 1), 1 faults, 2 faults, 5 faults, 1 and 2 hit, then 3, 4 and 5 fault. That is 10 faults.
