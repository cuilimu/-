
# Fix Stack Overflow in Bivariate Analysis

## Problem Identified
The "Maximum call stack size exceeded" error is caused by **deep recursion** in the merge sort algorithm used for Kendall Tau calculation. While the theoretical recursion depth is only ~20 levels for 600k rows, there are two contributing factors:

1. **Recursive merge sort** (`mergeCountInversions`) uses function calls that add stack frames
2. **Multiple `.sort()` calls** on large arrays may use recursive algorithms internally
3. **Combined recursion depth** from nested operations can exceed browser limits

## Solution
Convert the recursive merge sort to an **iterative (bottom-up) merge sort**. This eliminates recursion entirely while maintaining O(n log n) complexity.

### Algorithm Change
```text
BEFORE (recursive, top-down):
  function mergeSort(arr):
    if arr.length <= 1: return arr
    mid = arr.length / 2
    left = mergeSort(arr[0:mid])     // Recursive call
    right = mergeSort(arr[mid:])     // Recursive call
    return merge(left, right)

AFTER (iterative, bottom-up):
  function mergeSort(arr):
    for width = 1; width < n; width *= 2:
      for i = 0; i < n; i += 2*width:
        merge(arr, i, i+width, i+2*width)
    return arr
```

### Benefits
| Aspect | Recursive | Iterative |
|--------|-----------|-----------|
| Stack usage | O(log n) frames | O(1) frames |
| Risk of overflow | Possible | None |
| Performance | Same O(n log n) | Same O(n log n) |
| Memory | O(n) auxiliary | O(n) auxiliary |

## Implementation Details

### File: `src/lib/bivariateStatistics.ts`

Replace the recursive `mergeCountInversions` (lines 168-184) with an iterative version:

```typescript
function mergeCountInversions(arr: number[]): { sorted: number[]; inversions: number; ties: number } {
  const n = arr.length;
  if (n <= 1) return { sorted: arr.slice(), inversions: 0, ties: 0 };
  
  let inversions = 0;
  let ties = 0;
  
  // Work array to avoid repeated allocations
  let source = arr.slice();
  let target = new Array(n);
  
  // Bottom-up merge sort: start with width=1, double each pass
  for (let width = 1; width < n; width *= 2) {
    for (let i = 0; i < n; i += 2 * width) {
      const left = i;
      const mid = Math.min(i + width, n);
      const right = Math.min(i + 2 * width, n);
      
      // Merge source[left..mid) and source[mid..right) into target[left..right)
      const result = mergeAndCountInPlace(source, target, left, mid, right);
      inversions += result.inversions;
      ties += result.ties;
    }
    // Swap source and target
    [source, target] = [target, source];
  }
  
  return { sorted: source, inversions, ties };
}

function mergeAndCountInPlace(
  source: number[],
  target: number[],
  left: number,
  mid: number,
  right: number
): { inversions: number; ties: number } {
  let inversions = 0;
  let ties = 0;
  let i = left;
  let j = mid;
  let k = left;
  
  while (i < mid && j < right) {
    if (source[i] < source[j]) {
      target[k++] = source[i++];
    } else if (source[i] > source[j]) {
      inversions += mid - i;
      target[k++] = source[j++];
    } else {
      // Count consecutive equal values
      const val = source[i];
      let leftCount = 0, rightCount = 0;
      while (i < mid && source[i] === val) { leftCount++; i++; }
      while (j < right && source[j] === val) { rightCount++; j++; }
      ties += leftCount * rightCount;
      for (let c = 0; c < leftCount + rightCount; c++) target[k++] = val;
    }
  }
  
  while (i < mid) target[k++] = source[i++];
  while (j < right) target[k++] = source[j++];
  
  return { inversions, ties };
}
```

## Files to Modify

| File | Changes |
|------|---------|
| `src/lib/bivariateStatistics.ts` | Replace recursive `mergeCountInversions` with iterative bottom-up version; update `mergeAndCount` to work with in-place operations |

## Technical Notes

- The iterative version uses only O(1) stack frames regardless of array size
- Swaps between two arrays (`source`/`target`) to avoid repeated allocations
- Maintains the same tie counting and inversion counting logic
- Compatible with the existing Kendall Tau-b formula

## Testing
After implementation, bivariate analysis on 600k+ rows should complete without any stack overflow errors, regardless of data patterns.
