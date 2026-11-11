import { DefaultReferenceChip, kindRule, kindTint, typeChipClass, useModels, useTranslations } from "@pangloss/interface-core";
import type { JSX } from "@solidjs/web";

// A button that ends a mention's chip (the spanner, the ✕ of a form): as tall as the chip, and as wide as that
// (a chip is 30px tall: a line of `text-sm`, `py-1` and its hairlines; `aspect-square` does not size a stretched
// flex item by its height)
export const mentionButtonClass =
  "flex w-7.5 shrink-0 cursor-pointer items-center justify-center border-[0.5px] border-l-0 border-slate-400/70 bg-slate-100/70 text-xs select-none last:rounded-r-xs";

/**
 * An unreconciled mention, wherever it is shown: two chips as one, "Unreconciled" (in the colour of its model: rose)
 * and then the chip of what it would be, a type and what the source calls it; then any buttons (`children`).
 */
export function MentionChip(props: { type: string; label: string; href?: string; children?: JSX.Element }) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  const colour = () => definitions.models.Unreconciled?.interfaceMeta?.colour ?? "rose";
  return (
    <span class="inline-flex max-w-full min-w-0 items-stretch" data-testid="mention-chip">
      <span
        data-type-info="Unreconciled"
        data-tint
        class={[typeChipClass, "rounded-r-none border-r-0", kindTint("Document", colour()), kindRule("Document", colour())]}
      >
        {modelName("Unreconciled")}
      </span>
      {/* (joined to its neighbours: no rounding where it touches the first chip, nor, when buttons follow, where it
          touches them. Its frame and its type each round their own corners, so it is said of all that is in it) */}
      <span class="contents [&_*]:rounded-l-none [&:not(:last-child)_*]:rounded-r-none">
        <DefaultReferenceChip type={props.type} label={props.label} href={props.href} />
      </span>
      {props.children}
    </span>
  );
}
