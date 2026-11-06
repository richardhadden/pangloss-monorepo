import { createEffect, createMemo, createSignal, Errored, For, Loading, Match, Show, Switch } from "solid-js";
import type { ParentProps } from "solid-js";
import { Dynamic } from "@solidjs/web";
import {
  useApi,
  useComponent,
  useIncomingView,
  useModels,
  useModules,
  useTranslations,
} from "../context";
import { kindRule, kindTint, spaceTint } from "../primitives";
import { contextTrail, getIncoming, INCOMING_PAGE } from "../api";
import type { ContextLabel } from "../api";
import {
  collapsedView,
  edgeModelFor,
  getModel,
  headlessIn,
} from "../schema";
import type {
  FieldDefinition,
  IncomingEntry,
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
  smallButtonClass,
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

/** What has been read of what refers to an item: by the key of the incoming field, the items it has now */
type Read = Record<string, Data[]>;

const asItems = (value: unknown): Data[] =>
  (Array.isArray(value) ? value : value ? [value] : []).filter(isObject);

/**
 * After the items of a row of what refers to an entity, when there are more than were read with it: "and 109 more",
 * which reads the next of them (a hundred at a time, by label, as the first were) and gives the row what it has now.
 */
function MoreIncoming(props: {
  page: { type: string; id: string };
  field: string;
  /** What the row has */
  items: Data[];
  /** How many it does not have */
  left: number;
  onRead: (items: Data[]) => void;
}) {
  const api = useApi();
  const { t } = useTranslations();
  const [reading, setReading] = createSignal(false);
  const read = async () => {
    setReading(true);
    try {
      // (whole pages from the start: what the row has of the page it is in is read again with the rest of it)
      const page = Math.floor(props.items.length / INCOMING_PAGE) + 1;
      const kept = props.items.slice(0, (page - 1) * INCOMING_PAGE);
      const answer = await getIncoming(api, props.page.type, props.page.id, props.field, page);
      props.onRead([...kept, ...answer.results]);
    } finally {
      setReading(false);
    }
  };
  return (
    <button
      type="button"
      class={[smallButtonClass, "text-slate-600 disabled:text-slate-400"]}
      disabled={reading()}
      data-testid="incoming-more"
      onClick={() => void read()}
    >
      {t("incoming_more", "and {count} more", { count: props.left })}
    </button>
  );
}

/**
 * Above an interface module's view of what refers to an entity, when not all of it has been read: the view has only
 * what the page has (sorted by date, the first few of each field are not the earliest), so it says how many are
 * missing, and reads them all when asked.
 */
function ReadAllIncoming(props: {
  page: { type: string; id: string };
  /** The fields that have more than was read, by key, with what each has */
  fields: { key: string; items: Data[] }[];
  left: number;
  /** (once, with every field: the view is laid out again for each change of what it has) */
  onRead: (read: Read) => void;
}) {
  const api = useApi();
  const { t } = useTranslations();
  const [reading, setReading] = createSignal(false);
  const all = async (key: string): Promise<Data[]> => {
    let items: Data[] = [];
    for (let page = 1; ; page++) {
      const answer = await getIncoming(api, props.page.type, props.page.id, key, page, 500);
      items = [...items, ...answer.results];
      if (answer.results.length === 0 || items.length >= answer.count) return items;
    }
  };
  const read = async () => {
    setReading(true);
    try {
      const keys = props.fields.map((field) => field.key);
      const found: Read = {};
      // (a few fields at a time: an entity can have a hundred)
      const next = async (): Promise<void> => {
        const key = keys.shift();
        if (key === undefined) return;
        found[key] = await all(key);
        return next();
      };
      await Promise.all(Array.from({ length: 6 }, next));
      props.onRead(found);
    } finally {
      setReading(false);
    }
  };
  return (
    <p class="mt-6 flex flex-wrap items-center gap-3 text-xs text-slate-600" data-testid="incoming-not-read">
      <span>{t("incoming_not_read", "{count} more refer to this and are not read yet", { count: props.left })}</span>
      <button
        type="button"
        class={[smallButtonClass, "text-slate-600 disabled:text-slate-400"]}
        disabled={reading()}
        onClick={() => void read()}
      >
        {t("incoming_read_all", "Read them all")}
      </button>
    </p>
  );
}

/**
 * The rows of an object: a key and its contents for each field of its model, in the order of
 * the model, the keys in a column on the left and the contents on the right. Fields with
 * nothing in them are left out, and those only in the database (worked out, not said). What refers to the object from
 * elsewhere (`incoming`) follows, as chips, by the field it is in; on the item's own page, an interface module's view
 * of it (`incomingViews`, chosen in the console) can take some of it, to show after the rows in its own way.
 *
 * An entity's page is read with the first few of each incoming field and how many there are (`incomingCounts`): a
 * row that has more ends in "and N more" (`MoreIncoming`), and a module's view says how many it is without
 * (`ReadAllIncoming`).
 */
function Fields(props: {
  value: Data;
  model: ModelDefinition | undefined;
  depth: number;
  /** (a field that is shown some other way) */
  exclude?: string;
  /** (the item's own page: its type and id, for a module's view of what refers to it) */
  page?: { type: string; id: string };
}) {
  const { fieldName, incomingName } = useTranslations();
  const definitions = useModels();
  const views = useModules().incomingViews();
  const incoming = useIncomingView();
  // What has been read of what refers to the item since it was (forgotten when the item is another, or read again)
  const [read, setRead] = createSignal<Read>(() => (void props.value, {}));
  const itemsOf = (key: string): Data[] => read()[key] ?? asItems(props.value[key]);
  const counts = () => (isObject(props.value.incomingCounts) ? (props.value.incomingCounts as Record<string, number>) : {});
  // (how many of a field the page does not have)
  const leftOf = (key: string) => Math.max(0, (counts()[key] ?? 0) - itemsOf(key).length);
  const partial = createMemo(() =>
    (props.model?.incoming ?? [])
      .filter((incoming) => leftOf(incoming.key) > 0)
      .map((incoming) => ({ key: incoming.key, items: itemsOf(incoming.key) })),
  );
  const entries = createMemo<IncomingEntry[]>(() =>
    (props.model?.incoming ?? []).flatMap((incoming) =>
      itemsOf(incoming.key).map((item) => ({
        key: incoming.key,
        name: incomingName(props.model!.name, incoming.name),
        item,
      })),
    ),
  );
  // (the views that have something to show: only on the item's own page)
  const offered = createMemo(() =>
    props.page && views.length > 0
      ? views.filter((view) => entries().some((entry) => view.takes(entry.item, definitions)))
      : [],
  );
  // (the console offers each for as long as it has something)
  createEffect(offered, (now) => {
    const withdraw = now.map((view) => incoming.offer(view.name));
    return () => withdraw.forEach((done) => done());
  });
  const view = () => offered().find((view) => view.name === incoming.chosen());
  const taken = createMemo(() => {
    const chosen = view();
    return chosen ? entries().filter((entry) => chosen.takes(entry.item, definitions)) : [];
  });
  // (what the view does not take, by the relation it is in)
  const restByField = createMemo(() => {
    const groups = new Map<string, IncomingEntry[]>();
    for (const entry of entries()) {
      if (!taken().includes(entry)) groups.set(entry.name, [...(groups.get(entry.name) ?? []), entry]);
    }
    return [...groups.entries()];
  });
  return (
    <>
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
        <Show
          when={view()}
          fallback={
            <For each={props.model?.incoming ?? []}>
              {(incoming) => (
                <Show when={itemsOf(incoming.key).length > 0}>
                  <Row name={incomingName(props.model!.name, incoming.name)} incoming>
                    <Value value={itemsOf(incoming.key)} depth={props.depth} asChip />
                    <Show when={props.page && leftOf(incoming.key) > 0}>
                      <MoreIncoming
                        page={props.page!}
                        field={incoming.key}
                        items={itemsOf(incoming.key)}
                        left={leftOf(incoming.key)}
                        onRead={(items) => setRead((before) => ({ ...before, [incoming.key]: items }))}
                      />
                    </Show>
                  </Row>
                </Show>
              )}
            </For>
          }
        >
          <For each={restByField()}>
            {([name, group]) => (
              <Row name={name} incoming>
                <Value value={group.map((entry) => entry.item)} depth={props.depth} asChip />
              </Row>
            )}
          </For>
        </Show>
      </dl>
      <Show when={view() && props.page && partial().length > 0}>
        <ReadAllIncoming
          page={props.page!}
          fields={partial()}
          left={partial().reduce((sum, field) => sum + leftOf(field.key), 0)}
          onRead={(found) => setRead((before) => ({ ...before, ...found }))}
        />
      </Show>
      <Show when={view() && props.page && props.model ? view() : undefined}>
        {(chosen) => (
          <Errored
            fallback={(error) => {
              // (said in the browser's console, so that a module's author sees why there is nothing)
              console.error("A view of an interface module failed:", error());
              return null;
            }}
          >
            <Loading fallback={null}>
              {/* (`Dynamic`: the view chosen is read where it is shown, so another one chosen is shown) */}
              <Dynamic
                component={chosen().component}
                type={props.page!.type}
                id={props.page!.id}
                model={props.model!}
                entries={taken()}
              />
            </Loading>
          </Errored>
        )}
      </Show>
    </>
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
export function ItemValue(props: { value: unknown; field?: FieldDefinition; depth?: number; asChip?: boolean }) {
  return <Value value={props.value} field={props.field} depth={props.depth ?? 1} asChip={props.asChip} />;
}

export function ItemContents(props: ItemContentsProps) {
  const definitions = useModels();
  const model = () =>
    getModel(
      definitions,
      typeof props.item.type === "string" ? props.item.type : "",
    );
  const page = () =>
    typeof props.item.type === "string" && typeof props.item.id === "string"
      ? { type: props.item.type, id: props.item.id }
      : undefined;
  return <Fields value={props.item} model={model()} depth={0} page={page()} />;
}
