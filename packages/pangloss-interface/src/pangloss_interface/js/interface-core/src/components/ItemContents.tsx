import { createSignal, For, Match, Show, Switch } from "solid-js";
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
import { collapsedView, getModel } from "../schema";
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
 * nothing in them are left out. What refers to the object from elsewhere (`incoming`) follows,
 * as chips.
 */
function Fields(props: {
  value: Data;
  model: ModelDefinition | undefined;
  depth: number;
  /** (a field that is shown some other way) */
  exclude?: string;
}) {
  const { fieldName, incomingName } = useTranslations();
  return (
    <dl class={fieldGridClass}>
      <For each={props.model?.fields ?? []}>
        {(field) => (
          <Show
            when={
              field.key !== props.exclude && !isEmpty(props.value[field.key])
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
  const hasFields = () =>
    (model()?.fields ?? []).some((field) => !isEmpty(props.value[field.key]));
  const isChip = () =>
    type() !== undefined &&
    ((props.asChip && !hasFields()) || model()?.kind === "Entity");
  const isReified = () =>
    model()?.kind === "ReifiedRelation" ||
    model()?.kind === "ReifiedRelationDocument";
  const isSpace = () => model()?.kind === "SemanticSpace";
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
export function ItemContents(props: ItemContentsProps) {
  const definitions = useModels();
  const model = () =>
    getModel(
      definitions,
      typeof props.item.type === "string" ? props.item.type : "",
    );
  return <Fields value={props.item} model={model()} depth={0} />;
}
