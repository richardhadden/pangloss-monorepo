import { buttonClass } from "../../primitives";

// (whole class names, so that Tailwind finds them)
export const inputClass =
  "w-full min-w-0 rounded-xs border-[0.5px] border-slate-400/70 bg-white/80 px-2 py-1.5 text-sm focus:border-slate-600 focus:outline-none";

// (a value that is short whatever it is: a number, a date, a date and time)
export const numberWidthClass = "max-w-48";
export const dateWidthClass = "max-w-56";
export const dateTimeWidthClass = "max-w-64";

// (an ordinary button, of the one look: `buttonClass`)
export const smallButtonClass = buttonClass("ordinary", "sm");

// (a button that adds one type of what a relation holds, under its search: given the tint of the type)
export const choiceButtonClass =
  "inline-flex h-6.5 shrink-0 cursor-pointer items-center gap-1 rounded-xs border-[0.5px] border-slate-400/70 px-2.5 text-xs font-semibold uppercase select-none hover:brightness-95 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-slate-500/60 active:brightness-90";

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
  "flex w-full min-w-0 items-stretch overflow-hidden rounded-xs border-[0.5px] border-slate-400/70 bg-white/80 focus-within:border-slate-600 [&_input]:rounded-none [&_input]:border-0 [&_select]:rounded-none [&_select]:border-0 [&>div]:rounded-none [&>div]:border-0";

// (the place at the end of a list where the next one is added: as wide as what is in the list)
export const addSlotClass = `${buttonClass("add", "sm")} w-full`;

// (a field's row, a name and what is in it, in a grid of fields: a faint rule above each but the first, so
// that where one field ends and the next starts is plain to see; translucent, so it shows on a tinted space too)
export const fieldRuleClass = "border-slate-500/15";
// (the name on the left and what is in the field on the right while there is room. In a narrow place (a document
// nested several deep: `@container`, the thing it is nested in, is what the rows measure themselves by) the name
// goes above, close to it, and the whole width is the field's (under 28rem); with less room still (under 24rem)
// the rows draw closer together too)
export const fieldRowClass = `col-span-full grid grid-cols-subgrid gap-y-1.5 border-t ${fieldRuleClass} pt-5 first:border-t-0 first:pt-0 @max-sm:pt-3`;
export const fieldGridClass =
  "grid w-full grid-cols-[10rem_minmax(0,1fr)] gap-x-6 gap-y-5 @max-md:grid-cols-1 @max-sm:gap-y-3";

// (what a nested thing's fields are in: indented, with a rule down the left in the colour of its type. The indent,
// and the paddings of what is in it, get smaller as the room does (under 28rem), and all but vanish when there is
// hardly any (under 24rem): the rules down the left still show how deep a thing is, as the bars of a quoted letter
// do, and each further level costs a few pixels instead of thirty. There, the fields also keep a floor of 14rem,
// whatever is left: each level then steps out to the right of the one above it by its few pixels, a staircase the
// page scrolls sideways for, and a document nested sixty deep is still read at the bottom. The `ml-2` given with
// this class goes with the indent)
export const nestedClass =
  "@container flex min-w-0 flex-col gap-5 self-stretch border-l-2 pl-4 @max-md:pl-2 @max-sm:ml-0 @max-sm:min-w-56 @max-sm:gap-3 @max-sm:pl-1";
// (the padding of a semantic space's band round what is in it, which gives way in the same steps)
export const spacePaddingClass = "p-3 @max-md:p-1.5 @max-sm:px-0.5 @max-sm:py-1";

// (the type of a nested thing, the left end of its head bar, as tall as the bar: tinted by its kind or its
// model's colour; a type with no tint of its own, such as a reified relation, has a plain one, so it still reads as a chip;
// framed in the colour of the rule that hangs from it (`kindRule`, given with it), so the two meet in one colour)
export const typeChipClass =
  "flex shrink-0 items-center rounded-l-xs border-[0.5px] px-2.5 py-1 text-xs font-semibold uppercase select-none @max-sm:px-1";
export const plainTint = "bg-slate-400/20 text-slate-800";

// (the head line of a nested thing: a faint bar as wide as it, so that where each one starts is plain to see;
// its type at the left end (`typeChipClass`), then the rest (`headRestClass`): its label (`headLabelClass`), then any
// buttons, each as tall as the bar, framed by the same hairline as a chip or a field, since it is something you act on)
export const headBarClass = "flex min-w-0 items-stretch rounded-xs bg-slate-400/10";
export const headRestClass =
  "flex min-w-0 flex-1 items-stretch overflow-hidden rounded-r-xs border-[0.5px] border-l-0 border-slate-400/70";
// (the same, as a link, with the buttons after it and outside it: they close the frame)
export const headRestLinkClass =
  "flex min-w-0 flex-1 items-stretch overflow-hidden border-y-[0.5px] border-slate-400/70";
// (the same, where a button in it opens a menu, which hiding the overflow would cut off: its last button is rounded
// instead, so that its colour on hover keeps to the corner)
export const headRestOpenClass =
  "flex min-w-0 flex-1 items-stretch rounded-r-xs border-[0.5px] border-l-0 border-slate-400/70 [&>:last-child]:rounded-r-xs";
export const headLabelClass = "min-w-0 flex-1 self-center truncate px-3 py-1 text-sm @max-sm:px-1.5";

// (the same bar as a link to the item: it darkens as a chip that is a link does, `ReferenceChip`, to the same colour)
export const headBarLinkClass = "hover:bg-slate-200/70 active:bg-slate-300/70";

// (a semantic space's type and buttons: no bar; its type a plain label, its buttons a tab in the top right
// corner of its box, with the hairline on their inner sides, divided as in a head bar)
export const spaceTypeClass = "opacity-70 px-3 py-1.5 text-xs font-semibold uppercase select-none @max-sm:px-1";
export const spaceButtonsClass =
  "flex self-start overflow-hidden rounded-tr-xs rounded-bl-xs border-b-[0.5px] border-slate-400/70";

// (a button at the right end of a head bar, with a hairline before it, as in a reference chip: square, as wide as
// the bar is tall)
export const headButtonClass =
  "flex w-7 shrink-0 cursor-pointer items-center justify-center border-l-[0.5px] border-slate-400/70 text-xs select-none";
// (the same, as wide as what it says: a button that opens a menu has its ▾ too)
export const headMenuButtonClass =
  "flex min-w-7 shrink-0 cursor-pointer items-center justify-center gap-0.5 border-l-[0.5px] border-slate-400/70 px-1.5 text-xs select-none";
