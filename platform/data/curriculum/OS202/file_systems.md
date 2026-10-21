# File systems

## Concept

A file system maps names to data blocks. Directories map names to inodes, and inodes hold metadata and block pointers (direct, single, double and triple indirect). Allocation can be contiguous, linked (FAT) or indexed.

## Example

With 4 KB blocks and 12 direct pointers, the first 48 KB of a file need no indirect block.

## Common mistakes

Thinking the filename is stored in the inode (it is in the directory entry). Forgetting that a hard link adds a directory entry pointing to the same inode.

## Practice question

With 4 KB blocks and 4-byte pointers, how much data can a single indirect block address?

## Worked solution

<!-- type: solution -->

One block holds 4096 / 4 = 1024 pointers, each to a 4 KB block: 1024 * 4 KB = 4 MB.
