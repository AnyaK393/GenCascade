# Memory management

## Concept

The OS gives each process memory and protects it with base and limit registers. Contiguous allocation (first fit, best fit, worst fit) suffers external fragmentation; fixed partitions waste space internally.

## Example

Holes of 100, 500 and 200 KB with a 212 KB request: first fit uses 500, best fit uses 500 (the smallest that fits), worst fit uses 500.

## Common mistakes

Mixing up internal fragmentation (wasted space inside a block) and external fragmentation (free space split into pieces). Forgetting that compaction is expensive.

## Practice question

Explain why paging removes external fragmentation.

## Worked solution

<!-- type: solution -->

All frames are the same size, so any free frame can hold any page. The free space never splits into unusable pieces; only the last page of a process wastes space internally.
