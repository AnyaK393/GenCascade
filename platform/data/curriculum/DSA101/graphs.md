# Graphs: BFS and DFS

## Concept

A graph is a set of vertices and edges, stored as an adjacency list or matrix. Breadth-first search explores level by level with a queue and finds shortest paths in unweighted graphs; depth-first search goes deep using a stack or recursion.

## Example

BFS from A in A-B, A-C, B-D visits A, then B and C, then D, so D is at distance 2.

## Common mistakes

Forgetting the visited set, which loops forever on cycles. Marking a node visited when it is dequeued rather than enqueued in BFS, which adds duplicates.

## Practice question

Count the connected components of an undirected graph.

## Worked solution

<!-- type: solution -->

Loop over all vertices; whenever one is unvisited, increment the count and run BFS or DFS from it to mark its whole component.
