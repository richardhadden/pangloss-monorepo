// (whole class names, so that Tailwind finds them)
export const inputClass =
  "w-full min-w-0 rounded-sm border-[0.5px] border-slate-400/70 bg-white/80 px-2 py-1.5 text-sm focus:border-slate-600 focus:outline-none";

// (a value that is short whatever it is: a number, a date, a date and time)
export const numberWidthClass = "max-w-48";
export const dateWidthClass = "max-w-56";
export const dateTimeWidthClass = "max-w-64";

export const smallButtonClass =
  "inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/60 px-2 py-1 text-xs font-semibold uppercase select-none hover:bg-slate-300/50";

// (a button joined on to the right end of a box, such as the search for an entity)
export const joinedButtonClass =
  "flex shrink-0 cursor-pointer items-center gap-1 border-l-[0.5px] border-slate-400/70 bg-slate-100/60 px-3 text-xs font-semibold uppercase select-none hover:bg-slate-300/50 focus:bg-slate-300/50 focus:outline-none";

// (the same, to take out what it is joined to)
export const joinedRemoveClass =
  "flex shrink-0 cursor-pointer items-center border-l-[0.5px] border-slate-400/70 bg-slate-100/60 px-2.5 text-xs text-red-800 select-none hover:bg-red-400/30 focus:bg-red-400/30 focus:outline-none";

/**
 * A box with something joined on to its right end (a remove button): the box's own border and
 * corners are taken off, and this frame has them. (The input inside is still `inputClass`.)
 */
export const joinedFrameClass =
  "flex w-full min-w-0 items-stretch overflow-hidden rounded-sm border-[0.5px] border-slate-400/70 bg-white/80 focus-within:border-slate-600 [&_input]:rounded-none [&_input]:border-0 [&_select]:rounded-none [&_select]:border-0 [&>div]:rounded-none [&>div]:border-0";

// (the place at the end of a list where the next one is added: as wide as what is in the list)
export const addSlotClass =
  "flex w-full cursor-pointer items-center justify-center gap-1 rounded-sm border-[0.5px] border-dashed border-slate-400/80 px-3 py-1.5 text-xs font-semibold text-slate-500 uppercase select-none hover:border-slate-600 hover:bg-slate-100/60 hover:text-slate-800 focus:border-slate-600 focus:outline-none";

// (what a nested thing's fields are in: indented, with a rule down the left in the colour of its type)
export const nestedClass = "flex min-w-0 flex-col gap-5 self-stretch border-l-2 pl-4";

// (the type of a nested thing, the left end of its head bar, as tall as the bar: tinted by its kind or its
// model's colour; a type with no tint of its own, such as a reified relation, has a plain one, so it still reads as a chip)
export const typeChipClass = "flex shrink-0 items-center px-2.5 py-1 text-xs font-semibold uppercase select-none";
export const plainTint = "bg-slate-400/20 text-slate-800";

// (the head line of a nested thing: a faint bar as wide as it, so that where each one starts is plain to see;
// its type at the left end, then its label (`headLabelClass`), then any buttons, each as tall as the bar)
export const headBarClass = "flex min-w-0 items-stretch overflow-hidden rounded-sm bg-slate-400/10";
export const headLabelClass = "min-w-0 flex-1 self-center truncate px-3 py-1 text-sm";

// (the same bar as a link to the item: it darkens as a chip does, the type's tint with it)
export const headBarLinkClass = "hover:bg-slate-400/25 active:bg-slate-400/40";

// (a button at the right end of a head bar)
export const headButtonClass = "flex cursor-pointer items-center px-3 text-xs select-none";
