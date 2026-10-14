# Disk scheduling

## Concept

Disk scheduling orders requests to reduce head movement. FCFS is fair but slow, SSTF picks the nearest request (and can starve far ones), SCAN sweeps like an elevator, and C-SCAN returns to the start for more uniform waits.

## Example

Head at 53 with requests 98, 183, 37, 122: SSTF serves 37 first (distance 16), then 98, 122, 183.

## Common mistakes

Forgetting the direction of travel in SCAN. Counting the return sweep of C-SCAN inconsistently between methods.

## Practice question

Total head movement for SCAN (moving up, disk 0-199) from 53 with requests 98, 183, 37, 122, 14.

## Worked solution

<!-- type: solution -->

Go up 53 -> 98 -> 122 -> 183 -> 199 (146 cylinders), then down 199 -> 37 -> 14 (185 cylinders): 331 in total.
