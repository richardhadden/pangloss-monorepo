import { createMemo, createSignal, For, Loading, Show } from "solid-js";
import { buttonClass, fieldGridClass, fieldRowClass, SectionBar, useApi, useComponent, useTranslations } from "@pangloss/interface-core";
import type { ItemSectionProps } from "@pangloss/interface-core";

/** A thing a derived edge names: an entity */
interface DerivedRef {
  id: string;
  type: string;
  label?: string | null;
}

type Value = DerivedRef | string | number | boolean | null;

/** How a justification holds, by the walk over what it passed through (`pangloss_derived.status.STATUSES`) */
type JustificationStatus =
  | "asserted"
  | "reported"
  | "prescribed"
  | "denied"
  | "reported_not"
  | "prescribed_not"
  | "nothing";

/** What a fact's justifications say, summed up (`pangloss_derived.status.summed`) */
type FactStatus = "asserted" | "contested" | "reported" | "prescribed" | "denied" | "nothing";

/**
 * Whose a fact or a justification is, by the grounds of what it rests on (`pangloss_derived.status.STANDINGS`): a
 * claim (what a source says), or the record (what claims are held against: of a fact, where every justification is)
 */
type Standing = "claim" | "record";

/**
 * One edge of `_derived` (pangloss-derived): a row of the first page, as the view of an item has it (the other end,
 * and the qualifiers), or of a later page, which is the edge's own view (its two ends by the names of their fields,
 * `ends` naming them, and `qualifiers`)
 */
interface DerivedItem {
  id: string;
  type: string;
  /** (of the first page) the other end of the edge */
  other?: DerivedRef | null;
  /** (of the first page) the field the other end is in */
  otherField?: string | null;
  /** (of the first page) the qualifiers: entities, or values */
  fields?: Record<string, Value>;
  /**
   * (of the first page, read from a qualifier, which is at neither end) both ends, by their fields; (of a later page)
   * the names of the two fields that are the ends
   */
  ends?: Record<string, DerivedRef> | string[];
  /** (of a later page) the qualifiers */
  qualifiers?: Record<string, Value>;
  /** (of a later page) each end, by the name of its field */
  [field: string]: unknown;
  contextLabels: string[];
  qualifiedOnly: boolean;
  status: FactStatus;
  /** The statuses of its justifications, each once */
  statuses: JustificationStatus[];
  standing: Standing;
  justifications?: number;
  justificationCount?: number;
}

/** The `SymmetricLabel` of a symmetric derived class: the one name of its two ends */
interface SymmetricLabel {
  name: string;
  fields: [string, string];
}

/**
 * One section of `_derived`: the edges of a class that the item is in, in one way (`role`). Its key is the class's name
 * (the item is at an end: of an asymmetric class with a reverse name, the subject), the reverse name (the item is the
 * object), or `Class:field` (the item qualifies the edges: a group, of the edges between its members)
 */
interface DerivedClass {
  type?: string;
  role?: "subject" | "object" | "ends" | "qualifier";
  /** The fields of the class the item is at */
  as?: string[];
  ends?: string[];
  symmetric?: boolean;
  symmetricLabel?: SymmetricLabel | null;
  reverseName?: string | null;
  count: number;
  items: DerivedItem[];
}

/** A page of `/api/derived/{Class}`: the edges as their views */
interface DerivedPage {
  results: DerivedItem[];
  count: number;
  nextPage: number | null;
}

interface Justification {
  key: string;
  rule: string;
  description: string;
  /** The values of the class's `PerJustification()` fields (a probability found on the way) */
  values?: Record<string, string | number | boolean | null>;
  evidence: (DerivedRef & { published: boolean })[];
  contextLabels: string[];
  status: JustificationStatus;
  standing: Standing;
}

const isRef = (value: unknown): value is DerivedRef =>
  typeof value === "object" && value !== null && "id" in value && "type" in value;

/** A derived class's name: its translation, or its own name in words (`SameGroup`, "Same group") */
const className = (modelName: (model: string) => string, name: string) => {
  const shown = modelName(name);
  return shown !== name ? shown : name.replace(/(?<=[a-z0-9])(?=[A-Z])/g, " ").replace(/ [A-Z](?=[a-z])/g, (c) => c.toLowerCase());
};

const href = (ref: DerivedRef) => `/${ref.type}/${encodeURIComponent(ref.id)}`;

type FieldValue = Value | undefined;

/**
 * The fields of an edge to show, by name: the other end (both ends, read from a qualifier), then the qualifiers; never
 * the item itself. A row of the first page says which is which; a later page is the edge's whole view, and the item
 * is left out of it by its id, at the fields the section says it is at
 */
function shownFields(item: DerivedItem, itemId: string, own: string[]): [string, FieldValue][] {
  if (!Array.isArray(item.ends)) {
    return [
      ...(item.otherField && item.other ? [[item.otherField, item.other] as [string, FieldValue]] : []),
      ...(Object.entries(item.ends ?? {}) as [string, FieldValue][]),
      ...Object.entries(item.fields ?? {}),
    ];
  }
  const fields = [
    ...item.ends.map((name) => [name, item[name]] as [string, FieldValue]),
    ...(Object.entries(item.qualifiers ?? {}) as [string, FieldValue][]),
  ];
  return fields.filter(([name, value]) => !(own.includes(name) && isRef(value) && value.id === itemId));
}

/**
 * How a fact or a justification holds, in words: nothing for what is asserted, a small mark for the rest (what
 * speaks against it in rose)
 */
function StatusMark(props: { status: FactStatus | JustificationStatus }) {
  const { t } = useTranslations();
  const words = (): string => {
    switch (props.status) {
      case "contested":
        return t("derived_status_contested", "Contested");
      case "reported":
        return t("derived_status_reported", "Reported");
      case "prescribed":
        return t("derived_status_prescribed", "Prescribed");
      case "denied":
        return t("derived_status_denied", "Denied");
      case "reported_not":
        return t("derived_status_reported_not", "Reported not");
      case "prescribed_not":
        return t("derived_status_prescribed_not", "Forbidden");
      case "nothing":
        return t("derived_status_nothing", "Not said either way");
      default:
        return "";
    }
  };
  const against = () => ["contested", "denied", "reported_not", "prescribed_not"].includes(props.status);
  return (
    <Show when={props.status !== "asserted"}>
      <span
        data-status={props.status}
        class={[
          "rounded-xs px-1.5 text-xs",
          against() ? "bg-rose-50 text-rose-800" : "bg-amber-50 text-amber-800",
        ]}
      >
        {words()}
      </span>
    </Show>
  );
}

/** A fact of the record, beside its status: told apart from one a source says, which has no mark */
function StandingMark(props: { standing: Standing }) {
  const { t } = useTranslations();
  return (
    <Show when={props.standing === "record"}>
      <span data-standing="record" class="rounded-xs bg-slate-100 px-1.5 text-xs text-slate-700">
        {t("derived_standing_record", "Of the record")}
      </span>
    </Show>
  );
}

/** The rules and documents a fact rests on: read when it is asked for */
function Why(props: { type: string; id: string }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const api = useApi();
  const { t, fieldName } = useTranslations();
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
                <For each={Object.entries(justification.values ?? {})}>
                  {([name, value]) => (
                    <span class="flex items-center gap-1 text-xs text-slate-600">
                      <span class="font-semibold text-slate-500 uppercase select-none">
                        {fieldName(props.type, name)}
                      </span>
                      {String(value)}
                    </span>
                  )}
                </For>
                <StatusMark status={justification.status} />
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

function Fact(props: { item: DerivedItem; itemId: string; own: string[]; symmetricLabel?: SymmetricLabel | null }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, fieldName } = useTranslations();
  const [why, setWhy] = createSignal(false);
  const fields = createMemo(() =>
    shownFields(props.item, props.itemId, props.own).filter(([, value]) => value !== null && value !== undefined),
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
        <StatusMark status={props.item.status} />
        <StandingMark standing={props.item.standing} />
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
  /** The key of `_derived`: the class's name, a reverse name, or `Class:field` */
  name: string;
  type: string;
  section: DerivedClass;
  itemId: string;
}) {
  const api = useApi();
  const { t, modelName, incomingName, fieldName } = useTranslations();
  const own = () => props.section.as ?? [];
  // (the class's name; read from its object, the reverse name; from a qualifier, the class and that field)
  const title = () => {
    const section = props.section;
    if (section.role === "object" && section.reverseName) return incomingName(props.type, section.reverseName);
    if (section.role === "qualifier") {
      return `${className(modelName, props.type)} · ${own().map((field) => fieldName(props.type, field)).join(", ")}`;
    }
    return className(modelName, props.type);
  };
  // (the pages read so far, after the first the item came with; the pages are 25 as the first is)
  const [more, setMore] = createSignal<DerivedItem[]>([]);
  const [nextPage, setNextPage] = createSignal(2);
  const [loading, setLoading] = createSignal(false);
  const items = createMemo(() => [...props.section.items, ...more()]);
  const left = () => props.section.count - items().length;
  const load = async () => {
    setLoading(true);
    try {
      const page = await api.get<DerivedPage>(`/derived/${encodeURIComponent(props.type)}`, {
        entity: props.itemId,
        // (only the edges the item is in in this section's way: as the giver, not as the receiver)
        ...(own().length > 0 ? { at: own().join(",") } : {}),
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
        {title()}
        <span class="ml-1 font-normal normal-case">({props.section.count})</span>
      </dt>
      <dd class="flex min-w-0 flex-col gap-3">
        <ul class="flex flex-col gap-3">
          <For each={items()}>
            {(item) => (
              <Fact item={item} itemId={props.itemId} own={own()} symmetricLabel={props.section.symmetricLabel} />
            )}
          </For>
        </ul>
        <Show when={left() > 0}>
          <button
            type="button"
            class={[buttonClass("quiet"), "self-start"]}
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

/** What the rules derive about an item: for each way it is in the edges of a derived class, a count and a first page */
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
              <ClassSection name={name} type={section.type ?? name} section={section} itemId={props.itemId} />
            )}
          </For>
        </dl>
      </section>
    </Show>
  );
}
