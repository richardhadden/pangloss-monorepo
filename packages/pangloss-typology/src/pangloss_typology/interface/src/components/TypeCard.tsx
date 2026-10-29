import type { ViewCardProps } from "@pangloss/interface-core";

// A type wherever it is part of something else (a result, a reference): its label, marked as a type.
// It draws the item itself: the interface's own button for the model would ask for this card again.
export default function TypeCard(props: ViewCardProps) {
  return (
    <a
      href={props.href ?? `/${props.type}/${props.id ?? ""}`}
      class="flex w-full items-center gap-3 rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/70 px-4 py-3 text-sm hover:bg-slate-200/70"
    >
      <span class="text-xs font-semibold uppercase">{props.type}</span>
      <span class="rounded-sm border-[0.5px] border-slate-400/70 px-1 text-[0.65rem] uppercase text-slate-600">
        type
      </span>
      <span class="min-w-0 truncate">{props.label}</span>
    </a>
  );
}
