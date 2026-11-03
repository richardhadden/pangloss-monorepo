/**
 * Shares (`SumsTo`): whole numbers, each at least a minimum, that add up to a total (the percentages of
 * alternatives). When one is changed, one is added or one is taken away, the others give way in proportion to
 * what they had above the minimum; if none had anything above it, they share equally.
 */

/**
 * `amount` shared among as many as there are `weights`: each at least `min`, the rest in proportion to the weights
 * above `min`, rounded so that they add up (the remainders go to the largest fractions, the first first)
 */
export function apportion(weights: number[], amount: number, min: number): number[] {
  const count = weights.length;
  if (count === 0) return [];
  const rest = amount - count * min;
  if (rest <= 0) return weights.map(() => min);
  const above = weights.map((weight) => Math.max((Number.isFinite(weight) ? weight : 0) - min, 0));
  const sum = above.reduce((a, b) => a + b, 0);
  const exact = above.map((weight) => (sum > 0 ? (rest * weight) / sum : rest / count));
  const shares = exact.map(Math.floor);
  let left = rest - shares.reduce((a, b) => a + b, 0);
  const order = exact.map((value, index) => ({ index, fraction: value - Math.floor(value) }));
  order.sort((a, b) => b.fraction - a.fraction || a.index - b.index);
  for (const { index } of order) {
    if (left <= 0) break;
    shares[index]! += 1;
    left -= 1;
  }
  return shares.map((share) => share + min);
}

/** The most one can have, leaving each of the `count - 1` others its `min` */
const most = (count: number, total: number, min: number) => Math.max(total - (count - 1) * min, min);

/** The one at `index` is `value` (kept to what leaves the others their minimum); the others share the rest */
export function adjust(shares: number[], index: number, value: number, total: number, min: number): number[] {
  if (shares.length <= 1) return shares.map(() => total);
  const own = Math.min(Math.max(Math.round(value), min), most(shares.length, total, min));
  const others = apportion(
    shares.filter((_, at) => at !== index),
    total - own,
    min,
  );
  others.splice(index, 0, own);
  return others;
}

/** One more, at the end: it is given an even share (`total / (n + 1)`), and the others share the rest */
export function added(shares: number[], total: number, min: number): number[] {
  const count = shares.length + 1;
  if (count === 1) return [total];
  const own = Math.min(Math.max(Math.round(total / count), min), most(count, total, min));
  return [...apportion(shares, total - own, min), own];
}

/** The one at `index` taken away: the others share the whole */
export function removed(shares: number[], index: number, total: number, min: number): number[] {
  return apportion(
    shares.filter((_, at) => at !== index),
    total,
    min,
  );
}
