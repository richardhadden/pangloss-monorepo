import {
  ApiError,
  badgeClass,
  getModel,
  kindRule,
  kindTint,
  numberBadgeClass,
  plainTint,
  typeChipClass,
  useComponent,
  useModels,
  useTranslations,
} from "@pangloss/interface-core";
import { For, Show } from "solid-js";
import type { ParentProps } from "solid-js";
import { itemHref } from "../api";
import type { HeadRef, MergeRecord, MergeState } from "../api";

// The small parts the merge pages share: the icon, an entity as a chip, the two entities of a merge, a state

export const reasonOf = (error: unknown) =>
  error instanceof ApiError ? error.detail : error instanceof Error ? error.message : String(error);

/** Two lines that become one (24-unit paths, as the console's) */
export function MergeIcon(props: { class?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      class={["shrink-0 select-none fill-none stroke-current stroke-[1.5]", props.class ?? "size-5"]}
      stroke-linecap="square"
      aria-hidden="true"
    >
      <path d="M5 4v4l7 6v6M19 4v4l-7 6" />
    </svg>
  );
}

/** An arrow from the entity absorbed to the one that stays */
export function IntoIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      class="size-4 shrink-0 fill-none stroke-current stroke-[1.75] text-slate-500 select-none"
      stroke-linecap="square"
      aria-hidden="true"
    >
      <path d="M4 12h15M13 6l6 6-6 6" />
    </svg>
  );
}

/** A document or entity named by a merge, as a chip that links to it */
export function HeadChip(props: { head: HeadRef; plain?: boolean }) {
  const ReferenceChip = useComponent("ReferenceChip");
  return (
    <ReferenceChip
      type={props.head.type}
      label={props.head.label ?? props.head.id}
      // (`plain`: no link, for an entity whose address shows another, as one that was absorbed)
      href={props.plain ? undefined : itemHref(props.head.type, props.head.id)}
    />
  );
}

/** The entity a merge absorbed and the one that stays, as the record knows them */
export function absorbedOf(record: MergeRecord): HeadRef {
  return { id: record.absorbed, type: record.absorbedType ?? "", label: record.absorbedLabel };
}
export function survivorOf(record: MergeRecord): HeadRef {
  return {
    id: record.survivor,
    type: record.survivorType ?? record.survivorTypeBefore ?? record.absorbedType ?? "",
    label: record.survivorLabel,
  };
}

/** The two entities of a merge: the one absorbed, an arrow, the one that stays */
export function Pair(props: { record: MergeRecord }) {
  return (
    <span class="inline-flex min-w-0 flex-wrap items-center gap-2" data-testid="merge-pair">
      <HeadChip head={absorbedOf(props.record)} />
      <IntoIcon />
      <HeadChip head={survivorOf(props.record)} />
    </span>
  );
}

// (whole class names, so that Tailwind finds them: yellow for what waits for someone, as everywhere)
const STATE_TONE: Record<MergeState, string> = {
  proposed: "bg-yellow-200 text-yellow-950",
  rejected: "bg-red-100 text-red-900",
  stale: "bg-slate-200 text-slate-700",
  running: "bg-amber-100 text-amber-900",
  done: "bg-slate-700 text-white",
  undone: "bg-slate-200 text-slate-700",
};

export function useStateWords() {
  const { t } = useTranslations();
  return (state: MergeState): string => {
    switch (state) {
      case "proposed":
        return t("merge_state_proposed", "Proposed");
      case "rejected":
        return t("merge_state_rejected", "Rejected");
      case "stale":
        return t("merge_state_stale", "Out of date");
      case "running":
        return t("merge_state_running", "Not finished");
      case "done":
        return t("merge_state_done", "Merged");
      case "undone":
        return t("merge_state_undone", "Undone");
    }
  };
}

export function StateBadge(props: { record: MergeRecord }) {
  const { t } = useTranslations();
  const words = useStateWords();
  return (
    <span class="inline-flex items-center gap-1.5">
      <span class={[badgeClass, STATE_TONE[props.record.state]]} data-testid="merge-state" data-state={props.record.state}>
        {words(props.record.state)}
      </span>
      <Show when={props.record.undoProposedBy && (props.record.state === "done" || props.record.state === "running")}>
        <span class={[badgeClass, STATE_TONE.proposed]} data-testid="merge-undo-proposed">
          {t("merge_state_undo_proposed", "Undo proposed")}
        </span>
      </Show>
    </span>
  );
}

/** How many of each type, each type a chip in its colour with the number joined on */
export function TypeCounts(props: { counts: [string, number][] }) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  const model = (type: string) => getModel(definitions, type);
  return (
    <span class="inline-flex flex-wrap items-center gap-2">
      <For each={props.counts}>
        {([type, count]) => (
          <span class="inline-flex items-stretch" data-testid="merge-type-count" data-type={type}>
            <span
              data-type-info={type}
              class={[
                typeChipClass,
                kindTint(model(type)?.kind, model(type)?.interfaceMeta?.colour) || plainTint,
                kindRule(model(type)?.kind, model(type)?.interfaceMeta?.colour),
              ]}
            >
              {modelName(type, count !== 1)}
            </span>
            <span
              class={[
                numberBadgeClass,
                "rounded-l-none rounded-r-xs border-[0.5px] border-l-0 border-slate-400/70 bg-white px-2 text-slate-800",
              ]}
            >
              {count.toLocaleString()}
            </span>
          </span>
        )}
      </For>
    </span>
  );
}

/** A notice in the page: yellow for what waits for a person, red for what is refused, slate for the rest */
export function Notice(props: ParentProps<{ tone?: "waiting" | "refused" | "plain"; testid?: string }>) {
  return (
    <div
      role={props.tone === "refused" ? "alert" : "status"}
      data-testid={props.testid}
      class={[
        "flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xs border-[0.5px] px-3 py-2 text-sm",
        {
          "border-yellow-600/50": props.tone === "waiting",
          "bg-yellow-100": props.tone === "waiting",
          "text-yellow-950": props.tone === "waiting",
          "border-red-700/50": props.tone === "refused",
          "bg-red-50": props.tone === "refused",
          "text-red-950": props.tone === "refused",
          "border-slate-400/70": props.tone === undefined || props.tone === "plain",
          "bg-slate-100": props.tone === undefined || props.tone === "plain",
          "text-slate-800": props.tone === undefined || props.tone === "plain",
        },
      ]}
    >
      {props.children}
    </div>
  );
}

/** A heading inside a merge page: the words of the frame */
export function Heading(props: ParentProps) {
  return <h2 class="mt-8 mb-3 text-xs font-semibold text-slate-700 uppercase">{props.children}</h2>;
}
