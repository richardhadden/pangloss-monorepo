import { createMemo, createSignal, For, Loading, Show } from "solid-js";
import {
  fieldGridClass,
  fieldRowClass,
  SectionBar,
  smallButtonClass,
  useApi,
  useComponent,
  useTranslations,
} from "@pangloss/interface-core";
import type { ItemSectionProps } from "@pangloss/interface-core";

/** A thing a derived fact names: an entity, or a head document */
interface DerivedRef {
  id: string;
  type: string;
  label?: string | null;
}

/** One fact of `_derived` (pangloss-derived), as the view of an item has it, or of a later page */
interface DerivedItem {
  id: string;
  type: string;
  /** (of the first page) the other end of the relation */
  other?: DerivedRef | null;
  /** (of the first page) the field the other end is in */
  otherField?: string | null;
  /** (of the first page) the other fields: entities, or values */
  fields?: Record<string, DerivedRef | string | number | boolean | null>;
  /** (of a later page) the fields, as the fact's view has them */
  [field: string]: unknown;
  contextLabels: string[];
  qualifiedOnly: boolean;
  justifications?: number;
  justificationCount?: number;
}

/** The `SymmetricLabel` of a derived class: the name its two symmetric fields share */
interface SymmetricLabel {
  name: string;
  fields: [string, string];
}

/** One class of `_derived`: by its name, or its reverse name (the key) */
interface DerivedClass {
  type?: string;
  symmetricLabel?: SymmetricLabel | null;
  count: number;
  items: DerivedItem[];
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

/** A derived class's name: its translation, or its own name in words (`SameGroup`, "Same group") */
const className = (modelName: (model: string) => string, name: string) => {
  const shown = modelName(name);
  return shown !== name ? shown : name.replace(/(?<=[a-z0-9])(?=[A-Z])/g, " ").replace(/ [A-Z](?=[a-z])/g, (c) => c.toLowerCase());
};

const href = (ref: DerivedRef) => `/${ref.type}/${encodeURIComponent(ref.id)}`;

/** What a fact's view has besides its fields */
const notFields = new Set([
  "id",
  "type",
  "as",
  "contextLabels",
  "qualifiedOnly",
  "types",
  "justifications",
  "justificationCount",
  "derived",
]);

type FieldValue = DerivedRef | string | number | boolean | null | undefined;

/**
 * The fields of a fact to show, by name, in the order of its class: for the first page of an entity, the other end
 * and the other fields; for a fact's whole view (a later page), every field but those that are the
 * item itself
 */
function shownFields(item: DerivedItem, itemId: string): [string, FieldValue][] {
  if (item.other !== undefined || item.fields !== undefined) {
    return [
      ...(item.otherField && item.other ? [[item.otherField, item.other] as [string, FieldValue]] : []),
      ...Object.entries(item.fields ?? {}),
    ];
  }
  return Object.entries(item)
    .filter(([name]) => !notFields.has(name))
    .filter(([, value]) => !(isRef(value) && value.id === itemId)) as [string, FieldValue][];
}

/** The rules and documents a fact rests on: read when it is asked for */
function Why(props: { type: string; id: string }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const api = useApi();
  const { t } = useTranslations();
  const fact = createMemo(() =>
    api.get<{ justifications: Justification[] }>(
      `/derived/${encodeURIComponent(props.type)}/${encodeURIComponent(props.id)}`,
    ),
  );
  return (
    <Loading fallback={<p class="text-xs text-slate-500">{t("loading", "Loading…")}</p>}>
      <ul class="mt-2 flex w-full flex-col gap-2 border-l-2 border-slate-300 pl-3">
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

function Fact(props: { item: DerivedItem; itemId: string; symmetricLabel?: SymmetricLabel | null }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, fieldName } = useTranslations();
  const [why, setWhy] = createSignal(false);
  const fields = createMemo(() =>
    shownFields(props.item, props.itemId).filter(([, value]) => value !== null && value !== undefined),
  );
  const count = () => props.item.justifications ?? props.item.justificationCount ?? 0;
  return (
    <li class="flex flex-col">
      <span class="flex flex-wrap items-center gap-x-5 gap-y-2">
        <For each={fields()}>
          {([name, value]) => (
            <span class="flex items-center gap-2">
              <span class="text-xs font-semibold text-slate-500 uppercase select-none">
                {fieldName(
                  props.item.type,
                  props.symmetricLabel?.fields.includes(name) ? props.symmetricLabel.name : name,
                )}
              </span>
              <Show when={isRef(value) && value} fallback={<span class="text-sm">{String(value)}</span>}>
                {(ref) => <ReferenceChip type={ref().type} label={ref().label ?? ref().id} href={href(ref())} />}
              </Show>
            </span>
          )}
        </For>
        <Show when={props.item.qualifiedOnly}>
          <span
            class="rounded-xs bg-amber-50 px-1.5 text-xs text-amber-800"
            title={t("derived_qualified", "Only from statements with a context")}
          >
            {props.item.contextLabels.join(", ")}
          </span>
        </Show>
        <button
          type="button"
          class="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-xs px-1.5 py-1 text-xs font-semibold text-slate-500 uppercase select-none hover:bg-slate-200/70 hover:text-slate-700"
          aria-expanded={why() ? "true" : "false"}
          onClick={() => setWhy((open) => !open)}
        >
          <span aria-hidden="true" class={["inline-block transition-transform", why() && "rotate-90"]}>
            ▸
          </span>
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
  /** The key of `_derived`: the class's name, or a reverse name */
  name: string;
  type: string;
  symmetricLabel?: SymmetricLabel | null;
  count: number;
  first: DerivedItem[];
  itemId: string;
}) {
  const api = useApi();
  const { t, modelName, incomingName } = useTranslations();
  // (the pages read so far, after the first the item came with; the pages are 25 as the first is)
  const [more, setMore] = createSignal<DerivedItem[]>([]);
  const [nextPage, setNextPage] = createSignal(2);
  const [loading, setLoading] = createSignal(false);
  const items = createMemo(() => [...props.first, ...more()]);
  const left = () => props.count - items().length;
  const load = async () => {
    setLoading(true);
    try {
      const page = await api.get<DerivedPage>(`/derived/${encodeURIComponent(props.type)}`, {
        entity: props.itemId,
        page: nextPage(),
      });
      setMore((shown) => [...shown, ...page.results]);
      setNextPage((page) => page + 1);
    } finally {
      setLoading(false);
    }
  };
  return (
    <div class={fieldRowClass}>
      <dt class="pt-1 text-xs font-semibold text-slate-500 uppercase">
        {props.name === props.type ? className(modelName, props.type) : incomingName(props.type, props.name)}
        <span class="ml-1 font-normal normal-case">({props.count})</span>
      </dt>
      <dd class="flex min-w-0 flex-col gap-3">
        <ul class="flex flex-col gap-3">
          <For each={items()}>
            {(item) => <Fact item={item} itemId={props.itemId} symmetricLabel={props.symmetricLabel} />}
          </For>
        </ul>
        <Show when={left() > 0}>
          <button
            type="button"
            class={[smallButtonClass, "self-start text-slate-600 disabled:text-slate-400"]}
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

/** What the rules derive about an item: for each derived class, by its name or a reverse name, a count and a first page */
type DerivedOfItem = Record<string, DerivedClass>;

/**
 * What the rules derive about an item, apart from what its documents say: for each derived class, its facts, each
 * with "why" (the rules and documents it rests on) on demand. A section after the item's contents
 * (`itemSections.Derived`); the item (an entity, or a head document a fact points at) is left out of its facts.
 *
 * The item's view carries it as `_derived`, and that is shown; an item read without what the apps add to its view
 * (the item's page reads the item alone, so that it is on show at once) has it read here, from
 * `/api/derived/about/{Type}/{id}`, read directly: the boundary is the one `ItemSections` gives every section (nothing
 * shows until it has come, the page is not kept waiting, and it never shows before what refers to the item, which the
 * item page's `Reveal` puts first). A boundary of the section's own, nested in that one, hydrated wrongly.
 */
export default function DerivedSection(props: ItemSectionProps) {
  return (
    <Show
      when={props.item._derived === undefined}
      fallback={<Classes derived={props.item._derived as DerivedOfItem} itemId={props.id} />}
    >
      <FetchedClasses {...props} />
    </Show>
  );
}

// (read with the item, and again with a new one: after logging in or out, what a reader may see is not the same)
function FetchedClasses(props: ItemSectionProps) {
  const api = useApi();
  const about = createMemo(() => {
    const item = props.item;
    return api.get<DerivedOfItem>(
      `/derived/about/${encodeURIComponent(String(item.type))}/${encodeURIComponent(String(item.id))}`,
    );
  });
  return <Classes derived={about()} itemId={props.id} />;
}

function Classes(props: { derived: DerivedOfItem | null | undefined; itemId: string }) {
  const { t } = useTranslations();
  const classes = createMemo(() => Object.entries(props.derived ?? {}));
  return (
    <Show when={classes().length > 0}>
      <section data-testid="derived-section">
        <SectionBar>{t("derived_heading", "Derived")}</SectionBar>
        <dl class={fieldGridClass}>
          <For each={classes()}>
            {([name, section]) => (
              <ClassSection
                name={name}
                type={section.type ?? name}
                symmetricLabel={section.symmetricLabel}
                count={section.count}
                first={section.items}
                itemId={props.itemId}
              />
            )}
          </For>
        </dl>
      </section>
    </Show>
  );
}
