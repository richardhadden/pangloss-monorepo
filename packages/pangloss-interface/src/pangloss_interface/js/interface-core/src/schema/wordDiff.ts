// The words of two texts, added and removed (a longest common subsequence of words, the spaces kept with them), as a
// text that changed is shown

export interface Piece {
  text: string;
  kind: "same" | "added" | "removed";
}

// (beyond this, a word diff is too slow to be worth it: the whole text is said to be replaced)
const MOST = 250_000;

const tokens = (text: string) => text.match(/\s+|[^\s]+/g) ?? [];

/** The pieces of the two texts in order: what is in both, what only `before` has, and what only `after` has */
export function wordDiff(before: string, after: string): Piece[] {
  const a = tokens(before);
  const b = tokens(after);
  if (a.length * b.length > MOST) {
    return [
      ...(before ? [{ text: before, kind: "removed" as const }] : []),
      ...(after ? [{ text: after, kind: "added" as const }] : []),
    ];
  }
  // (lengths of the common subsequence of the rests: table[i][j] for a[i..], b[j..])
  const table = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i]![j] = a[i] === b[j] ? table[i + 1]![j + 1]! + 1 : Math.max(table[i + 1]![j]!, table[i]![j + 1]!);
    }
  }
  const pieces: Piece[] = [];
  const push = (text: string, kind: Piece["kind"]) => {
    const last = pieces[pieces.length - 1];
    if (last && last.kind === kind) last.text += text;
    else pieces.push({ text, kind });
  };
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push(a[i]!, "same");
      i++;
      j++;
    } else if (table[i + 1]![j]! >= table[i]![j + 1]!) {
      push(a[i++]!, "removed");
    } else {
      push(b[j++]!, "added");
    }
  }
  while (i < a.length) push(a[i++]!, "removed");
  while (j < b.length) push(b[j++]!, "added");
  return pieces;
}
