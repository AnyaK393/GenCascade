# Heaps and priority queues

## Concept

A binary heap is a complete binary tree where every parent is <= its children (min-heap). Stored in an array, the children of i are 2i + 1 and 2i + 2. Insert and extract-min are O(log n).

## Example

Inserting 2 into the min-heap [3, 5, 8] appends it at index 3, then sifts up past 5 and 3, giving [2, 3, 8, 5].

## Common mistakes

Thinking a heap is fully sorted: only the root is guaranteed minimal. Building a heap with n inserts (O(n log n)) when bottom-up heapify is O(n).

## Practice question

Find the k largest elements of a stream of n numbers using O(k) memory.

## Worked solution

<!-- type: solution -->

Keep a min-heap of size k. Push each number; if the size exceeds k, pop the minimum. The heap holds the k largest.
