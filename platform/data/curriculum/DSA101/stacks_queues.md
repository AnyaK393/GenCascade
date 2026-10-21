# Stacks and queues

## Concept

A stack is last-in first-out (push and pop at the top); a queue is first-in first-out (enqueue at the back, dequeue at the front). Both give O(1) operations with an array or linked list.

## Example

Checking balanced brackets: push each opening bracket, and on a closing bracket pop and check that the pair matches. The string is balanced if the stack is empty at the end.

## Common mistakes

Popping from an empty stack without checking. Using a plain array as a queue and shifting on every dequeue, which makes it O(n); use a circular buffer or deque.

## Practice question

Implement a queue using two stacks, with amortised O(1) per operation.

## Worked solution

<!-- type: solution -->

Push to an in-stack. On dequeue, if the out-stack is empty, pop everything from the in-stack onto it, then pop from the out-stack. Each element moves at most twice.
