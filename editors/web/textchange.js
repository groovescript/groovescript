// Smallest single replacement turning one text into another: the common
// prefix and suffix stay, only the middle is replaced. Applying a format
// this way keeps the cursor, selection and undo history meaningful
// instead of replacing the whole document.

/**
 * @param {string} before
 * @param {string} after
 * @returns {{ from: number, to: number, insert: string } | null} null when equal
 */
export function minimalChange(before, after) {
  if (before === after) return null;
  let start = 0;
  const max = Math.min(before.length, after.length);
  while (start < max && before.charCodeAt(start) === after.charCodeAt(start)) start++;
  let endBefore = before.length;
  let endAfter = after.length;
  while (endBefore > start && endAfter > start
         && before.charCodeAt(endBefore - 1) === after.charCodeAt(endAfter - 1)) {
    endBefore--;
    endAfter--;
  }
  return { from: start, to: endBefore, insert: after.slice(start, endAfter) };
}
