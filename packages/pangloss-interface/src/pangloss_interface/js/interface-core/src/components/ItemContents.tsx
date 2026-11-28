import { createSignal, For, Match, Show, Switch, untrack } from "solid-js";
import type { JSX } from "@solidjs/web";
import type { ParentProps } from "solid-js";
import {
  useComponent,
  useModels,
  useModules,
  useTranslations,
} from "../context";
import { dataBand, ExternalLink, kindRule, kindTint, spaceBand } from "../primitives";
import { contextTrail } from "../api";
import type { PathEntry } from "../api";
import {
  collapsedView,
  degreeField,
  edgeModelFor,
  getModel,
  headlessIn,
} from "../schema";
import type {
  FieldDefinition,
  ItemContentsProps,
  ModelDefinition,
} from "../types";
import { CITED_BASIS, CitationChips, CitedBasisChips, isCitation } from "./Citation";
import { Customised, PartActions } from "./Customised";
import { IncomingRelations } from "./IncomingRelations";
import { holdsId, NestingProvider, RevealProvider, startsFolded, useInIncoming, useNesting, useRevealed } from "./nesting";
import { Head } from "./Head";
import { AssertionMark, SpaceBands, useDegreeName } from "./SpaceBands";
import {
  fieldGridClass,
  fieldRowClass,
  fieldRuleClass,
  nestedClass,
  plainTint,
  smallButtonClass,
  spacePaddingClass,
  spaceTypeClass,
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
 * The rows of an object: a key and its contents for each field of its model, in the order of
 * the model, the keys in a column on the left and the contents on the right. Fields with
 * nothing in them are left out, and those only in the database (worked out, not said). What refers to the
 * object from elsewhere is not here: `IncomingRelations` (after the rows, on the item's own page).
 */
function Fields(props: {
  value: Data;
  model: ModelDefinition | undefined;
  depth: number;
  /** (the fields that are shown some other way) */
  exclude?: string | readonly string[];
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
              ![props.exclude ?? []].flat().includes(field.key) &&
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
  const { t, memberName } = useTranslations();
  const degreeName = useDegreeName();
  const enums = useModels();
  const typeOf = () =>
    props.field?.kind === "literal" ? props.field.type : props.field?.kind === "list" ? props.field.item : undefined;
  // (a member of an enum by its name, as the form says it, in the language of the page: not the value that is stored)
  const member = () => {
    const type = typeOf();
    if (type === undefined || !("type" in type) || type.type !== "enum" || isObject(props.value) || Array.isArray(props.value))
      return undefined;
    const found = enums.enums?.[type.enum]?.members.find((each) => each.value === props.value);
    return found ? memberName(type.enum, found.name) : undefined;
  };
  // (a value of a field that is a URL, as an address the browser can go to: a link, not the `javascript:` of someone's typing)
  const webAddress = () => {
    const type = typeOf();
    const isUrl = type !== undefined && "format" in type && type.format === "url";
    return isUrl && typeof props.value === "string" && /^https?:/i.test(props.value) ? props.value : undefined;
  };
  // (a space's degree, `Degree()`: its step in words)
  const degree = () =>
    typeof props.value === "string" && props.field && "markers" in props.field && isDegreeField(props.field)
      ? degreeName(props.value)
      : undefined;
  return (
    <Switch
      fallback={
        <span class="w-full text-sm break-words whitespace-pre-wrap">
          {String(props.value)}
        </span>
      }
    >
      <Match when={member()}>{(name) => <span class="w-full text-sm">{name()}</span>}</Match>
      <Match when={degree()}>{(name) => <span class="w-full text-sm">{name()}</span>}</Match>
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
  // (what is referred to can be inside semantic spaces and other documents: the API says so in its `meta`, the path)
  const storedPath = () =>
    isObject(props.value.meta) ? (props.value.meta.path as PathEntry[] | null | undefined) : undefined;
  const trail = () => contextTrail(storedPath(), definitions);
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
  // (a space's band: its tint, and the pattern of its kind)
  const band = () => spaceBand(definitions, model()?.name ?? "", props.depth);
  // (a reified relation or a semantic space that is all its field can hold, and it holds one: no head,
  // `InterfaceMeta(headless=True)`)
  const headless = () =>
    props.field?.kind === "relation" && headlessIn(definitions, props.field, type() ?? "");
  // (a space's fields other than what it holds, that say something here: a degree)
  const ownFields = () =>
    (model()?.fields ?? []).some(
      (field) => field.key !== "contents" && !field.dbField && !isEmpty(props.value[field.key]),
    );
  // (a space with its head: its degree is beside the head, and its other fields of its own under what it holds)
  const degree = () => degreeField(model());
  const headedOwn = () => ["contents", ...(degree() ? [degree()!.key] : [])];
  const headedFields = () =>
    (model()?.fields ?? []).some(
      (field) => !headedOwn().includes(field.key) && !field.dbField && !isEmpty(props.value[field.key]),
    );
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
  // (in a list of what refers to the page's item: a card the model names is told so)
  const incoming = useInIncoming();
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
  // (a citation of another document, `Cites[T]`: shown as what it cites, never as a block of its own fields)
  if (isCitation(untrack(type))) return <CitationChips value={props.value} />;
  // (something derived that was cited: what was chosen, and the citations of what it rests on)
  if (untrack(type) === CITED_BASIS) return <CitedBasisChips value={props.value} />;
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
        incoming: incoming || undefined,
      }}
      fallback={
        <Switch
          fallback={
            // (a block takes a line of its own, as far from what is above it as from what is below: the row's gap)
            <div class="w-full min-w-0 scroll-mt-28" data-item-id={partId()} data-block>
              <SpaceBands
                spaces={props.asChip ? trail() : []}
                depth={0}
                stacked
              >
                <div class="flex w-full min-w-0 flex-col">
                  <Head
                    type={type() ?? model()?.name ?? ""}
                    tint={tint()}
                    rule={rule()}
                    label={label()}
                    // (something of another document that refers to the item: what its path says of it, if not that it is so)
                    mark={<AssertionMark path={props.asChip ? storedPath() : undefined} class="flex shrink-0 items-center pr-2" />}
                    onFold={onFold()}
                    open={open()}
                    onToggle={onToggle}
                    href={
                      // (a document inside this one has a page of its own, as what is referred to has)
                      (props.asChip || model()?.kind === "Document") && props.value.id
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
              spaces={trail()}
              path={props.asChip ? storedPath() : undefined}
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
              {/* (what an interface module adds beside the part: a button to confirm it, say) */}
              <PartActions type={type() ?? ""} item={props.value} page="item" place="inline" />
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
                // (what an interface module adds to the part's bar: a button to confirm it, say)
                lead={<PartActions type={type() ?? ""} item={props.value} page="item" place="bar" />}
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
          <Match when={isSpace() && headless()}>
            {/* (without its head, but in its band and colour, so that a reader still sees that what it holds is
                inside it: what it holds, then its own fields, as a headless reified relation has them) */}
            <div
              class={["flex w-full min-w-0 flex-col gap-3 rounded-xs", spacePaddingClass, band().class]}
              data-headless={type()}
              data-band={dataBand(band().pattern)}
            >
              <div class="flex min-w-0 flex-1 flex-wrap items-start gap-x-2 gap-y-6">
                <Value value={props.value.contents} depth={props.depth + 1} />
              </div>
              <Show when={ownFields()}>
                <Fields value={props.value} model={model()} depth={props.depth + 1} exclude="contents" />
              </Show>
            </div>
          </Match>
          <Match when={isSpace()}>
            <div class={["flex w-full min-w-0 flex-col rounded-xs", band().class]} data-band={dataBand(band().pattern)}>
              <div class="flex min-w-0 flex-wrap items-baseline">
                <span data-type-info={type() ?? undefined} class={spaceTypeClass}>{modelName(type() ?? "")}</span>
                <Show when={model()}>
                  {(space) => <SpaceDegree model={space()} value={degree() ? props.value[degree()!.key] : undefined} />}
                </Show>
              </div>
              <div class={["flex min-w-0 flex-1 flex-wrap items-start gap-x-2 gap-y-6", spacePaddingClass]}>
                <Value value={props.value.contents} depth={props.depth + 1} />
              </div>
              <Show when={headedFields()}>
                {/* (as far in as what it holds, and under it with no more room than a row has) */}
                <div class="min-w-0 px-3 pb-3 @max-md:px-1.5 @max-md:pb-1.5 @max-sm:px-0.5 @max-sm:pb-1">
                  <Fields value={props.value} model={model()} depth={props.depth + 1} exclude={headedOwn()} />
                </div>
              </Show>
            </div>
          </Match>
        </Switch>
      }
    />
  );
}

/** Whether a field is a space's degree (`Degree()`) */
const isDegreeField = (field: FieldDefinition) =>
  "markers" in field && (field.markers ?? []).some((marker) => marker.name === "Degree");

/**
 * The degree of a space, beside its head: the step entered on it, in words; where none is, its class's default,
 * muted (nothing if the class has none)
 */
function SpaceDegree(props: { model: ModelDefinition; value: unknown }) {
  const { t, modelName } = useTranslations();
  const degreeName = useDegreeName();
  const entered = () => (typeof props.value === "string" && props.value ? props.value : undefined);
  return (
    <Show
      when={entered()}
      fallback={
        <Show when={props.model.degree}>
          {(fallback) => (
            <span
              data-space-degree={fallback()}
              data-default
              class="pr-3 text-xs text-slate-500 italic select-none"
              title={t("degree_default_title", "No degree is entered: this is the default of {space}", {
                space: modelName(props.model.name),
              })}
            >
              {t("degree_default", "{degree} (default)", { degree: degreeName(fallback()) })}
            </span>
          )}
        </Show>
      }
    >
      {(step) => (
        <span data-space-degree={step()} class="pr-3 text-xs text-slate-800">
          {degreeName(step())}
        </span>
      )}
    </Show>
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
          exclude={props.exclude}
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
