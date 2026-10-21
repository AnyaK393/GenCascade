# Binary search

## Concept

Binary search finds a target in a sorted array by comparing with the middle element and discarding half the range each step, so it takes O(log n) comparisons.

## Example

Searching 23 in [2, 5, 8, 12, 16, 23, 38]: mid is 12, go right; mid of [16, 23, 38] is 23, found in two steps.

## Common mistakes

Infinite loops from updating lo = mid instead of mid + 1. Overflow in (lo + hi) / 2 in fixed-width languages. Using it on unsorted data.

## Practice question

Find the first index where a sorted array has a value >= x (lower bound).

## Worked solution

<!-- type: solution -->

lo = 0, hi = n. While lo < hi: mid = (lo + hi) // 2; if a[mid] < x then lo = mid + 1 else hi = mid. Return lo.
