# Processes

## Concept

A process is a program in execution with its own address space, registers and a process control block (PCB). It moves between the new, ready, running, waiting and terminated states; a context switch saves one PCB and loads another.

## Example

fork() creates a child that is a copy of the parent; fork returns 0 in the child and the child's PID in the parent.

## Common mistakes

Thinking fork shares variables between parent and child (memory is copied, with copy-on-write). Forgetting to wait() for children, which leaves zombies.

## Practice question

How many times does 'hi' print in: fork(); fork(); printf("hi");?

## Worked solution

<!-- type: solution -->

Four. Each fork doubles the number of processes: 1 -> 2 -> 4, and each prints once.
