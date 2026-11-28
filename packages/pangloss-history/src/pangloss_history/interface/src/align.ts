// Several versions of an item lined up, row by row: core's (`interface-core`, `schema/align.ts`), where comparison's
// page of two statements uses it too. (implementation_docs/history.md)
export {
  align,
  changedRows,
  isEmptyValue as isEmpty,
  mergeOrder,
  sameAlignedValue as sameValue,
} from "@pangloss/interface-core";
export type {
  AlignedCellOf as Cell,
  AlignedRow,
  AlignMark as Mark,
  AlignStep as Step,
} from "@pangloss/interface-core";
