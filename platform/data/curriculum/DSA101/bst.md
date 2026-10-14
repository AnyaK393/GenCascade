# Binary search trees

## Concept

A binary search tree keeps every key in the left subtree smaller and every key in the right subtree larger than the node. Search, insert and delete take O(h), where h is the height.

## Example

Inserting 8, 3, 10, 1, 6 gives root 8, left child 3 (children 1 and 6) and right child 10. An inorder traversal prints 1 3 6 8 10.

## Common mistakes

Checking only a node's direct children instead of the whole subtree range when validating. Inserting sorted keys, which makes the tree a linked list with height n.

## Practice question

Check whether a binary tree is a valid BST.

## Worked solution

<!-- type: solution -->

Recurse with bounds: valid(node, lo, hi) requires lo < node.key < hi, then valid(left, lo, key) and valid(right, key, hi).
