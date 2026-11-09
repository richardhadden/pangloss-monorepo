// The one look of a table (docs/look-and-feel): a heading row as the frame's text is, rows divided by a
// faint hairline, a faint hover. An item in a cell is a `ReferenceChip`; actions in a row are `quiet`
// buttons; a state is a `badgeClass`. Whole class names, so that Tailwind finds them.

export const tableClass = "w-full border-collapse text-sm";
export const tableHeadRowClass =
  "border-b-[0.5px] border-slate-400/70 text-left text-xs font-semibold text-slate-500 uppercase";
export const tableHeadCellClass = "py-2 pr-3.5 font-semibold last:pr-0";
export const tableRowClass = "border-b-[0.5px] border-slate-500/30 hover:bg-slate-50";
export const tableCellClass = "py-1.75 pr-3.5 last:pr-0";
