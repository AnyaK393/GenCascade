# Hash tables

## Concept

A hash table maps a key through a hash function to a bucket index, giving O(1) average insert and lookup. Collisions are handled by chaining (a list per bucket) or open addressing (probing).

## Example

With 7 buckets and h(k) = k mod 7, keys 10 and 24 both land in bucket 3; chaining stores both in bucket 3's list.

## Common mistakes

Assuming O(1) in the worst case: with many collisions lookups degrade to O(n). Forgetting to resize when the load factor grows. Using mutable objects as keys.

## Practice question

Given an array and a target, return the indices of two numbers that add up to the target in O(n).

## Worked solution

<!-- type: solution -->

Scan once with a map from value to index. For each x, if target - x is in the map, return both indices; otherwise store x.
