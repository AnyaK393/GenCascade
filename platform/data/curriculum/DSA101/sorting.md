# Sorting

## Concept

Comparison sorts like merge sort and heap sort run in O(n log n); quicksort averages O(n log n) but can be O(n^2) with bad pivots. A stable sort keeps equal keys in their original order.

## Example

Merge sort on [5, 2, 4, 1] splits into [5, 2] and [4, 1], sorts them to [2, 5] and [1, 4], then merges to [1, 2, 4, 5].

## Common mistakes

Choosing the first element as pivot on already sorted input, which gives quicksort O(n^2). Forgetting to copy the leftover elements when merging.

## Practice question

Sort an array of only 0s, 1s and 2s in one pass.

## Worked solution

<!-- type: solution -->

Dutch national flag: keep low, mid and high pointers. A 0 swaps with low (advance both), a 1 advances mid, a 2 swaps with high (decrement high only).
