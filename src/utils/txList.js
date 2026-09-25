// A provider fee is shown as its own history row right after the operation it
// belongs to (id `<parentId>-fee`). Short lists ("3 latest") must count
// OPERATIONS, not rows — otherwise the cut can fall between a purchase and
// its fee and the fee silently disappears from the screen.
export function latestOperations(list, count) {
  const out = []
  let ops = 0
  for (const tx of list || []) {
    const isFee = tx.type === 'fee'
    if (!isFee) {
      if (ops >= count) break
      ops += 1
    }
    out.push(tx)
  }
  return out
}
