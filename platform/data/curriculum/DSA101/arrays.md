# Arrays

## Concept

An array stores elements of one type in contiguous memory, so element i is found at base + i * size in O(1). Inserting or deleting in the middle needs shifting, which costs O(n).

## Example

In [4, 8, 15, 16], reading index 2 returns 15 immediately. Inserting 5 at index 1 shifts 8, 15 and 16 one place right.

## Common mistakes

Off-by-one errors at the last index (n - 1, not n). Assuming dynamic arrays never copy: a resize copies every element, although amortised append is still O(1).

## Practice question

Write a function that rotates an array of n elements left by k positions using O(1) extra space.

## Worked solution

<!-- type: solution -->

Reverse the first k elements, reverse the remaining n - k, then reverse the whole array. Each reversal is O(n) and in place.
