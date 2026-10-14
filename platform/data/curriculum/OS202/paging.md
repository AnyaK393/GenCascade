# Paging

## Concept

Paging splits logical memory into pages and physical memory into frames of the same size. A page table maps page numbers to frames; an address is (page number, offset). A TLB caches recent translations.

## Example

With 4 KB pages, the logical address 8200 is page 2 (8200 // 4096) at offset 8; if page 2 maps to frame 5, the physical address is 5 * 4096 + 8 = 20488.

## Common mistakes

Forgetting that every memory access needs a page-table lookup without a TLB. Mixing up the number of page-number bits and offset bits.

## Practice question

With a 32-bit address and 4 KB pages, how many entries does a single-level page table have?

## Worked solution

<!-- type: solution -->

The offset needs 12 bits, which leaves 20 bits for the page number: 2^20 ≈ 1 million entries.
