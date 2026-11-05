import { createMemo, createSignal, For, Match, onSettled, Show, Switch } from "solid-js";
import type { ParentProps } from "solid-js";
import {
  useComponent,
  useModels,
  useModules,
  useTranslations,
} from "../context";
import { kindRule, kindTint, spaceTint } from "../primitives";
import { contextTrail } from "../api";
import type { ContextLabel } from "../api";
import {
  arrangeByDate,
  collapsedView,
  edgeModelFor,
  getModel,
  headlessIn,
  inYears,
  isDateable,
  yearSpan,
} from "../schema";
import type { IncomingEntry } from "../schema";
import type {
  FieldDefinition,
  ItemContentsProps,
  ModelDefinition,
} from "../types";
import { Customised } from "./Customised";
import { SpaceBands } from "./SpaceBands";
import {
  fieldGridClass,
  fieldRowClass,
  fieldRuleClass,
  headBarClass,
  headButtonClass,
  headBarLinkClass,
  headLabelClass,
  headRestClass,
  nestedClass,
  plainTint,
  spaceTypeClass,
  typeChipClass,
} from "./form/styles";

type Data = Record<string, unknown>;

const isObject = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);

// (nothing to show: the row is left out)
const isEmpty = (value: unknown) =>
  value === null ||
  value === undefined ||
  value === "" ||
  (Array.isArray(value) && value.length === 0);

/**
 * A key on the left, its contents on the right: chips side by side (as many as fit on a line),
 * anything bigger, and each text, on a line of its own, with a faint rule above it as in a form. A
 * row of what refers to the item from elsewhere (`incoming`) has more room above it and between its
 * items, and centres the chips of a line on each other (some are taller, wrapped in semantic spaces).
 */
function Row(props: ParentProps<{ name: string; incoming?: boolean }>) {
  return (
    <div
      class={[
        fieldRowClass,
        // (more room above what refers to the item from elsewhere)
        { "pt-6": props.incoming, "first:pt-0": props.incoming },
      ]}
    >
      <dt class="pt-1 text-xs font-semibold text-slate-500 uppercase">
        {props.name}
      </dt>
      <dd
        class={[
          "flex min-w-0 flex-wrap gap-x-2",
          {
            "items-start": !props.incoming,
            // (a row with a block in it has blocks as far apart as rows of what refers to the item: `data-block`)
            "gap-y-4 has-[>[data-block]]:gap-y-6": !props.incoming,
            "items-center": props.incoming,
            "gap-y-6": props.incoming,
          },
        ]}
      >
        {props.children}
      </dd>
    </div>
  );
}

/**
 * The head of something nested: a bar with its type as a chip at the left end, and its label. If it
 * is an item of its own (`href`), the whole bar is a link to it, and darkens as a chip does.
 */
function Head(props: {
  type: string;
  tint: string;
  /** The colour of the rule that hangs from it, which the frame of its type has too */
  rule: string;
  label?: string;
  href?: string;
  /** Gives the bar a button at its right end that folds it (what is shown whole that can be collapsed) */
  onFold?: () => void;
}) {
  const { t, modelName } = useTranslations();
  const contents = () => (
    <>
      <span class={[typeChipClass, props.tint || plainTint, props.rule]}>
        {modelName(props.type)}
      </span>
      <span class={headRestClass}>
        <Show when={props.label}>
          <span class={headLabelClass}>{props.label}</span>
        </Show>
        <Show when={props.onFold}>
          <button
            type="button"
            class={[headButtonClass, "ml-auto text-slate-500 hover:bg-slate-400/30"]}
            aria-label={t("collapse_fold", "Fold {name}", { name: modelName(props.type) })}
            title={t("collapse_fold", "Fold {name}", { name: modelName(props.type) })}
            onClick={() => props.onFold!()}
          >
            ▾
          </button>
        </Show>
      </span>
    </>
  );
  return (
    <Show
      when={props.href}
      fallback={<div class={headBarClass}>{contents()}</div>}
    >
      <a href={props.href} class={[headBarClass, headBarLinkClass]}>
        {contents()}
      </a>
    </Show>
  );
}

/**
 * The rows of an object: a key and its contents for each field of its model, in the order of
 * the model, the keys in a column on the left and the contents on the right. Fields with
 * nothing in them are left out, and those only in the database (worked out, not said). What refers to the object from elsewhere (`incoming`) follows,
 * as chips: by the field it is in, or (on the item's page, when some of it is `Dateable`) by date.
 */
function Fields(props: {
  value: Data;
  model: ModelDefinition | undefined;
  depth: number;
  /** (a field that is shown some other way) */
  exclude?: string;
}) {
  const { fieldName, incomingName } = useTranslations();
  const definitions = useModels();
  const entries = createMemo<IncomingEntry[]>(() =>
    (props.model?.incoming ?? []).flatMap((incoming) => {
      const value = props.value[incoming.key];
      return (Array.isArray(value) ? value : value ? [value] : [])
        .filter(isObject)
        .map((item) => ({
          key: incoming.key,
          name: incomingName(props.model!.name, incoming.name),
          item,
        }));
    }),
  );
  // (only on the item's own page, and only if something that refers to it can have a date)
  const canDate = () =>
    props.depth === 0 && entries().some((entry) => isDateable(definitions, entry.item.type));
  const order = useIncomingOrder();
  return (
    <dl class={fieldGridClass}>
      <For each={props.model?.fields ?? []}>
        {(field) => (
          <Show
            when={
              field.key !== props.exclude &&
              !field.dbField &&
              !isEmpty(props.value[field.key])
            }
          >
            <Row name={fieldName(props.model!.name, field.name)}>
              <Value
                value={props.value[field.key]}
                field={field}
                depth={props.depth}
              />
            </Row>
          </Show>
        )}
      </For>
      <Show when={canDate()}>
        <IncomingOrderSwitch order={order.order()} onChange={order.setOrder} />
      </Show>
      <Show
        when={canDate() && order.order() === "date"}
        fallback={
          <For each={props.model?.incoming ?? []}>
            {(incoming) => (
              <Show when={!isEmpty(props.value[incoming.key])}>
                <Row name={incomingName(props.model!.name, incoming.name)} incoming>
                  <Value
                    value={props.value[incoming.key]}
                    depth={props.depth}
                    asChip
                  />
                </Row>
              </Show>
            )}
          </For>
        }
      >
        <IncomingByDate entries={entries()} depth={props.depth} />
      </Show>
    </dl>
  );
}

type IncomingOrder = "field" | "date";
const INCOMING_ORDER_KEY = "pangloss.incomingOrder";

/** How what refers to an item is shown, remembered from one page to the next (read once settled, so that the
 * server-side render and the first client render agree) */
function useIncomingOrder() {
  const [order, setOrderSignal] = createSignal<IncomingOrder>("field");
  onSettled(() => {
    try {
      if (localStorage.getItem(INCOMING_ORDER_KEY) === "date") setOrderSignal("date");
    } catch {
      // (storage unavailable: the choice is just not remembered)
    }
  });
  const setOrder = (next: IncomingOrder) => {
    setOrderSignal(next);
    try {
      localStorage.setItem(INCOMING_ORDER_KEY, next);
    } catch {
      // (as above)
    }
  };
  return { order, setOrder };
}

/** Two buttons, one pressed: what refers to the item by the field it is in, or by date */
function IncomingOrderSwitch(props: { order: IncomingOrder; onChange: (order: IncomingOrder) => void }) {
  const { t } = useTranslations();
  const button = (order: IncomingOrder, text: string) => (
    <button
      type="button"
      class={[
        "px-2.5 py-1 text-xs first:rounded-l-sm last:rounded-r-sm",
        props.order === order
          ? "bg-slate-600 text-white"
          : "bg-white text-slate-600 hover:bg-slate-100",
      ]}
      aria-pressed={props.order === order ? "true" : "false"}
      onClick={() => props.onChange(order)}
    >
      {text}
    </button>
  );
  return (
    <div class={["col-span-2 flex items-center gap-3 border-t pt-6", fieldRuleClass]}>
      <span class="text-xs font-semibold text-slate-500 uppercase">
        {t("incoming_order", "What refers to it")}
      </span>
      <div
        role="group"
        aria-label={t("incoming_order", "What refers to it")}
        class="inline-flex divide-x divide-slate-300 rounded-sm border border-slate-300"
      >
        {button("field", t("incoming_by_field", "By field"))}
        {button("date", t("incoming_by_date", "By date"))}
      </div>
    </div>
  );
}

/**
 * What refers to the item, by date: each dated one on a row of its own, in order, with its date and
 * the field it is in on the left (where a field's name is) and its chip on the right; a slider of
 * years beside them, which narrows the rows to a span of years. Then those whose date is not known,
 * and last those of a kind that has no date, by field as they are otherwise.
 */
function IncomingByDate(props: { entries: IncomingEntry[]; depth: number }) {
  const { t } = useTranslations();
  const definitions = useModels();
  const arranged = createMemo(() => arrangeByDate(props.entries, definitions));
  const span = createMemo(() => yearSpan(arranged().dated));
  // (the years chosen; none chosen is the whole span, which follows the items)
  const [from, setFrom] = createSignal<number>();
  const [to, setTo] = createSignal<number>();
  const first = () => Math.max(from() ?? span()?.[0] ?? 0, span()?.[0] ?? 0);
  const last = () => Math.min(to() ?? span()?.[1] ?? 0, span()?.[1] ?? 0);
  const shown = createMemo(() =>
    arranged().dated.filter((entry) => inYears(entry, first(), last())),
  );
  const undatedByField = createMemo(() => {
    const groups = new Map<string, IncomingEntry[]>();
    for (const entry of arranged().undated)
      groups.set(entry.name, [...(groups.get(entry.name) ?? []), entry]);
    return [...groups.entries()];
  });
  return (
    <>
      <Show when={arranged().dated.length > 0}>
        <div class="col-span-2 flex items-start gap-6 pt-1">
          <div class={["grid min-w-0 flex-1 grid-cols-[10rem_minmax(0,1fr)] gap-x-6"]} data-testid="incoming-by-date">
            <For each={shown()}>
              {(entry) => <DatedRow entry={entry} depth={props.depth} />}
            </For>
            <Show when={shown().length === 0}>
              <p class="col-span-2 py-3 text-sm text-slate-500">
                {t("incoming_none_in_years", "Nothing in these years")}
              </p>
            </Show>
          </div>
          <Show when={span() && span()![0] < span()![1]}>
            <aside
              class="sticky top-28 flex w-40 shrink-0 flex-col gap-3 rounded-sm border border-slate-300 p-3"
              aria-label={t("incoming_years", "Years")}
            >
              <YearSlider
                label={t("incoming_from_year", "From")}
                min={span()![0]}
                max={span()![1]}
                value={first()}
                onInput={(year) => {
                  setFrom(year);
                  if (year > last()) setTo(year);
                }}
              />
              <YearSlider
                label={t("incoming_to_year", "To")}
                min={span()![0]}
                max={span()![1]}
                value={last()}
                onInput={(year) => {
                  setTo(year);
                  if (year < first()) setFrom(year);
                }}
              />
              <p class="text-xs text-slate-500" data-testid="incoming-shown">
                {t("incoming_shown", "{shown} of {total}", {
                  shown: shown().length,
                  total: arranged().dated.length,
                })}
              </p>
            </aside>
          </Show>
        </div>
      </Show>
      <Show when={arranged().unknown.length > 0}>
        <Row name={t("incoming_date_unknown", "Date unknown")} incoming>
          <div class="grid w-full grid-cols-[10rem_minmax(0,1fr)] gap-x-6 gap-y-3" data-testid="incoming-date-unknown">
            <For each={arranged().unknown}>
              {(entry) => (
                <>
                  <span class="pt-1 text-xs font-semibold text-slate-500 uppercase">{entry.name}</span>
                  <div class="flex min-w-0 flex-wrap items-center gap-2">
                    <Value value={entry.item} depth={props.depth} asChip />
                  </div>
                </>
              )}
            </For>
          </div>
        </Row>
      </Show>
      <Show when={undatedByField().length > 0}>
        <div class={["col-span-2 border-t pt-6 text-xs font-semibold text-slate-500 uppercase", fieldRuleClass]}>
          {t("incoming_not_dated", "Not dated")}
        </div>
        <For each={undatedByField()}>
          {([name, group]) => (
            <Row name={name} incoming>
              <Value value={group.map((entry) => entry.item)} depth={props.depth} asChip />
            </Row>
          )}
        </For>
      </Show>
    </>
  );
}

/** A dated item: its date and the field it is in on the left, its chip on the right */
function DatedRow(props: { entry: IncomingEntry; depth: number }) {
  return (
    <div
      class={["col-span-2 grid grid-cols-subgrid items-center border-t py-3 first:border-t-0", fieldRuleClass]}
      data-testid="dated-item"
    >
      <div class="flex flex-col">
        <span class="text-sm text-slate-800 tabular-nums">{String(props.entry.item.dateText)}</span>
        <span class="text-xs font-semibold text-slate-500 uppercase">{props.entry.name}</span>
      </div>
      <div class="flex min-w-0 flex-wrap items-center gap-2">
        <Value value={props.entry.item} depth={props.depth} asChip />
      </div>
    </div>
  );
}

function YearSlider(props: {
  label: string;
  min: number;
  max: number;
  value: number;
  onInput: (year: number) => void;
}) {
  return (
    <label class="flex flex-col gap-1">
      <span class="flex items-baseline justify-between text-xs font-semibold text-slate-500 uppercase">
        {props.label}
        <span class="text-sm font-normal text-slate-800 tabular-nums normal-case">{props.value}</span>
      </span>
      <input
        type="range"
        class="w-full accent-slate-600"
        min={props.min}
        max={props.max}
        step={1}
        value={props.value}
        aria-label={props.label}
        onInput={(event) => props.onInput(Number(event.currentTarget.value))}
      />
    </label>
  );
}

/** A text, a number, a yes or no, a list, or an object */
function Value(props: {
  value: unknown;
  field?: FieldDefinition;
  depth: number;
  asChip?: boolean;
  /** It is shown in the place of something folded into it: if it folds too, it has no marker of its own */
  inFold?: boolean;
}) {
  const { t } = useTranslations();
  return (
    <Switch
      fallback={
        <span class="w-full text-sm break-words whitespace-pre-wrap">
          {String(props.value)}
        </span>
      }
    >
      <Match when={Array.isArray(props.value)}>
        <For each={props.value as unknown[]}>
          {(item) => (
            <Value
              value={item}
              field={props.field}
              depth={props.depth}
              asChip={props.asChip}
              inFold={props.inFold}
            />
          )}
        </For>
      </Match>
      <Match when={isObject(props.value)}>
        <ObjectValue
          value={props.value as Data}
          field={props.field}
          depth={props.depth}
          asChip={props.asChip}
          inFold={props.inFold}
        />
      </Match>
      <Match when={typeof props.value === "boolean"}>
        <span class="w-full text-sm">
          {props.value ? t("yes", "Yes") : t("no", "No")}
        </span>
      </Match>
    </Switch>
  );
}

/**
 * An object in a field. An Entity is a chip. A semantic space is a band, with what is in it
 * inside. An embedded object is only its rows, indented under a plain rule (it is in one place
 * only). An annotated value is its value, as if it were the field's own, with what is said of it
 * under it. Anything else (a Document inside, a reified relation, a conjunction) has a head (its
 * type as a chip, and its label) and its own rows under it, indented, with a rule in the colour of
 * its type down the left: the look of the form.
 */
function ObjectValue(props: {
  value: Data;
  field?: FieldDefinition;
  depth: number;
  asChip?: boolean;
  inFold?: boolean;
}) {
  const ReferenceChip = useComponent("ReferenceChip");
  const definitions = useModels();
  const modules = useModules();
  const { t, modelName, fieldName } = useTranslations();
  const type = () =>
    typeof props.value.type === "string" ? props.value.type : undefined;
  // (an annotated value has no type of its own in the JSON: the field says which it is)
  const model = () =>
    getModel(definitions, type() ?? "") ??
    (props.field?.kind === "annotatedValue"
      ? getModel(definitions, props.field.model)
      : undefined);
  const label = () =>
    typeof props.value.label === "string" ? props.value.label : undefined;
  // (what is referred to can be inside semantic spaces: the API says so in its `meta`)
  const contextLabels = () =>
    isObject(props.value.meta)
      ? (props.value.meta.contextLabels as ContextLabel[] | undefined)
      : undefined;
  // (what refers to the item from elsewhere through a reified relation comes with the field that holds it)
  // (not those only in the database, worked out and not said: a dateable document's copy of its date is in its reference)
  const hasFields = () =>
    (model()?.fields ?? []).some((field) => !field.dbField && !isEmpty(props.value[field.key]));
  const isChip = () =>
    type() !== undefined &&
    ((props.asChip && !hasFields()) || model()?.kind === "Entity");
  const isReified = () =>
    model()?.kind === "ReifiedRelation" ||
    model()?.kind === "ReifiedRelationDocument";
  const isSpace = () => model()?.kind === "SemanticSpace";
  // (a reified relation that is all its field can hold, and it holds one: no head, `InterfaceMeta(headless=True)`)
  const headless = () =>
    props.field?.kind === "relation" && headlessIn(definitions, props.field, type() ?? "");
  const tint = () => kindTint(model()?.kind, model()?.interfaceMeta?.colour);
  const rule = () => kindRule(model()?.kind, model()?.interfaceMeta?.colour);
  const isEmbedded = () => model()?.kind === "Embedded";
  const isAnnotated = () =>
    type() === undefined && props.field?.kind === "annotatedValue";
  // (a reified relation or a conjunction that holds one thing can be shown folded into it: view only)
  const collapsed = () =>
    isChip() || props.asChip
      ? undefined
      : collapsedView(props.value, definitions, modules.collapseRule);
  const [whole, setWhole] = createSignal(false);
  const folded = () => collapsed() !== undefined && !whole();
  // (a part of the item's own document is marked with its id, as in the form, for what points at it: a review comment;
  // not something of another document that refers to it)
  const partId = () =>
    !props.asChip && typeof props.value.id === "string" ? props.value.id : undefined;
  const onFold = () => (collapsed() ? () => setWhole(false) : undefined);
  const plain = (value: unknown): string =>
    Array.isArray(value)
      ? value.map(plain).join(", ")
      : typeof value === "boolean"
        ? value
          ? t("yes", "Yes")
          : t("no", "No")
        : String(value);
  return (
    // (a card that the model names for itself shows an embedded item or a block; a chip is the reference's card)
    <Customised
      slot="viewCard"
      type={type() ?? ""}
      skip={isChip() || type() === undefined}
      props={{
        type: type() ?? "",
        label: label() ?? "",
        item: props.value,
        context: "embedded",
      }}
      fallback={
        <Switch
          fallback={
            // (a block takes a line of its own, as far from what is above it as from what is below: the row's gap)
            <div class="w-full min-w-0 scroll-mt-28" data-item-id={partId()} data-block>
              <SpaceBands
                spaces={
                  props.asChip
                    ? contextTrail(
                        contextLabels(),
                        String(props.value.id ?? ""),
                      )
                    : []
                }
                depth={0}
                stacked
              >
                <div class="flex w-full min-w-0 flex-col">
                  <Head
                    type={type() ?? model()?.name ?? ""}
                    tint={tint()}
                    rule={rule()}
                    label={label()}
                    onFold={onFold()}
                    href={
                      props.asChip && props.value.id
                        ? `/${type()}/${props.value.id}`
                        : undefined
                    }
                  />
                  {/* (more room under the head than a reified relation has: its first row is a field's, text with no box, not a chip) */}
                  <div class={["ml-2 pt-6", nestedClass, rule()]}>
                    <Fields
                      value={props.value}
                      model={model()}
                      depth={props.depth}
                    />
                  </div>
                </div>
              </SpaceBands>
            </div>
          }
        >
          <Match when={isChip()}>
            <ReferenceChip
              type={type() ?? ""}
              label={label() ?? String(props.value.id ?? "")}
              href={`/${type()}/${props.value.id}`}
              spaces={contextTrail(
                contextLabels(),
                String(props.value.id ?? ""),
              )}
              edgeProperties={
                isObject(props.value.edgeProperties)
                  ? props.value.edgeProperties
                  : undefined
              }
              edgeModel={
                props.field?.kind === "relation"
                  ? edgeModelFor(props.field.options ?? [], type() ?? "")
                  : undefined
              }
            />
          </Match>
          <Match when={folded()}>
            {/* (folded: what it holds in its place, after a marker in the colour of its type that shows it whole, then its own filled fields, each with its name) */}
            <span
              class="inline-flex min-w-0 scroll-mt-28 flex-wrap items-center gap-x-2 gap-y-1"
              data-item-id={partId()}
            >
              <Show when={!props.inFold}>
                <button
                  type="button"
                  class={[
                    "flex h-6 w-6 shrink-0 cursor-pointer items-center justify-center rounded-xs border-[0.5px] border-slate-400/70 text-xs select-none hover:brightness-90",
                    tint() || plainTint,
                  ]}
                  aria-label={t("collapse_show_whole", "Show the whole {name}", {
                    name: modelName(type() ?? ""),
                  })}
                  title={t("collapse_show_whole", "Show the whole {name}", {
                    name: modelName(type() ?? ""),
                  })}
                  onClick={() => setWhole(true)}
                >
                  ▸
                </button>
              </Show>
              <Value value={collapsed()!.held} depth={props.depth} inFold />
              <For each={collapsed()!.extras}>
                {(extra) => (
                  <span class="inline-flex min-w-0 items-baseline gap-1.5">
                    <span class="text-xs font-semibold text-slate-500 uppercase">
                      {fieldName(model()!.name, extra.field.name)}
                    </span>
                    <span class="text-sm break-words">{plain(extra.value)}</span>
                  </span>
                )}
              </For>
            </span>
          </Match>
          <Match when={isReified() && headless()}>
            {/* (without its head: what it holds as the field's own, then its own fields under it, as an annotated value) */}
            <div class="flex w-full min-w-0 scroll-mt-28 flex-col gap-3" data-item-id={partId()} data-block>
              <div class="flex min-w-0 flex-wrap items-start gap-x-2 gap-y-4">
                <Value value={props.value.target} depth={props.depth} />
              </div>
              <Fields value={props.value} model={model()} depth={props.depth} exclude="target" />
            </div>
          </Match>
          <Match when={isReified()}>
            {/* (a reified relation: its type at the head, then what it holds, full width and without its field name, then its own fields, if it has any) */}
            <div
              class="flex w-full min-w-0 scroll-mt-28 flex-col"
              data-item-id={partId()}
              data-block
            >
              <Head
                type={type() ?? ""}
                tint={tint()}
                rule={rule()}
                label={label()}
                onFold={onFold()}
              />
              <div class={["ml-2 pt-4", nestedClass, rule()]}>
                {/* (what it holds first, then what is said of the relation) */}
                <div class="flex min-w-0 flex-wrap items-start gap-x-2 gap-y-4">
                  <Value value={props.value.target} depth={props.depth} />
                </div>
                <Fields
                  value={props.value}
                  model={model()}
                  depth={props.depth}
                  exclude="target"
                />
              </div>
            </div>
          </Match>
          <Match when={isAnnotated()}>
            {/* (an annotated value: the value as the field's own, then what is said of it, as in the form) */}
            <div class="flex w-full min-w-0 flex-col gap-3">
              <div class="flex min-w-0 flex-wrap items-start gap-x-2 gap-y-4">
                <Value value={props.value.value} depth={props.depth} />
              </div>
              <Fields
                value={props.value}
                model={model()}
                depth={props.depth}
                exclude="value"
              />
            </div>
          </Match>
          <Match when={isEmbedded()}>
            {/* (it is in this one place only: no box, no type, only its fields, indented to show they go together) */}
            <div class={["ml-2 w-full", nestedClass, "border-slate-300"]}>
              <Fields value={props.value} model={model()} depth={props.depth} />
            </div>
          </Match>
          <Match when={isSpace()}>
            <div
              class={[
                "flex w-full min-w-0 flex-col rounded-xs",
                spaceTint(model()?.interfaceMeta?.colour, props.depth),
              ]}
            >
              <span class={spaceTypeClass}>{modelName(type() ?? "")}</span>
              <div class="flex min-w-0 flex-1 flex-wrap items-start gap-x-2 gap-y-6 p-3">
                <Value value={props.value.contents} depth={props.depth + 1} />
              </div>
            </div>
          </Match>
        </Switch>
      }
    />
  );
}

/**
 * The contents of one Document or Entity, laid out by its model: keys on the left, contents
 * on the right, and what is nested inside nested the same way, to any depth.
 */
/**
 * A value of a field as the item's page shows it (a chip, a block, a band, text): for an interface module's card
 * that shows what a model holds in its own way. `field`: the field it is the value of (its edge model, its type)
 */
export function ItemValue(props: { value: unknown; field?: FieldDefinition; depth?: number }) {
  return <Value value={props.value} field={props.field} depth={props.depth ?? 1} />;
}

export function ItemContents(props: ItemContentsProps) {
  const definitions = useModels();
  const model = () =>
    getModel(
      definitions,
      typeof props.item.type === "string" ? props.item.type : "",
    );
  return <Fields value={props.item} model={model()} depth={0} />;
}
