import type { ViewCardProps } from "@pangloss/interface-core";

// A card for an item, wherever it is part of something else (a result in a list, a reference,
// an embedded item). Use it from a model:
//
//     class Thing(Entity):
//         _interface_meta = InterfaceMeta(view_card="{{app}}:ExampleCard")
//
// It replaces the interface's own button or chip for the model, so it draws the item itself: it must
// not render `ResultButton` or `ReferenceChip` for the same type (they would ask for this card again).
// Other components are got with `useComponent` (so that a project's override reaches here); never
// destructure props (Solid 2.0).
export default function ExampleCard(props: ViewCardProps) {
  return (
    <a
      href={props.href ?? `/${props.type}/${props.id ?? ""}`}
      class="flex w-full items-center gap-3 rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/70 px-4 py-3 text-sm hover:bg-slate-200/70"
    >
      <span class="text-xs font-semibold uppercase">{props.type}</span>
      <span class="min-w-0 truncate">{props.label}</span>
    </a>
  );
}
