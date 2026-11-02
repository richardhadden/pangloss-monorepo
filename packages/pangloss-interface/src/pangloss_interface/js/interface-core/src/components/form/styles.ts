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
  "flex w-8 shrink-0 cursor-pointer items-center justify-center border-l-[0.5px] border-slate-400/70 bg-slate-100/60 text-xs text-red-800 select-none hover:bg-red-400/30 focus:bg-red-400/30 focus:outline-none";

/**
 * A box with something joined on to its right end (a remove button): the box's own border and
 * corners are taken off, and this frame has them. (The input inside is still `inputClass`.)
 */
export const joinedFrameClass =
  "flex w-full min-w-0 items-stretch overflow-hidden rounded-sm border-[0.5px] border-slate-400/70 bg-white/80 focus-within:border-slate-600 [&_input]:rounded-none [&_input]:border-0 [&_select]:rounded-none [&_select]:border-0 [&>div]:rounded-none [&>div]:border-0";

// (the place at the end of a list where the next one is added: as wide as what is in the list)
export const addSlotClass =
  "flex w-full cursor-pointer items-center justify-center gap-1 rounded-sm border-[0.5px] border-dashed border-slate-400/80 px-3 py-1.5 text-xs font-semibold text-slate-500 uppercase select-none hover:border-slate-600 hover:bg-slate-100/60 hover:text-slate-800 focus:border-slate-600 focus:outline-none";

// (a field's row, a name and what is in it, in a grid of fields: a faint rule above each but the first, so
// that where one field ends and the next starts is plain to see; translucent, so it shows on a tinted space too)
export const fieldRuleClass = "border-slate-500/15";
export const fieldRowClass = `col-span-2 grid grid-cols-subgrid border-t ${fieldRuleClass} pt-5 first:border-t-0 first:pt-0`;
export const fieldGridClass = "grid w-full grid-cols-[10rem_minmax(0,1fr)] gap-x-6 gap-y-5";

// (what a nested thing's fields are in: indented, with a rule down the left in the colour of its type)
export const nestedClass = "flex min-w-0 flex-col gap-5 self-stretch border-l-2 pl-4";

// (the type of a nested thing, the left end of its head bar, as tall as the bar: tinted by its kind or its
// model's colour; a type with no tint of its own, such as a reified relation, has a plain one, so it still reads as a chip;
// framed in the colour of the rule that hangs from it (`kindRule`, given with it), so the two meet in one colour)
export const typeChipClass =
  "flex shrink-0 items-center rounded-l-sm border-[0.5px] px-2.5 py-1 text-xs font-semibold uppercase select-none";
export const plainTint = "bg-slate-400/20 text-slate-800";

// (the head line of a nested thing: a faint bar as wide as it, so that where each one starts is plain to see;
// its type at the left end (`typeChipClass`), then the rest (`headRestClass`): its label (`headLabelClass`), then any
// buttons, each as tall as the bar, framed by the same hairline as a chip or a field, since it is something you act on)
export const headBarClass = "flex min-w-0 items-stretch rounded-sm bg-slate-400/10";
export const headRestClass =
  "flex min-w-0 flex-1 items-stretch overflow-hidden rounded-r-sm border-[0.5px] border-l-0 border-slate-400/70";
// (the same, where a button in it opens a menu, which hiding the overflow would cut off: its last button is rounded
// instead, so that its colour on hover keeps to the corner)
export const headRestOpenClass =
  "flex min-w-0 flex-1 items-stretch rounded-r-sm border-[0.5px] border-l-0 border-slate-400/70 [&>:last-child]:rounded-r-sm";
export const headLabelClass = "min-w-0 flex-1 self-center truncate px-3 py-1 text-sm";

// (the same bar as a link to the item: it darkens as a chip does, the type's tint with it)
export const headBarLinkClass = "hover:bg-slate-400/25 active:bg-slate-400/40";

// (a semantic space's type and buttons: no bar; its type a plain label, its buttons a tab in the top right
// corner of its box, with the hairline on their inner sides, divided as in a head bar)
export const spaceTypeClass = "px-3 py-1.5 text-xs font-semibold uppercase select-none";
export const spaceButtonsClass =
  "flex self-start overflow-hidden rounded-tr-sm rounded-bl-sm border-b-[0.5px] border-slate-400/70";

// (a button at the right end of a head bar, with a hairline before it, as in a reference chip: square, as wide as
// the bar is tall)
export const headButtonClass =
  "flex w-7 shrink-0 cursor-pointer items-center justify-center border-l-[0.5px] border-slate-400/70 text-xs select-none";
// (the same, as wide as what it says: a button that opens a menu has its ▾ too)
export const headMenuButtonClass =
  "flex min-w-7 shrink-0 cursor-pointer items-center justify-center gap-0.5 border-l-[0.5px] border-slate-400/70 px-1.5 text-xs select-none";
