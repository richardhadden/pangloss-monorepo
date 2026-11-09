import { createSignal, For, Match, Show, Switch, untrack } from "solid-js";
import type { JSX } from "@solidjs/web";
import type { ParentProps } from "solid-js";
import {
  useComponent,
  useModels,
  useModules,
  useTranslations,
} from "../context";
import { ExternalLink, kindRule, kindTint, spaceTint } from "../primitives";
import { contextTrail } from "../api";
import type { ContextLabel } from "../api";
import {
  collapsedView,
  edgeModelFor,
  getModel,
  headlessIn,
} from "../schema";
import type {
  FieldDefinition,
  ItemContentsProps,
  ModelDefinition,
} from "../types";
import { Customised } from "./Customised";
import { IncomingRelations } from "./IncomingRelations";
import { holdsId, NestingProvider, RevealProvider, startsFolded, useNesting, useRevealed } from "./nesting";
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
  spacePaddingClass,
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
 * anything bigger, and each text, on a line of its own, with a faint rule above it as in a form.
 * (A row of what refers to the item from elsewhere is `IncomingRelations`'s own.)
 */
function Row(props: ParentProps<{ name: string }>) {
  return (
    <div class={fieldRowClass}>
      <dt class="pt-1 text-xs font-semibold text-slate-500 uppercase">
        {props.name}
      </dt>
      {/* (a row with a block in it has blocks as far apart as rows of what refers to the item: `data-block`) */}
      <dd class="flex min-w-0 flex-wrap items-start gap-x-2 gap-y-4 has-[>[data-block]]:gap-y-6">
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
  /** A block nested deep enough to start folded (`startsFolded`): whether it is open, and the button that opens and folds it */
  open?: boolean;
  onToggle?: () => void;
}) {
  const { t, modelName } = useTranslations();
  const contents = () => (
    <>
      <span data-type-info={props.type} class={[typeChipClass, props.tint || plainTint, props.rule]}>
        {modelName(props.type)}
      </span>
      <span class={headRestClass}>
        <Show
          when={props.onToggle && !props.href}
          fallback={
            <Show when={props.label}>
              <span class={headLabelClass}>{props.label}</span>
            </Show>
          }
        >
          {/* (as in the form: the grey of the bar, with the label in it, folds and unfolds it; folded, a ▸ says so) */}
          <button
            type="button"
            class="flex min-w-0 flex-1 cursor-pointer items-center gap-2 px-3 py-1 text-left text-sm hover:bg-slate-400/20 focus-visible:bg-slate-400/20 focus-visible:outline-none"
            aria-expanded={props.open ? "true" : "false"}
            aria-label={t("fold", "Fold or unfold {name}", { name: modelName(props.type) })}
            title={t("fold", "Fold or unfold {name}", { name: modelName(props.type) })}
            onClick={() => props.onToggle!()}
          >
            <Show when={!props.open}>
              <span aria-hidden="true" class="shrink-0 text-xs text-slate-500">
                ▸
              </span>
            </Show>
            <span class="min-w-0 truncate">{props.label}</span>
          </button>
        </Show>
        <Show when={props.onToggle && props.href}>
          <button
            type="button"
            class={[headButtonClass, "ml-auto text-slate-500 hover:bg-slate-400/30"]}
            aria-expanded={props.open ? "true" : "false"}
            aria-label={t("fold", "Fold or unfold {name}", { name: modelName(props.type) })}
            title={t("fold", "Fold or unfold {name}", { name: modelName(props.type) })}
            onClick={() => props.onToggle!()}
          >
            {props.open ? "▾" : "▸"}
          </button>
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
 * nothing in them are left out, and those only in the database (worked out, not said). What refers to the
 * object from elsewhere is not here: `IncomingRelations` (after the rows, on the item's own page).
 */
function Fields(props: {
  value: Data;
  model: ModelDefinition | undefined;
  depth: number;
  /** (a field that is shown some other way) */
  exclude?: string;
  /** Rows before those of the fields */
  lead?: JSX.Element;
}) {
  const { fieldName } = useTranslations();
  return (
    <dl class={fieldGridClass}>
      {props.lead}
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
    </dl>
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
  // (a value of a field that is a URL, as an address the browser can go to: a link, not the `javascript:` of someone's typing)
  const webAddress = () => {
    const type = props.field?.kind === "literal" ? props.field.type : props.field?.kind === "list" ? props.field.item : undefined;
    const isUrl = type !== undefined && "format" in type && type.format === "url";
    return isUrl && typeof props.value === "string" && /^https?:/i.test(props.value) ? props.value : undefined;
  };
  return (
    <Switch
      fallback={
        <span class="w-full text-sm break-words whitespace-pre-wrap">
          {String(props.value)}
        </span>
      }
    >
      <Match when={webAddress()}>
        {(address) => (
          <ExternalLink href={address()} class="w-full text-sm">
            {address()}
          </ExternalLink>
        )}
      </Match>
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
  // (a block this deep starts folded, and what it holds is made when it is opened: see `nesting.ts`)
  const nesting = useNesting();
  const deep = startsFolded(nesting);
  const revealed = useRevealed();
  const holdsRevealed = () => {
    const id = revealed();
    return id !== null && holdsId(props.value, id);
  };
  const [open, setOpen] = createSignal(!deep || untrack(holdsRevealed));
  const onToggle = deep ? () => setOpen(!open()) : undefined;
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
                    open={open()}
                    onToggle={onToggle}
                    href={
                      props.asChip && props.value.id
                        ? `/${type()}/${props.value.id}`
                        : undefined
                    }
                  />
                  <Show when={open()}>
                    {/* (more room under the head than a reified relation has: its first row is a field's, text with no box, not a chip) */}
                    <div class={["ml-2 pt-6", nestedClass, rule()]}>
                      <NestingProvider value={nesting + 1}>
                        <Fields
                          value={props.value}
                          model={model()}
                          depth={props.depth}
                        />
                      </NestingProvider>
                    </div>
                  </Show>
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
                open={open()}
                onToggle={onToggle}
              />
              <Show when={open()}>
                <div class={["ml-2 pt-4", nestedClass, rule()]}>
                  <NestingProvider value={nesting + 1}>
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
                  </NestingProvider>
                </div>
              </Show>
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
              <span data-type-info={type() ?? undefined} class={spaceTypeClass}>{modelName(type() ?? "")}</span>
              <div class={["flex min-w-0 flex-1 flex-wrap items-start gap-x-2 gap-y-6", spacePaddingClass]}>
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
  const { t } = useTranslations();
  const model = () =>
    getModel(
      definitions,
      typeof props.item.type === "string" ? props.item.type : "",
    );
  // (what the API says are an entity's URIs)
  const uris = () => (Array.isArray(props.item.urls) ? (props.item.urls as string[]) : []);
  // (whether any of the item's own fields is shown: what refers to it is ruled off from them)
  const hasFields = () =>
    uris().length > 0 || (model()?.fields ?? []).some((field) => !field.dbField && !isEmpty(props.item[field.key]));
  // (an item that something can refer to: the model has incoming fields)
  const referable = () => {
    const found = model();
    return found && (found.incoming ?? []).length > 0 && typeof props.item.id === "string" ? found : undefined;
  };
  return (
    // (what the rows of the fields measure themselves by: see `fieldGridClass`)
    <div class="@container w-full min-w-0">
      <RevealProvider value={() => props.show ?? null}>
        <Fields
          value={props.item}
          model={model()}
          depth={0}
          lead={
            <Show when={uris().length > 0}>
              <Row name={t("uris", "URIs")}>
                <For each={uris()}>
                  {(address) => (
                    <ExternalLink href={address} class="w-full text-sm">
                      {address}
                    </ExternalLink>
                  )}
                </For>
              </Row>
            </Show>
          }
        />
      </RevealProvider>
      <Show when={referable()}>
        {(model) => (
          <IncomingRelations
            item={props.item}
            model={model()}
            afterFields={hasFields()}
            chips={(items) => <Value value={items} depth={0} asChip />}
          />
        )}
      </Show>
    </div>
  );
}

export default ItemContents;
