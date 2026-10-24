/**
 * The largest zoom between 1 and `max` at which `fits` holds, by bisection to within a
 * hundredth. 1 when even that does not fit: content never shrinks below its own size.
 */
export function largestFit(fits: (zoom: number) => boolean, max: number): number {
  if (fits(max)) return max
  let low = 1
  let high = max
  while (high - low > 0.005) {
    const mid = (low + high) / 2
    if (fits(mid)) low = mid
    else high = mid
  }
  return low
}
