import { createMemo, createSignal, For, Loading, Show } from "solid-js";
import { useApi, useTranslations } from "../context";
import { ReferenceChip } from "./ReferenceChip";
import { fieldGridClass, fieldRowClass } from "./form/styles";

/** A thing a derived fact names: an entity, or a head document */
interface DerivedRef {
  id: string;
  type: string;
  label?: string | null;
}

/** One fact of `_derived` (pangloss-derived), as the view of an entity or a head document has it */
interface DerivedItem {
  id: string;
  type: string;
  /** (of an entity) the other end of the relation */
  other?: DerivedRef | null;
  /** (of an entity) the other fields: entities, or values */
  fields?: Record<string, DerivedRef | string | number | boolean | null>;
  /** (of a document) the fields, as the fact's view has them */
  [field: string]: unknown;
  contextLabels: string[];
  qualifiedOnly: boolean;
  justifications?: number;
  justificationCount?: number;
}

export interface DerivedSectionProps {
  /** `_derived` of the item: for each derived class, a count and a first page */
  derived: Record<string, { count: number; items: DerivedItem[] }>;
  /** The item: a document's facts show all their ends, an entity's leave itself out */
  itemId: string;
  /** Whether the item is a document (the rest of its facts are those it is `evidence` of) or an entity (`entity`) */
  kind?: "entity" | "document";
}

/** A page of `/api/derived/{Class}`: the facts as their views (every end a field) */
interface DerivedPage {
  results: DerivedItem[];
  count: number;
  nextPage: number | null;
}

interface Justification {
  key: string;
  rule: string;
  description: string;
  evidence: (DerivedRef & { published: boolean })[];
  contextLabels: string[];
}

const isRef = (value: unknown): value is DerivedRef =>
  typeof value === "object" && value !== null && "id" in value && "type" in value;

const href = (ref: DerivedRef) => `/${ref.type}/${encodeURIComponent(ref.id)}`;

/** The rules and documents a fact rests on: read when it is asked for */
function Why(props: { type: string; id: string }) {
  const api = useApi();
  const { t } = useTranslations();
  const fact = createMemo(() =>
    api.get<{ justifications: Justification[] }>(
      `/api/derived/${encodeURIComponent(props.type)}/${encodeURIComponent(props.id)}`,
    ),
  );
  return (
    <Loading fallback={<p class="text-xs text-slate-500">{t("loading", "Loading…")}</p>}>
      <ul class="mt-2 flex w-full flex-col gap-2 border-l-2 border-violet-200 pl-3">
        <For each={fact().justifications}>
          {(justification) => (
            <li class="flex flex-col gap-1 text-sm">
              <span class="text-slate-700">
                {justification.description || justification.rule}
              </span>
              <span class="flex flex-wrap items-center gap-2">
                <For each={justification.evidence}>
                  {(evidence) => (
                    <ReferenceChip
                      type={evidence.type}
                      label={evidence.label ?? evidence.id}
                      href={href(evidence)}
                    />
                  )}
                </For>
                <Show when={justification.contextLabels.length > 0}>
                  <span class="text-xs text-amber-700">
                    {justification.contextLabels.join(", ")}
                  </span>
                </Show>
              </span>
            </li>
          )}
        </For>
      </ul>
    </Loading>
  );
}

function Fact(props: { item: DerivedItem; itemId: string }) {
  const { t } = useTranslations();
  const [why, setWhy] = createSignal(false);
  // (what to show of it: for an entity, the other end and the other fields; for a document, every end)
  const refs = createMemo(() => {
    const item = props.item;
    if (item.other !== undefined || item.fields !== undefined) {
      return [
        ...(isRef(item.other) ? [item.other] : []),
        ...Object.values(item.fields ?? {}).filter(isRef),
      ];
    }
    return Object.values(item).filter(isRef).filter((ref) => ref.id !== props.itemId);
  });
  const count = () => props.item.justifications ?? props.item.justificationCount ?? 0;
  return (
    <li class="flex flex-col">
      <span class="flex flex-wrap items-center gap-2">
        <For each={refs()}>
          {(ref) => (
            <ReferenceChip type={ref.type} label={ref.label ?? ref.id} href={href(ref)} />
          )}
        </For>
        <Show when={props.item.qualifiedOnly}>
          <span
            class="rounded-sm bg-amber-50 px-1.5 text-xs text-amber-800"
            title={t("derived_qualified", "Only from statements with a context")}
          >
            {props.item.contextLabels.join(", ")}
          </span>
        </Show>
        <button
          type="button"
          class="text-xs font-semibold text-violet-700 uppercase select-none hover:underline"
          aria-expanded={why() ? "true" : "false"}
          onClick={() => setWhy((open) => !open)}
        >
          {t("derived_why", "Why ({count})", { count: count() })}
        </button>
      </span>
      <Show when={why()}>
        <Why type={props.item.type} id={props.item.id} />
      </Show>
    </li>
  );
}

function ClassSection(props: {
  name: string;
  count: number;
  first: DerivedItem[];
  itemId: string;
  kind: "entity" | "document";
}) {
  const api = useApi();
  const { t, modelName } = useTranslations();
  // (the pages read so far, after the first the item came with; the pages are 25 as the first is)
  const [more, setMore] = createSignal<DerivedItem[]>([]);
  const [nextPage, setNextPage] = createSignal(2);
  const [loading, setLoading] = createSignal(false);
  const items = createMemo(() => [...props.first, ...more()]);
  const left = () => props.count - items().length;
  const load = async () => {
    setLoading(true);
    try {
      const page = await api.get<DerivedPage>(`/api/derived/${encodeURIComponent(props.name)}`, {
        [props.kind]: props.itemId,
        page: nextPage(),
      });
      // (the `_derived` of an entity names the class by a reverse name at times; the items are the class's)
      setMore((shown) => [...shown, ...page.results]);
      setNextPage((page) => page + 1);
    } finally {
      setLoading(false);
    }
  };
  return (
    <div class={fieldRowClass}>
      <dt class="pt-1 text-xs font-semibold text-slate-500 uppercase">
        {modelName(props.name)}
        <span class="ml-1 font-normal normal-case">({props.count})</span>
      </dt>
      <dd class="flex min-w-0 flex-col gap-3">
        <ul class="flex flex-col gap-3">
          <For each={items()}>{(item) => <Fact item={item} itemId={props.itemId} />}</For>
        </ul>
        <Show when={left() > 0}>
          <button
            type="button"
            class="self-start text-xs font-semibold text-violet-700 uppercase select-none hover:underline disabled:text-slate-400"
            disabled={loading()}
            onClick={() => void load()}
          >
            {t("derived_more", "and {count} more", { count: left() })}
          </button>
        </Show>
      </dd>
    </div>
  );
}

/**
 * What the rules derive about an item (`_derived` of its view, from `pangloss-derived`), apart from what its documents
 * say: for each derived class, its facts, each with "why" (the rules and documents it rests on) on demand
 */
export function DerivedSection(props: DerivedSectionProps) {
  const { t } = useTranslations();
  const classes = createMemo(() => Object.entries(props.derived ?? {}));
  return (
    <Show when={classes().length > 0}>
      <section class="mt-10 border-t-[0.5px] border-slate-400/70 pt-4">
        <h2 class="mb-4 text-xs font-semibold text-violet-700 uppercase">
          {t("derived_heading", "Derived")}
        </h2>
        <dl class={fieldGridClass}>
          <For each={classes()}>
            {([name, section]) => (
              <ClassSection
                name={name}
                count={section.count}
                first={section.items}
                itemId={props.itemId}
                kind={props.kind ?? "entity"}
              />
            )}
          </For>
        </dl>
      </section>
    </Show>
  );
}
