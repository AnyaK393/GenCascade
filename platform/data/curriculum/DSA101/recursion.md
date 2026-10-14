# Recursion

## Concept

A recursive function solves a problem by calling itself on smaller inputs until it reaches a base case. Each call takes a frame on the call stack, so the depth affects memory.

## Example

factorial(n) = 1 if n <= 1, else n * factorial(n - 1). factorial(4) expands to 4 * 3 * 2 * 1.

## Common mistakes

A missing or unreachable base case causes infinite recursion and a stack overflow. Recomputing the same subproblems (naive Fibonacci is O(2^n)); memoise them.

## Practice question

Write a recursive function that returns all subsets of a list.

## Worked solution

<!-- type: solution -->

subsets([]) = [[]]. For [x] + rest, compute S = subsets(rest) and return S plus x added to every set in S.
