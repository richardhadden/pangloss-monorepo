import { createContext, createEffect, createMemo, createSignal, flush, For, Match, onCleanup, onSettled, Show, Switch, untrack, useContext } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";
import type { JSX } from "@solidjs/web";
import { searchFieldTypes } from "../../api";
import { createItemFormState, useApi, useComponent, useModels, useTranslations } from "../../context";
import type { ItemFormState } from "../../context";
import { buttonClass, kindRule, kindTint, segmentClass, segmentedClass } from "../../primitives";
import {
  getModel,
  documentTypesOf,
  extraRowsOf,
  foundTargets,
  newCondition,
  newRow,
  whereWithout,
  incomingSourcesOf,
  menuGroups,
  operatorsOf,
  searchFieldsOf,
  searchKindOf,
  semanticSpacesOf,
  orderFieldsOf,
  wrappersOf,
  targetsEntities,
} from "../../schema";
import type {
  ExtraRow,
  FieldSearch,
  IncomingSearch,
  OrderSearch,
  SomewhereSearch,
  MenuGroup,
  NodeSearch,
  FormData,
  Path,
  PickedEntity,
  SearchField,
  SearchOperator,
  SearchOperators,
} from "../../schema";
import type { FieldType, ModelDefinitions, RelationOption } from "../../types";
import { EntityPicker } from "../form/EntityPicker";
import { MenuSelect } from "./MenuSelect";
import { deleteSearch, saveSearch, savedSearches } from "./saved";
import type { SavedSearch } from "./saved";
import { NumberInput, allowOnly, decimalCharacters } from "../form/NumberInput";
import { TypeMenu } from "../form/TypeMenu";
import {
  dateTimeWidthClass,
  dateWidthClass,
  fieldGridClass,
  fieldRowClass,
  headBarClass,
  headButtonClass,
  headLabelClass,
  headMenuButtonClass,
  headRestOpenClass,
  inputClass,
  nestedClass,
  numberWidthClass,
  plainTint,
  smallButtonClass,
  typeChipClass,
} from "../form/styles";

// (how long after the last change the search is made, as for the text box)
const DEBOUNCE_MS = 250;

// (how long the panel takes to slide open: its `duration-300`)
const SLIDE_MS = 300;

// (a text box of the form: as tall as the other things in a condition's line, 32px, the `md` of a button)
const boxClass = `${inputClass} h-8 py-0`;

// (the button that adds another condition on the same field: quiet, under what is there)
const addConditionClass = buttonClass("add");

// (the button that takes a condition out: square, as tall as the line it ends)
const removeConditionClass = `${buttonClass("ordinary", "md", true)} not-disabled:hover:text-red-800`;

// (the toggle that wants what does not hold: chosen, it is dark, as a chosen segment is)
// (the same, in the foot of the panel, as small as the buttons beside it)
const removeSmallClass = `${buttonClass("ordinary", "sm", true).replace("w-7", "w-6.5")} not-disabled:hover:text-red-800`;

/** Takes the entry `index` out of a list of the form, and the list with it if it was the last */
function removeEntry(form: ItemFormState, path: Path, index: number, count: number) {
  form.remove(count <= 1 ? path : [...path, index]);
}

const notClass = (pressed: boolean) => buttonClass(pressed ? "primary" : "ordinary", "md");

/** The ✕ of a remove button, drawn as the other icons are */
function RemoveIcon() {
  return (
    <svg viewBox="0 0 24 24" class="size-3.5 fill-none stroke-current stroke-2 select-none" stroke-linecap="square" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

interface SearchFormContext {
  form: ItemFormState;
}

const SearchContext = createContext<SearchFormContext>();

function useSearchForm(): ItemFormState {
  const found = useContext(SearchContext);
  if (!found) throw new Error("useSearchForm(): there is no <SearchPanel> above");
  return found.form;
}

/**
 * The search form of a list, which slides out from under the console bar (`open`) and pushes the list down: a row for
 * each field of `type` that can be searched, as the entry form has them, each with an operator (and a toggle to want
 * what does not hold), and the rows for what a document mentions or what refers to an entity. It edits a copy of
 * `initial`, and says what it holds a moment after each change (`onChange`), or at once on Enter. See
 * docs/search-form.md.
 */
export function SearchPanel(props: {
  type: string;
  initial?: NodeSearch;
  open: boolean;
  onChange: (form: NodeSearch) => void;
  onClose: () => void;
}) {
  const { t, modelName } = useTranslations();
  const type = untrack(() => props.type);
  const state = createItemFormState(untrack(() => props.initial ?? { type }) as unknown as FormData);
  let timer: ReturnType<typeof setTimeout> | undefined;
  onCleanup(() => clearTimeout(timer));
  const emit = () => {
    clearTimeout(timer);
    props.onChange(state.plain() as unknown as NodeSearch);
  };
  const changed = () => {
    clearTimeout(timer);
    timer = setTimeout(emit, DEBOUNCE_MS);
  };
  // (every change of the form is a search to make)
  const form: ItemFormState = {
    ...state,
    set: (path, value) => {
      state.set(path, value);
      changed();
    },
    remove: (path) => {
      state.remove(path);
      changed();
    },
  };
  // (the whole form, at once: a saved search loaded, or nothing)
  const replace = (next: NodeSearch) => {
    const now = state.plain() as Record<string, unknown>;
    const given = next as unknown as Record<string, unknown>;
    for (const key of new Set([...Object.keys(now), ...Object.keys(given)])) {
      if (key === "type") continue;
      if (key in given) state.set([key], structuredClone(given[key]));
      else state.remove([key]);
    }
    emit();
  };
  const clear = () => replace({ type });
  // (what is in it can only be clipped while it slides: a menu or a list of matches opens over its edge. Unclipped
  // when the slide is over by the clock, not by `transitionend`: the panel's code is loaded when it is first asked for,
  // so it is often made already open, there is no slide, and no event came, which left every menu cut off)
  const [settled, setSettled] = createSignal(false);
  createEffect(
    () => props.open,
    (open) => {
      setSettled(false);
      if (!open) return;
      const timer = setTimeout(() => setSettled(true), SLIDE_MS);
      return () => clearTimeout(timer);
    },
  );
  return (
    <SearchContext value={{ form }}>
      {/* (from under the bar: up into the page's top padding, which is given back under it) */}
      <div class="-mt-8">
        <section
          aria-label={t("search_form_of", "Search {type} by fields", { type: modelName(props.type) })}
          aria-hidden={props.open ? undefined : "true"}
          inert={props.open ? undefined : true}
          data-open={props.open ? "" : undefined}
          class={[
            // (a little in from the ends of the console, so the two read as two things)
            "mx-3 grid transition-[grid-template-rows,opacity] duration-300",
            { "grid-rows-[1fr]": props.open, "opacity-100": props.open },
            { "grid-rows-[0fr]": !props.open, "opacity-0": !props.open },
          ]}
          onKeyDown={(event) => {
            // (Enter searches at once: no waiting for the moment after the last change)
            if (event.key === "Enter" && event.target instanceof HTMLInputElement) emit();
          }}
        >
          <div class={["min-h-0", { "overflow-hidden": !settled() || !props.open }]}>
            <div class="rounded-b-xs border-[0.5px] border-t-0 border-slate-400/70 bg-slate-200/40">
              <div class="px-6 pt-6 pb-5">
                <NodeFields type={props.type} path={() => []} root />
              </div>
              <div class="flex items-center justify-end gap-2 border-t-[0.5px] border-slate-400/50 px-6 py-2">
                <SavedSearches type={props.type} current={() => state.plain() as unknown as NodeSearch} onLoad={replace} />
                <button type="button" class={smallButtonClass} onClick={clear}>
                  {t("search_clear", "Clear")}
                </button>
                <button type="button" class={smallButtonClass} onClick={() => props.onClose()}>
                  {t("search_close", "Close")}
                </button>
              </div>
            </div>
          </div>
        </section>
        <div class="h-8" />
      </div>
    </SearchContext>
  );
}

/**
 * The rows of the form for a node of `type` at `path`: only what has been added (a field, mentions, what refers to an
 * entity...), in the order it was added, then a menu to add another
 */
function NodeFields(props: {
  type: string;
  path: Accessor<Path>;
  /** The node the search is of (not what a relation points at) */
  root?: boolean;
  /** One of a group of alternatives: it has no groups of its own, nor an order */
  alternative?: boolean;
}) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t, fieldName } = useTranslations();
  const fields = createMemo(() => searchFieldsOf(definitions, props.type));
  const node = () => form.get(props.path()) as NodeSearch | undefined;
  // (the fields with a condition, in the order they were added: those of the type only)
  const shown = createMemo(() => {
    const given = Object.keys(node()?.fields ?? {});
    return given.flatMap((name) => fields().filter((field) => field.name === name));
  });
  const extras = createMemo(() =>
    extraRowsOf(definitions, props.type, { root: props.root, alternative: props.alternative }),
  );
  const has = (row: ExtraRow) => extras().includes(row) && node()?.[row] !== undefined;
  const nameOf = (field: SearchField) =>
    field.name === "label" ? t("label", "Label") : fieldName(props.type, field.name);
  const at = (row: ExtraRow) => () => [...props.path(), row];
  const removeRow = (row: ExtraRow) => () => form.remove([...props.path(), row]);
  return (
    <dl class={fieldGridClass}>
      <For each={shown()}>
        {(field) => (
          <ConditionRow
            type={props.type}
            field={field}
            name={nameOf(field)}
            path={() => [...props.path(), "fields", field.name]}
            root={props.root}
          />
        )}
      </For>
      <Show when={has("mentions")}>
        <MentionsRow path={at("mentions")} />
      </Show>
      <Show when={has("incoming")}>
        <IncomingRow type={props.type} path={at("incoming")} onRemove={removeRow("incoming")} />
      </Show>
      <Show when={has("somewhere")}>
        <SomewhereRow path={at("somewhere")} onRemove={removeRow("somewhere")} />
      </Show>
      <Show when={has("spaces")}>
        <SpacesRow path={at("spaces")} onRemove={removeRow("spaces")} />
      </Show>
      <Show when={has("anyOf")}>
        <AnyOfRow type={props.type} path={at("anyOf")} root={props.root} onRemove={removeRow("anyOf")} />
      </Show>
      <Show when={has("order")}>
        <OrderRow type={props.type} path={at("order")} onRemove={removeRow("order")} />
      </Show>
      <AddFilter
        fields={fields()
          .filter((field) => !(field.name in (node()?.fields ?? {})))
          .map((field) => ({ value: field.name, name: nameOf(field) }))}
        extras={extras().filter((row) => !has(row))}
        onField={(name) => {
          const field = fields().find((each) => each.name === name);
          if (field) form.set([...props.path(), "fields", name], newCondition(definitions, field));
        }}
        onExtra={(row) => form.set([...props.path(), row], newRow(definitions, props.type, row))}
      />
    </dl>
  );
}

/** The menu at the foot of a node's rows that adds a filter: a field, or one of the rows that are not fields */
function AddFilter(props: {
  fields: { value: string; name: string }[];
  extras: ExtraRow[];
  onField: (name: string) => void;
  onExtra: (row: ExtraRow) => void;
}) {
  const { t } = useTranslations();
  const extraName = (row: ExtraRow): string => {
    switch (row) {
      case "mentions":
        return t("search_mentions", "Mentions");
      case "incoming":
        return t("search_referred_to_by", "Referred to by");
      case "somewhere":
        return t("search_somewhere", "Contains");
      case "spaces":
        return t("search_in_spaces", "Inside");
      case "anyOf":
        return t("search_any_of", "Any of");
      case "order":
        return t("search_order_by", "Order by");
    }
  };
  return (
    <Show when={props.fields.length > 0 || props.extras.length > 0}>
      <div class={fieldRowClass}>
        <dt class="sr-only">{t("search_add_filter", "Add a filter")}</dt>
        <dd class="col-start-2 @max-md:col-start-1">
          <MenuSelect
            look="add"
            label={t("search_add_filter", "Add a filter")}
            placeholder={t("search_add_filter", "Add a filter")}
            options={[
              ...props.fields.map((field) => ({
                value: `field:${field.value}`,
                label: field.name,
                group: t("search_fields", "Fields"),
              })),
              ...props.extras.map((row) => ({ value: `row:${row}`, label: extraName(row), group: t("search_more", "More") })),
            ]}
            onChoose={(chosen) => {
              if (chosen.startsWith("field:")) props.onField(chosen.slice("field:".length));
              else if (chosen.startsWith("row:")) props.onExtra(chosen.slice("row:".length) as ExtraRow);
            }}
          />
        </dd>
      </div>
    </Show>
  );
}

/**
 * A row of the form, as the entry form has them: the name on the left (darker while it has a condition), then what it
 * is; `onRemove`: a button at its end that takes the row out
 */
function SearchRow(props: ParentProps<{ name: string; active: boolean; onRemove?: () => void }>) {
  const { t } = useTranslations();
  return (
    <div class={fieldRowClass} data-active={props.active ? "" : undefined}>
      <dt
        class={[
          "pt-2 text-xs font-semibold uppercase transition-colors",
          { "text-slate-500": !props.active, "text-slate-900": props.active },
        ]}
      >
        {props.name}
      </dt>
      <dd class="flex min-w-0 items-start gap-2">
        <div class="flex min-w-0 flex-1 flex-col items-start gap-3">{props.children}</div>
        <Show when={props.onRemove}>
          <button
            type="button"
            class={removeConditionClass}
            aria-label={t("search_remove_condition", "Remove the condition on {name}", { name: props.name })}
            title={t("search_remove_condition", "Remove the condition on {name}", { name: props.name })}
            onClick={() => props.onRemove?.()}
          >
            <RemoveIcon />
          </button>
        </Show>
      </dd>
    </div>
  );
}

/** The toggle that wants what does not hold */
function NotToggle(props: { name: string; pressed: boolean; onToggle: () => void }) {
  const { t } = useTranslations();
  return (
    <button
      type="button"
      aria-pressed={props.pressed ? "true" : "false"}
      aria-label={t("search_not_named", "Not: {name}", { name: props.name })}
      title={t("search_not_title", "Find what does not match this")}
      class={notClass(props.pressed)}
      onClick={() => props.onToggle()}
    >
      {t("search_not", "not")}
    </button>
  );
}

/** What an operator is called, for the kind of field it is on */
function useOperatorName() {
  const { t } = useTranslations();
  return (operators: SearchOperators | "mentions", op: SearchOperator): string => {
    const symbols: Partial<Record<SearchOperator, string>> = { gt: ">", gte: "≥", lt: "<", lte: "≤" };
    if (operators === "compare" && op === "eq") return "=";
    if (symbols[op]) return symbols[op]!;
    switch (op) {
      case "contains":
        return t("search_op_contains", "contains");
      case "starts_with":
        return t("search_op_starts_with", "starts with");
      case "eq":
        return t("search_op_is", "is");
      case "between":
        return t("search_op_between", "between");
      case "in":
        return t("search_op_one_of", "is one of");
      case "any":
        return t("search_op_any_of", "is any of");
      case "all":
        return t("search_op_all_of", "is all of");
      case "match":
        return t("search_op_matching", "is one matching");
      case "exists":
        return operators === "relation" || operators === "items"
          ? t("search_op_has_any", "has any")
          : t("search_op_has_value", "has a value");
      case "missing":
        return operators === "relation" || operators === "items"
          ? t("search_op_has_none", "has none")
          : t("search_op_has_no_value", "has no value");
      default:
        return op;
    }
  };
}

/** The menu of the operators of a field */
function OperatorSelect(props: {
  name: string;
  operators: SearchOperators | "mentions";
  ops: SearchOperator[];
  value: SearchOperator;
  onChoose: (op: SearchOperator) => void;
}) {
  const { t } = useTranslations();
  const operatorName = useOperatorName();
  return (
    <MenuSelect
      // (as wide in every row, so that what each is compared with starts at the same place)
      class="w-36 shrink-0"
      label={t("search_operator", "Condition on {name}", { name: props.name })}
      value={props.value}
      options={props.ops.map((op) => ({ value: op, label: operatorName(props.operators, op) }))}
      onChoose={(op) => props.onChoose(op as SearchOperator)}
    />
  );
}

// (the value an operator keeps of the one before: one end of a range, or the only value)
function carried(from: FieldSearch | undefined, op: SearchOperator): unknown {
  const value = from?.value;
  const range = op === "between";
  if (from?.op === "between") {
    const first = Array.isArray(value) ? value[0] : undefined;
    return range ? value : first;
  }
  if (from?.op === "in" || op === "in") return undefined;
  return range ? [value ?? "", ""] : value;
}

// (a value that the API takes: what is typed in a box for a number is a number)
function isBlankValue(value: unknown): boolean {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && value.every(isBlankValue));
}

/** Whether a condition is complete, so that it is part of the search */
function isActive(search: FieldSearch | undefined): boolean {
  if (!search) return false;
  switch (search.op) {
    case "exists":
    case "missing":
      return true;
    case "any":
    case "all":
      return (search.entities ?? []).length > 0;
    case "match":
      return !!search.node?.type;
    default:
      return !isBlankValue(search.value);
  }
}

/**
 * One field of the form: its condition (a toggle for not, the operator, what it is compared with), and any more on the
 * same field, each of which must hold too
 */
function ConditionRow(props: {
  type: string;
  field: SearchField;
  name: string;
  path: Accessor<Path>;
  /** The field is of the node the search is of (not of what a relation points at) */
  root?: boolean;
}) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t } = useTranslations();
  const search = () => form.get(props.path()) as FieldSearch | undefined;
  const more = () => search()?.and ?? [];
  const active = () => isActive(search()) || more().some(isActive);
  return (
    <SearchRow name={props.name} active={active()}>
      <ConditionLine
        type={props.type}
        field={props.field}
        name={props.name}
        path={props.path}
        node={() => props.path().slice(0, -2)}
        root={props.root}
        onRemove={() => form.remove(props.path())}
      />
      <For each={more()}>
        {(_, index) => (
          <>
            <span class="text-xs font-semibold text-slate-500 uppercase select-none">{t("search_and", "and")}</span>
            <ConditionLine
              type={props.type}
              field={props.field}
              name={props.name}
              path={() => [...props.path(), "and", index()]}
              node={() => props.path().slice(0, -2)}
              root={props.root}
              onRemove={() => form.remove([...props.path(), "and", index()])}
            />
          </>
        )}
      </For>
      <Show when={search()}>
        <button
          type="button"
          class={addConditionClass}
          aria-label={t("search_and_condition", "And another condition on {name}", { name: props.name })}
          title={t("search_and_condition", "And another condition on {name}", { name: props.name })}
          onClick={() => form.set([...props.path(), "and", more().length], { op: operatorsOf(definitions, props.field)[0]! })}
        >
          + {t("search_and", "and")}
        </button>
      </Show>
    </SearchRow>
  );
}

/** One condition on a field: the toggle for not, its operator, what it is compared with, and (a relation) the wrappers it passes through */
function ConditionLine(props: {
  type: string;
  field: SearchField;
  name: string;
  path: Accessor<Path>;
  /** Where the node the field is of is in the form */
  node: Accessor<Path>;
  root?: boolean;
  onRemove: () => void;
}) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t } = useTranslations();
  const ops = createMemo(() => operatorsOf(definitions, props.field));
  const wrappers = createMemo(() =>
    props.field.operators === "relation" ? wrappersOf(definitions, props.type, props.field.name) : [],
  );
  const search = () => form.get(props.path()) as FieldSearch | undefined;
  const op = () => search()?.op ?? ops()[0]!;
  // (of the types the field can point at, those there are, in the nodes that fit the rest of the node's form)
  const found = useFoundTypes(() =>
    op() === "match" && (props.field.targets ?? []).length > 1
      ? {
          type: props.type,
          field: props.field.name,
          where: whereWithout(form.get(props.node()) as NodeSearch | undefined, props.field.name),
          parts: !props.root,
        }
      : undefined,
  );
  const targets = createMemo(() => foundTargets(definitions, props.field.targets ?? [], found()));
  // (a condition is written when something is first put in it, with the operator on show)
  const write = (key: keyof FieldSearch, value: unknown) => {
    if (search()) form.set([...props.path(), key], value);
    else form.set(props.path(), { op: op(), [key]: value });
  };
  const chooseOp = (next: SearchOperator) => {
    const before = search();
    const chosen: FieldSearch = { op: next };
    if (before?.not) chosen.not = true;
    if (before?.through) chosen.through = before.through;
    if (before?.and) chosen.and = before.and;
    const value = carried(before, next);
    if (value !== undefined) chosen.value = value;
    if ((next === "any" || next === "all") && before?.entities) chosen.entities = before.entities;
    if (next === "match") {
      const targets = props.field.targets ?? [];
      if (before?.node) chosen.node = before.node;
      else if (targets.length === 1) chosen.node = { type: targets[0]! };
    }
    form.set(props.path(), chosen);
  };
  return (
    <div class="flex w-full min-w-0 flex-col items-start gap-3">
      <div class="flex w-full min-w-0 items-start gap-2">
        <NotToggle name={props.name} pressed={!!search()?.not} onToggle={() => write("not", !search()?.not)} />
        <OperatorSelect
          name={props.name}
          operators={props.field.operators}
          ops={ops()}
          value={op()}
          onChoose={chooseOp}
        />
        <div class="flex min-w-0 flex-1 flex-col items-start gap-3">
          <ConditionValue
            field={props.field}
            targets={targets()}
            counts={found()}
            name={props.name}
            op={op()}
            search={search()}
            write={write}
            path={props.path}
          />
        </div>
        <Show when={search()}>
          <button
            type="button"
            class={removeConditionClass}
            aria-label={t("search_remove_condition", "Remove the condition on {name}", { name: props.name })}
            title={t("search_remove_condition", "Remove the condition on {name}", { name: props.name })}
            onClick={() => props.onRemove()}
          >
            <RemoveIcon />
          </button>
        </Show>
      </div>
      <Show when={wrappers().length > 0 && op() !== "missing"}>
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs font-semibold text-slate-500 uppercase select-none">{t("search_through", "through")}</span>
          <ChoiceSet
            type={{ type: "str" }}
            label={t("search_through_named", "Through, for {name}", { name: props.name })}
            choices={wrappers()}
            value={search()?.through ?? []}
            onChange={(through) => write("through", through)}
          />
        </div>
      </Show>
      <Show when={op() === "match" && search()?.node?.type}>
        <NestedNode
          type={search()!.node!.type}
          targets={targets()}
          counts={found()}
          path={() => [...props.path(), "node"]}
          onRetype={(type) => form.set([...props.path(), "node"], { type })}
        />
      </Show>
    </div>
  );
}

/** What a condition is compared with, by its operator */
function ConditionValue(props: {
  field: SearchField;
  /** The types the field can point at that there are (all of them, until that is known) */
  targets: string[];
  counts?: Record<string, number>;
  name: string;
  op: SearchOperator;
  search: FieldSearch | undefined;
  write: (key: keyof FieldSearch, value: unknown) => void;
  path: Accessor<Path>;
}) {
  const definitions = useModels();
  const { t } = useTranslations();
  const range = () => (Array.isArray(props.search?.value) ? (props.search!.value as unknown[]) : ["", ""]);
  const groups = createMemo(() => searchableGroups(definitions, props.targets));
  return (
    <Switch>
      <Match when={props.op === "exists" || props.op === "missing"}>{null}</Match>
      <Match when={props.op === "between"}>
        <div class="flex flex-wrap items-center gap-2">
          <ValueInput
            type={props.field.value!}
            label={`${props.name} ${t("search_from", "from")}`}
            value={range()[0]}
            onInput={(value) => props.write("value", [value, range()[1] ?? ""])}
          />
          <span class="text-xs font-semibold text-slate-500 uppercase select-none">{t("search_and", "and")}</span>
          <ValueInput
            type={props.field.value!}
            label={`${props.name} ${t("search_to", "to")}`}
            value={range()[1]}
            onInput={(value) => props.write("value", [range()[0] ?? "", value])}
          />
        </div>
      </Match>
      <Match when={props.op === "in"}>
        <ChoiceSet
          type={props.field.value!}
          label={props.name}
          value={Array.isArray(props.search?.value) ? (props.search!.value as unknown[]) : []}
          onChange={(values) => props.write("value", values)}
        />
      </Match>
      <Match when={props.op === "any" || props.op === "all"}>
        <EntityChoice
          types={props.field.targets ?? []}
          entities={props.search?.entities ?? []}
          onChange={(entities) => props.write("entities", entities)}
        />
      </Match>
      <Match when={props.op === "match" && !props.search?.node?.type && props.targets.length === 0}>
        <span class="py-1.5 text-sm text-slate-500 italic">{t("search_none_found", "There are none")}</span>
      </Match>
      <Match when={props.op === "match" && !props.search?.node?.type}>
        <TypeMenu
          groups={groups()}
          counts={props.counts}
          label={t("search_choose_type", "Choose a type")}
          onChoose={(choice) => props.write("node", { type: choice.type })}
        />
      </Match>
      <Match when={props.op === "match"}>{null}</Match>
      <Match when={props.field.value}>
        <ValueInput
          type={props.field.value!}
          label={props.name}
          value={props.search?.value}
          onInput={(value) => props.write("value", value)}
        />
      </Match>
    </Switch>
  );
}

/**
 * The types the relation of a node points at, with how many of the nodes point at one (`searchFieldTypes`), asked again
 * a moment after what it depends on changes; `undefined` until it is known, or if it cannot be (then every type is offered).
 * In the browser only: an effect.
 */
function useFoundTypes(
  query: () => { type: string; field: string; where: Record<string, unknown>; parts: boolean } | undefined,
): Accessor<Record<string, number> | undefined> {
  const client = useApi();
  const [found, setFound] = createSignal<Record<string, number> | undefined>(undefined);
  let asked = 0;
  createEffect(
    () => {
      const given = query();
      return given ? JSON.stringify(given) : "";
    },
    (key) => {
      const at = ++asked;
      if (!key) return;
      const timer = setTimeout(() => {
        searchFieldTypes(client, JSON.parse(key)).then(
          (types) => {
            if (at === asked) setFound(types);
          },
          () => {
            if (at === asked) setFound(undefined);
          },
        );
      }, DEBOUNCE_MS);
      return () => clearTimeout(timer);
    },
  );
  return found;
}

/** The types to choose from for a pattern: those of the targets, with their parents, any that can be searched (a parent finds its subclasses) */
function searchableGroups(definitions: ModelDefinitions, targets: string[]): MenuGroup[] {
  const options: RelationOption[] = targets.map((type) => ({
    kind: getModel(definitions, type)?.kind === "Entity" ? "entity" : "document",
    type,
    edgeModel: null,
  }));
  return menuGroups(definitions, options).map((group) => ({
    ...group,
    columns: group.columns.map((column) =>
      column.map((row) => ({ ...row, selectable: row.selectable || !!definitions.searchPatterns?.[row.name] })),
    ),
  }));
}

/** A box for one value of a literal type (a number is a number; what is not typed is "") */
function ValueInput(props: { type: FieldType; label: string; value: unknown; onInput: (value: unknown) => void }) {
  const definitions = useModels();
  const { t, memberName } = useTranslations();
  const text = () => (props.value === undefined || props.value === null ? "" : String(props.value));
  const members = () =>
    props.type.type === "enum" ? (definitions.enums[props.type.enum]?.members ?? []) : [];
  return (
    <Switch
      fallback={
        <input
          type="text"
          class={boxClass}
          aria-label={props.label}
          value={text()}
          onInput={(event) => props.onInput(event.currentTarget.value)}
        />
      }
    >
      <Match when={props.type.type === "int" || props.type.type === "float"}>
        <NumberInput
          class={["h-8 w-full", numberWidthClass].join(" ")}
          label={props.label}
          step={props.type.type === "int" ? 1 : "any"}
          value={text()}
          onInput={(typed) => props.onInput(typed === "" ? "" : Number(typed))}
        />
      </Match>
      <Match when={props.type.type === "decimal"}>
        <input
          type="text"
          class={[boxClass, numberWidthClass]}
          aria-label={props.label}
          inputmode="decimal"
          onBeforeInput={allowOnly(decimalCharacters)}
          value={text()}
          onInput={(event) => props.onInput(event.currentTarget.value)}
        />
      </Match>
      <Match when={props.type.type === "date"}>
        <input
          type="date"
          class={[boxClass, dateWidthClass]}
          aria-label={props.label}
          value={text()}
          onInput={(event) => props.onInput(event.currentTarget.value)}
        />
      </Match>
      <Match when={props.type.type === "datetime"}>
        <input
          type="datetime-local"
          class={[boxClass, dateTimeWidthClass]}
          aria-label={props.label}
          value={text().slice(0, 16)}
          onInput={(event) => props.onInput(event.currentTarget.value)}
        />
      </Match>
      <Match when={props.type.type === "bool"}>
        <MenuSelect
          class={numberWidthClass}
          label={props.label}
          value={text()}
          options={[
            { value: "true", label: t("yes", "Yes") },
            { value: "false", label: t("no", "No") },
          ]}
          onChoose={(chosen) => props.onInput(chosen === "true")}
        />
      </Match>
      <Match when={props.type.type === "enum"}>
        <MenuSelect
          class="w-fit min-w-36"
          label={props.label}
          value={text()}
          options={members().map((member) => ({
            value: String(member.value),
            label: memberName((props.type as Extract<FieldType, { type: "enum" }>).enum, member.name),
          }))}
          onChoose={(chosen) => {
            const found = members().find((member) => String(member.value) === chosen);
            props.onInput(found ? found.value : "");
          }}
        />
      </Match>
    </Switch>
  );
}

/** The values of an enum (or yes and no) as pills, any number of them chosen: what is one of them is found */
function ChoiceSet(props: {
  type: FieldType;
  label: string;
  value: unknown[];
  onChange: (values: unknown[]) => void;
  /** Names of models to choose from, instead of the values of the type */
  choices?: string[];
}) {
  const definitions = useModels();
  const { t, memberName, modelName } = useTranslations();
  const options = (): { value: unknown; name: string }[] => {
    if (props.choices) return props.choices.map((name) => ({ value: name, name: modelName(name) }));
    if (props.type.type === "bool")
      return [
        { value: true, name: t("yes", "Yes") },
        { value: false, name: t("no", "No") },
      ];
    if (props.type.type === "enum") {
      const name = props.type.enum;
      return (definitions.enums[name]?.members ?? []).map((member) => ({
        value: member.value,
        name: memberName(name, member.name),
      }));
    }
    return [];
  };
  return (
    <div role="group" aria-label={props.label} class={segmentedClass}>
      <For each={options()}>
        {(option) => {
          const chosen = () => props.value.includes(option.value);
          return (
            <button
              type="button"
              aria-pressed={chosen() ? "true" : "false"}
              class={segmentClass(chosen(), true)}
              onClick={() =>
                props.onChange(
                  chosen() ? props.value.filter((value) => value !== option.value) : [...props.value, option.value],
                )
              }
            >
              {option.name}
            </button>
          );
        }}
      </For>
    </div>
  );
}

/** Entities picked, as chips that can be taken out, and the search to pick more */
function EntityChoice(props: {
  types: string[];
  entities: PickedEntity[];
  onChange: (entities: PickedEntity[]) => void;
  placeholder?: string;
}) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  return (
    <div class="flex w-full min-w-0 flex-col gap-2">
      <Show when={props.entities.length > 0}>
        <div class="flex w-full min-w-0 flex-wrap items-start gap-2">
          <For each={props.entities}>
            {(entity) => (
              <ReferenceChip
                type={entity.type}
                label={entity.label}
                onRemove={() => props.onChange(props.entities.filter((other) => other.id !== entity.id))}
                removeLabel={t("remove_item", "Remove {name}", { name: entity.label })}
              />
            )}
          </For>
        </div>
      </Show>
      <EntityPicker
        types={props.types}
        placeholder={props.placeholder}
        onPick={(entity) => {
          if (props.entities.some((other) => other.id === entity.id)) return;
          props.onChange([...props.entities, { type: entity.type, id: entity.id, label: entity.label }]);
        }}
      />
    </div>
  );
}

/**
 * The form for what a field points at, in a box headed by its type as a nested document is in the entry form: the
 * type a chip (a menu to change it, if the field can point at more than one), then its own rows, indented, with a rule
 * in the colour of the type
 */
function NestedNode(props: {
  type: string;
  targets: string[];
  counts?: Record<string, number>;
  path: Accessor<Path>;
  onRetype: (type: string) => void;
}) {
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const model = () => getModel(definitions, props.type);
  const groups = createMemo(() => searchableGroups(definitions, props.targets));
  const several = () => groups().reduce((count, group) => count + group.columns.flat().filter((row) => row.selectable).length, 0) > 1;
  return (
    <NestedBox
      type={props.type}
      tint={kindTint(model()?.kind, model()?.interfaceMeta?.colour)}
      rule={kindRule(model()?.kind, model()?.interfaceMeta?.colour)}
      buttons={
        <Show when={several()}>
          <TypeMenu
            groups={groups()}
            counts={props.counts}
            label={t("search_change_type", "Type")}
            title={t("search_change_type_of", "Change the type of {name}", { name: modelName(props.type) })}
            buttonClass={[headMenuButtonClass, "text-slate-500 hover:bg-slate-400/30"].join(" ")}
            alignRight
            onChoose={(choice) => props.onRetype(choice.type)}
          />
        </Show>
      }
    >
      <NodeFields type={props.type} path={props.path} />
    </NestedBox>
  );
}

/** The head bar and indented body of something nested in the form */
function NestedBox(
  props: ParentProps<{
    type: string;
    label?: string;
    tint: string;
    rule: string;
    buttons?: JSX.Element;
  }>,
) {
  const { t, modelName } = useTranslations();
  const [folded, setFolded] = createSignal(false);
  return (
    <div class="flex w-full min-w-0 flex-col" data-search-node={props.type}>
      <div class={headBarClass}>
        <span data-type-info={props.type} data-tint class={[typeChipClass, props.tint || plainTint, props.rule]}>
          {modelName(props.type)}
        </span>
        <div class={headRestOpenClass}>
          <span class={headLabelClass}>{props.label}</span>
          {props.buttons}
          <button
            type="button"
            class={[headButtonClass, "text-slate-500 hover:bg-slate-400/30"]}
            aria-expanded={folded() ? "false" : "true"}
            aria-label={t("fold", "Fold or unfold {name}", { name: modelName(props.type) })}
            onClick={() => setFolded(!folded())}
          >
            <Show when={folded()} fallback="▾">
              ▸
            </Show>
          </button>
        </div>
      </div>
      <Show when={!folded()}>
        <div class={["ml-2 pt-4", nestedClass, props.rule]}>{props.children}</div>
      </Show>
    </div>
  );
}

/** Documents: entities that appear anywhere in the document (any of them, or all) */
function MentionsRow(props: { path: Accessor<Path> }) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t } = useTranslations();
  const name = () => t("search_mentions", "Mentions");
  const search = () => form.get(props.path()) as FieldSearch | undefined;
  const op = () => search()?.op ?? "any";
  const write = (key: keyof FieldSearch, value: unknown) => {
    if (search()) form.set([...props.path(), key], value);
    else form.set(props.path(), { op: op(), [key]: value });
  };
  // (any entity: those that are not abstract, as the autocomplete looks them up)
  const entityTypes = createMemo(() =>
    Object.entries(definitions.searchPatterns ?? {})
      .filter(([type, pattern]) => pattern.kind === "entity" && !getModel(definitions, type)?.abstract)
      .map(([type]) => type),
  );
  return (
    <SearchRow name={name()} active={isActive(search())}>
      <div class="flex w-full min-w-0 items-start gap-2">
        <NotToggle name={name()} pressed={!!search()?.not} onToggle={() => write("not", !search()?.not)} />
        <OperatorSelect
          name={name()}
          operators="mentions"
          ops={["any", "all"]}
          value={op()}
          onChoose={(next) => write("op", next)}
        />
        <div class="flex min-w-0 flex-1 flex-col items-start gap-3">
          <EntityChoice
            types={entityTypes()}
            placeholder={t("search_find_any_entity", "Find an entity…")}
            entities={search()?.entities ?? []}
            onChange={(entities) => write("entities", entities)}
          />
        </div>
        <Show when={search()}>
          <button
            type="button"
            class={removeConditionClass}
            aria-label={t("search_remove_condition", "Remove the condition on {name}", { name: name() })}
            onClick={() => form.remove(props.path())}
          >
            <RemoveIcon />
          </button>
        </Show>
      </div>
    </SearchRow>
  );
}

/** Entities: what refers to them, each a type and its relation, with a form of its own for what that is */
function IncomingRow(props: { type: string; path: Accessor<Path>; onRemove: () => void }) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t, modelName, fieldName } = useTranslations();
  const name = () => t("search_referred_to_by", "Referred to by");
  const sources = createMemo(() => incomingSourcesOf(definitions, props.type));
  const entries = () => (form.get(props.path()) as IncomingSearch[] | undefined) ?? [];
  const sourceName = (source: { model: string; field: string }) =>
    t("search_source", "{type} · {field}", {
      type: modelName(source.model),
      field: fieldName(source.model, source.field),
    });
  return (
    <SearchRow name={name()} active={entries().length > 0} onRemove={entries().length === 0 ? props.onRemove : undefined}>
      <Show when={entries().length > 0}>
        <div class="flex w-full min-w-0 flex-col gap-4">
          <For each={entries()}>
            {(entry, index) => {
              const at = () => [...props.path(), index()];
              const model = () => getModel(definitions, entry.node.type);
              const label = () =>
                entry.field ? fieldName(entry.node.type, entry.field) : t("search_any_field", "any field");
              return (
                <NestedBox
                  type={entry.node.type}
                  label={label()}
                  tint={kindTint(model()?.kind, model()?.interfaceMeta?.colour)}
                  rule={kindRule(model()?.kind, model()?.interfaceMeta?.colour)}
                  buttons={
                    <>
                      <button
                        type="button"
                        aria-pressed={entry.not ? "true" : "false"}
                        aria-label={t("search_not_named", "Not: {name}", { name: sourceName({ model: entry.node.type, field: entry.field ?? "" }) })}
                        title={t("search_not_title", "Find what does not match this")}
                        class={[
                          headMenuButtonClass,
                          "font-semibold uppercase",
                          { "bg-red-800 text-white hover:bg-red-700": !!entry.not },
                          { "text-slate-500 hover:bg-slate-400/30": !entry.not },
                        ]}
                        onClick={() => form.set([...at(), "not"], !entry.not)}
                      >
                        {t("search_not", "not")}
                      </button>
                      <button
                        type="button"
                        class={[headButtonClass, "text-red-800 hover:bg-red-400/30"]}
                        aria-label={t("remove_item", "Remove {name}", { name: modelName(entry.node.type) })}
                        onClick={() => removeEntry(form, props.path(), index(), entries().length)}
                      >
                        ✕
                      </button>
                    </>
                  }
                >
                  <NodeFields type={entry.node.type} path={() => [...at(), "node"]} />
                </NestedBox>
              );
            }}
          </For>
        </div>
      </Show>
      <MenuSelect
        look="add"
        label={t("search_add_referring", "Add what refers to it")}
        placeholder={t("search_add_referring", "Add what refers to it")}
        options={sources().map((source, index) => ({
          value: String(index),
          type: source.model,
          label: fieldName(source.model, source.field),
        }))}
        onChoose={(chosen) => {
          const source = sources()[Number(chosen)];
          if (source) form.set([...props.path(), entries().length], { field: source.field, node: { type: source.model } });
        }}
      />
    </SearchRow>
  );
}

/** The buttons of a thing added to a row (a document it contains, an alternative): not, and remove */
function EntryButtons(props: { name: string; not?: boolean; onNot?: () => void; onRemove: () => void }) {
  const { t } = useTranslations();
  return (
    <>
      <Show when={props.onNot}>
        <button
          type="button"
          aria-pressed={props.not ? "true" : "false"}
          aria-label={t("search_not_named", "Not: {name}", { name: props.name })}
          title={t("search_not_title", "Find what does not match this")}
          class={[
            headMenuButtonClass,
            "font-semibold uppercase",
            { "bg-red-800 text-white hover:bg-red-700": !!props.not },
            { "text-slate-500 hover:bg-slate-400/30": !props.not },
          ]}
          onClick={() => props.onNot?.()}
        >
          {t("search_not", "not")}
        </button>
      </Show>
      <button
        type="button"
        class={[headButtonClass, "text-red-800 hover:bg-red-400/30"]}
        aria-label={t("remove_item", "Remove {name}", { name: props.name })}
        onClick={() => props.onRemove()}
      >
        ✕
      </button>
    </>
  );
}

/** A menu that adds something to a row: the dashed button of what it adds */
function AddSelect(props: { label: string; options: { value: string; name: string }[]; onChoose: (value: string) => void }) {
  return (
    <MenuSelect
      look="add"
      label={props.label}
      placeholder={props.label}
      options={props.options.map((option) => ({ value: option.value, label: option.name }))}
      onChoose={(value) => props.onChoose(value)}
    />
  );
}

/** Documents: documents of other types somewhere inside them (`$somewhere`), each with a form of its own */
function SomewhereRow(props: { path: Accessor<Path>; onRemove: () => void }) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const entries = () => (form.get(props.path()) as SomewhereSearch[] | undefined) ?? [];
  const typeGroups = createMemo(() => searchableGroups(definitions, documentTypesOf(definitions)));
  return (
    <SearchRow
      name={t("search_somewhere", "Contains")}
      active={entries().length > 0}
      onRemove={entries().length === 0 ? props.onRemove : undefined}
    >
      <Show when={entries().length > 0}>
        <div class="flex w-full min-w-0 flex-col gap-4">
          <For each={entries()}>
            {(entry, index) => {
              const at = () => [...props.path(), index()];
              const model = () => getModel(definitions, entry.node.type);
              return (
                <NestedBox
                  type={entry.node.type}
                  tint={kindTint(model()?.kind, model()?.interfaceMeta?.colour)}
                  rule={kindRule(model()?.kind, model()?.interfaceMeta?.colour)}
                  buttons={
                    <EntryButtons
                      name={modelName(entry.node.type)}
                      not={entry.not}
                      onNot={() => form.set([...at(), "not"], !entry.not)}
                      onRemove={() => removeEntry(form, props.path(), index(), entries().length)}
                    />
                  }
                >
                  <NodeFields type={entry.node.type} path={() => [...at(), "node"]} />
                </NestedBox>
              );
            }}
          </For>
        </div>
      </Show>
      {/* (types are chosen as everywhere: by the hierarchy, in the menu of types) */}
      <TypeMenu
        groups={typeGroups()}
        label={`+ ${t("search_add_somewhere", "Add a document it contains")}`}
        title={t("search_add_somewhere", "Add a document it contains")}
        buttonClass={addConditionClass}
        onChoose={(choice) => form.set([...props.path(), entries().length], { node: { type: choice.type } })}
      />
    </SearchRow>
  );
}

/** A document that a relation points at: the semantic spaces it is inside, all of them (`$spaces`) */
function SpacesRow(props: { path: Accessor<Path>; onRemove: () => void }) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t } = useTranslations();
  const name = () => t("search_in_spaces", "Inside");
  const chosen = () => (form.get(props.path()) as string[] | undefined) ?? [];
  return (
    <SearchRow name={name()} active={chosen().length > 0} onRemove={props.onRemove}>
      <ChoiceSet
        type={{ type: "str" }}
        label={name()}
        choices={semanticSpacesOf(definitions)}
        value={chosen()}
        onChange={(spaces) => form.set(props.path(), spaces)}
      />
    </SearchRow>
  );
}

/**
 * Groups of alternatives (`$any_of`): of each group at least one has to hold. Each alternative is a form of the same
 * type, in a box of its own, with "or" between them.
 */
function AnyOfRow(props: { type: string; path: Accessor<Path>; root?: boolean; onRemove: () => void }) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const groups = () => (form.get(props.path()) as NodeSearch[][] | undefined) ?? [];
  const model = () => getModel(definitions, props.type);
  return (
    <SearchRow
      name={t("search_any_of", "Any of")}
      active={groups().length > 0}
      onRemove={groups().length === 0 ? props.onRemove : undefined}
    >
      <For each={groups()}>
        {(group, g) => (
          <div
            role="group"
            aria-label={t("search_alternatives_n", "Alternatives {n}", { n: g() + 1 })}
            class="flex w-full min-w-0 flex-col items-start gap-3 rounded-xs border-[0.5px] border-dashed border-slate-400/80 p-3"
          >
            <For each={group}>
              {(_, a) => (
                <>
                  <Show when={a() > 0}>
                    <span class="text-xs font-semibold text-slate-500 uppercase select-none">{t("search_or", "or")}</span>
                  </Show>
                  <NestedBox
                    type={props.type}
                    label={t("search_alternative", "alternative {n}", { n: a() + 1 })}
                    tint={kindTint(model()?.kind, model()?.interfaceMeta?.colour)}
                    rule={kindRule(model()?.kind, model()?.interfaceMeta?.colour)}
                    buttons={
                      <EntryButtons
                        name={`${modelName(props.type)} ${t("search_alternative", "alternative {n}", { n: a() + 1 })}`}
                        onRemove={() =>
                          group.length <= 1
                            ? removeEntry(form, props.path(), g(), groups().length)
                            : form.remove([...props.path(), g(), a()])
                        }
                      />
                    }
                  >
                    <NodeFields type={props.type} path={() => [...props.path(), g(), a()]} root={props.root} alternative />
                  </NestedBox>
                </>
              )}
            </For>
            <button
              type="button"
              class={addConditionClass}
              onClick={() => form.set([...props.path(), g(), group.length], { type: props.type })}
            >
              + {t("search_or", "or")}
            </button>
          </div>
        )}
      </For>
      <button
        type="button"
        class={addConditionClass}
        onClick={() => form.set([...props.path(), groups().length], [{ type: props.type }, { type: props.type }])}
      >
        + {t("search_add_alternatives", "Add alternatives")}
      </button>
    </SearchRow>
  );
}

// (how many fields a search can be ordered by, as the API takes)
const MAX_ORDER = 3;

/** The root: what the results are ordered by, a field after another, each up or down */
function OrderRow(props: { type: string; path: Accessor<Path>; onRemove: () => void }) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t, fieldName } = useTranslations();
  const entries = () => (form.get(props.path()) as OrderSearch[] | undefined) ?? [];
  const fields = createMemo(() => orderFieldsOf(definitions, props.type));
  // (`date.sort_day`: the field, then the field of the embedded object in it)
  const nameOf = (field: string) =>
    field
      .split(".")
      .map((part, at) => (part === "label" && at === 0 ? t("label", "Label") : fieldName(at === 0 ? props.type : "", part)))
      .join(" › ");
  const name = () => t("search_order_by", "Order by");
  return (
    <SearchRow name={name()} active={entries().length > 0} onRemove={entries().length === 0 ? props.onRemove : undefined}>
      <For each={entries()}>
        {(entry, index) => (
          <div class="flex w-full min-w-0 items-center gap-2">
            <Show when={index() > 0}>
              <span class="self-center text-xs font-semibold text-slate-500 uppercase select-none">
                {t("search_then_by", "then by")}
              </span>
            </Show>
            <MenuSelect
              class="w-48 shrink-0"
              label={t("search_order_n", "Order by, {n}", { n: index() + 1 })}
              value={entry.field}
              options={fields().map((field) => ({ value: field, label: nameOf(field) }))}
              onChoose={(field) => form.set([...props.path(), index(), "field"], field)}
            />
            <MenuSelect
              class="w-36 shrink-0"
              label={t("search_direction", "Direction of {name}", { name: nameOf(entry.field) })}
              value={entry.direction ?? "asc"}
              options={[
                { value: "asc", label: t("search_ascending", "ascending") },
                { value: "desc", label: t("search_descending", "descending") },
              ]}
              onChoose={(direction) => form.set([...props.path(), index(), "direction"], direction)}
            />
            <button
              type="button"
              class={removeConditionClass}
              aria-label={t("remove_item", "Remove {name}", { name: nameOf(entry.field) })}
              title={t("remove_item", "Remove {name}", { name: nameOf(entry.field) })}
              onClick={() => removeEntry(form, props.path(), index(), entries().length)}
            >
            <RemoveIcon />
          </button>
          </div>
        )}
      </For>
      <Show when={entries().length < MAX_ORDER}>
        <AddSelect
          label={entries().length > 0 ? t("search_then_by", "then by") : t("search_order_by", "Order by")}
          options={fields()
            .filter((field) => !entries().some((entry) => entry.field === field))
            .map((field) => ({ value: field, name: nameOf(field) }))}
          onChoose={(field) => form.set([...props.path(), entries().length], { field, direction: "asc" })}
        />
      </Show>
    </SearchRow>
  );
}

/**
 * The searches saved in this browser for the type (local storage): a menu to load one (which replaces what is in the
 * form) and a button to delete it; Save asks for a name, and saves what is in the form under it
 */
function SavedSearches(props: { type: string; current: () => NodeSearch; onLoad: (form: NodeSearch) => void }) {
  const { t } = useTranslations();
  const [all, setAll] = createSignal<SavedSearch[]>([]);
  const [chosen, setChosen] = createSignal("");
  const [naming, setNaming] = createSignal(false);
  const [name, setName] = createSignal("");
  let nameBox: HTMLInputElement | undefined;
  // (in the browser only: they are in its storage)
  onSettled(() => {
    setAll(savedSearches(props.type));
  });
  const save = () => {
    const given = name().trim();
    if (!given) return;
    setAll(saveSearch(props.type, given, props.current()));
    setChosen(given);
    setNaming(false);
  };
  return (
    <div class="mr-auto flex min-w-0 items-center gap-2">
      <Show when={all().length > 0}>
        <MenuSelect
          look="small"
          class="w-48"
          label={t("search_saved", "Saved searches")}
          placeholder={t("search_saved_placeholder", "Saved searches…")}
          value={chosen()}
          options={all().map((each) => ({ value: each.name, label: each.name }))}
          onChoose={(picked) => {
            const found = all().find((each) => each.name === picked);
            setChosen(picked);
            if (found) props.onLoad(structuredClone(found.form));
          }}
        />
        <Show when={chosen()}>
          <button
            type="button"
            class={removeSmallClass}
            aria-label={t("search_delete_saved", "Delete the saved search {name}", { name: chosen() })}
            title={t("search_delete_saved", "Delete the saved search {name}", { name: chosen() })}
            onClick={() => {
              setAll(deleteSearch(props.type, chosen()));
              setChosen("");
            }}
          >
            <RemoveIcon />
          </button>
        </Show>
      </Show>
      <Show
        when={naming()}
        fallback={
          <button
            type="button"
            class={smallButtonClass}
            onClick={() => {
              setName(chosen());
              setNaming(true);
              // (the box drawn, then the cursor in it)
              flush();
              nameBox?.focus();
            }}
          >
            {t("search_save", "Save")}…
          </button>
        }
      >
        <input
          type="text"
          class={[inputClass, "h-6.5 w-48 py-0"]}
          aria-label={t("search_save_name", "Name of this search")}
          placeholder={t("search_save_name", "Name of this search")}
          value={name()}
          ref={nameBox}
          onInput={(event) => setName(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") save();
            if (event.key === "Escape") setNaming(false);
          }}
        />
        <button type="button" class={smallButtonClass} disabled={!name().trim()} onClick={save}>
          {t("search_save", "Save")}
        </button>
        <button type="button" class={smallButtonClass} onClick={() => setNaming(false)}>
          {t("cancel", "Cancel")}
        </button>
      </Show>
    </div>
  );
}

export default SearchPanel;
