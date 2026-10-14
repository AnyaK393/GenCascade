# Linked lists

## Concept

A linked list is a chain of nodes, each holding a value and a pointer to the next node. Insertion and deletion at a known node are O(1), but finding the i-th element needs O(i) traversal.

## Example

To insert 7 after node A in A -> B, create node N(7), set N.next = B, then set A.next = N.

## Common mistakes

Changing A.next before saving B, which loses the rest of the list. Forgetting the empty-list and single-node cases. Not updating the tail pointer.

## Practice question

Reverse a singly linked list in place and return the new head.

## Worked solution

<!-- type: solution -->

Keep prev = None and cur = head. While cur exists: save nxt = cur.next, set cur.next = prev, move prev = cur and cur = nxt. Return prev.
