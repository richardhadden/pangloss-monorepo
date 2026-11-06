import { createContext, createMemo, createSignal, flush, For, Match, onCleanup, onSettled, Show, Switch, untrack, useContext } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";
import type { JSX } from "@solidjs/web";
import { createItemFormState, useComponent, useModels, useTranslations } from "../../context";
import type { ItemFormState } from "../../context";
import { kindRule, kindTint } from "../../primitives";
import {
  getModel,
  documentTypesOf,
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

// (a box as wide as what it holds, such as the menu of the operators: the input's look without its whole width)
const compactClass = `${inputClass.replace("w-full ", "")} w-auto shrink-0`;

// (the button that adds another condition on the same field: quiet, under what is there)
const addConditionClass =
  "inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-xs border-[0.5px] border-dashed border-slate-400/80 px-2 py-0.5 text-xs font-semibold text-slate-500 uppercase select-none hover:border-slate-600 hover:bg-slate-100/60 hover:text-slate-800";

// (the button that takes a condition out: as tall as the boxes of the row, however tall the row grows)
const removeConditionClass =
  "inline-flex shrink-0 cursor-pointer items-center self-start rounded-xs border-[0.5px] border-slate-400/70 bg-slate-100/60 px-2 py-1.5 text-xs leading-5 text-red-800 select-none hover:bg-red-400/30";

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
  // (what is in it can only be clipped while it slides: a menu or a list of matches opens over its edge)
  const [settled, setSettled] = createSignal(untrack(() => props.open));
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
          // (its own, not those of what is in it, which bubble up)
          onTransitionStart={(event) => {
            if (event.target === event.currentTarget) setSettled(false);
          }}
          onTransitionEnd={(event) => {
            if (event.target === event.currentTarget) setSettled(props.open);
          }}
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

/** The rows of the form for a node of `type` at `path`: its fields; mentions (a document at the root); what refers to it (an entity) */
function NodeFields(props: {
  type: string;
  path: Accessor<Path>;
  /** The node the search is of (not what a relation points at) */
  root?: boolean;
  /** One of a group of alternatives: it has no groups of its own, nor an order */
  alternative?: boolean;
}) {
  const definitions = useModels();
  const { t, fieldName } = useTranslations();
  const fields = createMemo(() => searchFieldsOf(definitions, props.type));
  const kind = () => searchKindOf(definitions, props.type);
  const nameOf = (field: SearchField) =>
    field.name === "label" ? t("label", "Label") : fieldName(props.type, field.name);
  return (
    <dl class={fieldGridClass}>
      <For each={fields()}>
        {(field) => (
          <ConditionRow
            type={props.type}
            field={field}
            name={nameOf(field)}
            path={() => [...props.path(), "fields", field.name]}
          />
        )}
      </For>
      <Show when={props.root && kind() === "document"}>
        <MentionsRow path={() => [...props.path(), "mentions"]} />
      </Show>
      <Show when={kind() === "entity" && incomingSourcesOf(definitions, props.type).length > 0}>
        <IncomingRow type={props.type} path={() => [...props.path(), "incoming"]} />
      </Show>
      <Show when={props.root && kind() === "document"}>
        <SomewhereRow path={() => [...props.path(), "somewhere"]} />
      </Show>
      <Show when={!props.root && kind() === "document" && semanticSpacesOf(definitions).length > 0}>
        <SpacesRow path={() => [...props.path(), "spaces"]} />
      </Show>
      <Show when={!props.alternative}>
        <AnyOfRow type={props.type} path={() => [...props.path(), "anyOf"]} root={props.root} />
      </Show>
      <Show when={props.root && !props.alternative && orderFieldsOf(definitions, props.type).length > 0}>
        <OrderRow type={props.type} path={() => [...props.path(), "order"]} />
      </Show>
    </dl>
  );
}

/** A row of the form, as the entry form has them: the name on the left (darker while it has a condition), then what it is */
function SearchRow(props: ParentProps<{ name: string; active: boolean }>) {
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
      <dd class="flex min-w-0 flex-col items-start gap-3">{props.children}</dd>
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
      class={[
        "shrink-0 cursor-pointer self-start rounded-xs border-[0.5px] px-2 py-1.5 text-xs leading-5 font-semibold uppercase select-none",
        { "border-red-800 bg-red-800 text-white hover:bg-red-700": props.pressed },
        { "border-slate-400/70 bg-white/80 text-slate-500 hover:bg-slate-200/70": !props.pressed },
      ]}
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
    <select
      // (as wide in every row, so that what each is compared with starts at the same place)
      class={[compactClass, "min-w-36"]}
      aria-label={t("search_operator", "Condition on {name}", { name: props.name })}
      value={props.value}
      onChange={(event) => props.onChoose(event.currentTarget.value as SearchOperator)}
    >
      <For each={props.ops}>
        {(op) => (
          <option value={op} selected={props.value === op}>
            {operatorName(props.operators, op)}
          </option>
        )}
      </For>
    </select>
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
function ConditionRow(props: { type: string; field: SearchField; name: string; path: Accessor<Path> }) {
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
            ✕
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
          targets={props.field.targets ?? []}
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
  name: string;
  op: SearchOperator;
  search: FieldSearch | undefined;
  write: (key: keyof FieldSearch, value: unknown) => void;
  path: Accessor<Path>;
}) {
  const definitions = useModels();
  const { t } = useTranslations();
  const range = () => (Array.isArray(props.search?.value) ? (props.search!.value as unknown[]) : ["", ""]);
  const groups = createMemo(() => searchableGroups(definitions, props.field.targets ?? []));
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
      <Match when={props.op === "match" && !props.search?.node?.type}>
        <TypeMenu
          groups={groups()}
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
          class={inputClass}
          aria-label={props.label}
          value={text()}
          onInput={(event) => props.onInput(event.currentTarget.value)}
        />
      }
    >
      <Match when={props.type.type === "int" || props.type.type === "float"}>
        <NumberInput
          class={["w-full", numberWidthClass].join(" ")}
          label={props.label}
          step={props.type.type === "int" ? 1 : "any"}
          value={text()}
          onInput={(typed) => props.onInput(typed === "" ? "" : Number(typed))}
        />
      </Match>
      <Match when={props.type.type === "decimal"}>
        <input
          type="text"
          class={[inputClass, numberWidthClass]}
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
          class={[inputClass, dateWidthClass]}
          aria-label={props.label}
          value={text()}
          onInput={(event) => props.onInput(event.currentTarget.value)}
        />
      </Match>
      <Match when={props.type.type === "datetime"}>
        <input
          type="datetime-local"
          class={[inputClass, dateTimeWidthClass]}
          aria-label={props.label}
          value={text().slice(0, 16)}
          onInput={(event) => props.onInput(event.currentTarget.value)}
        />
      </Match>
      <Match when={props.type.type === "bool"}>
        <select
          class={compactClass}
          aria-label={props.label}
          value={text()}
          onChange={(event) =>
            props.onInput(event.currentTarget.value === "" ? "" : event.currentTarget.value === "true")
          }
        >
          <option value="" />
          <option value="true" selected={props.value === true}>
            {t("yes", "Yes")}
          </option>
          <option value="false" selected={props.value === false}>
            {t("no", "No")}
          </option>
        </select>
      </Match>
      <Match when={props.type.type === "enum"}>
        <select
          class={compactClass}
          aria-label={props.label}
          value={text()}
          onChange={(event) => {
            const chosen = members().find((member) => String(member.value) === event.currentTarget.value);
            props.onInput(chosen ? chosen.value : "");
          }}
        >
          <option value="" />
          <For each={members()}>
            {(member) => (
              <option value={String(member.value)} selected={text() === String(member.value)}>
                {memberName((props.type as Extract<FieldType, { type: "enum" }>).enum, member.name)}
              </option>
            )}
          </For>
        </select>
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
    <div role="group" aria-label={props.label} class="flex flex-wrap gap-1.5">
      <For each={options()}>
        {(option) => {
          const chosen = () => props.value.includes(option.value);
          return (
            <button
              type="button"
              aria-pressed={chosen() ? "true" : "false"}
              class={[
                "cursor-pointer rounded-full border-[0.5px] px-3 py-1 text-sm select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400/60",
                { "border-slate-700 bg-slate-700 text-white hover:bg-slate-600": chosen() },
                { "border-slate-400/70 bg-white/80 text-slate-700 hover:bg-slate-200/70": !chosen() },
              ]}
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
function NestedNode(props: { type: string; targets: string[]; path: Accessor<Path>; onRetype: (type: string) => void }) {
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
        <span data-tint class={[typeChipClass, props.tint || plainTint, props.rule]}>
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
            ✕
          </button>
        </Show>
      </div>
    </SearchRow>
  );
}

/** Entities: what refers to them, each a type and its relation, with a form of its own for what that is */
function IncomingRow(props: { type: string; path: Accessor<Path> }) {
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
    <SearchRow name={name()} active={entries().length > 0}>
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
                        onClick={() => form.remove(at())}
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
      <select
        class={compactClass}
        aria-label={t("search_add_referring", "Add what refers to it")}
        onChange={(event) => {
          const chosen = sources()[Number(event.currentTarget.value)];
          event.currentTarget.value = "";
          if (!chosen) return;
          form.set([...props.path(), entries().length], { field: chosen.field, node: { type: chosen.model } });
        }}
      >
        <option value="" textContent={`+ ${t("search_add_referring", "Add what refers to it")}`} />
        <For each={sources()}>
          {(source, index) => <option value={String(index())}>{sourceName(source)}</option>}
        </For>
      </select>
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

/** A menu that adds something to a row: it says what it adds, and goes back to that once it has */
function AddSelect(props: { label: string; options: { value: string; name: string }[]; onChoose: (value: string) => void }) {
  return (
    <select
      class={compactClass}
      aria-label={props.label}
      onChange={(event) => {
        const chosen = event.currentTarget.value;
        event.currentTarget.value = "";
        if (chosen) props.onChoose(chosen);
      }}
    >
      {/* (the text as a property, not a child: a child that is an expression, in an option that others follow,
          is counted by the browser and not by the server, and the options after it were not taken over) */}
      <option value="" textContent={`+ ${props.label}`} />
      {/* (by their values: the options are made anew each time one is chosen, and each would be a new row) */}
      <For each={props.options} keyed={(option) => option.value}>
        {(option) => <option value={option().value}>{option().name}</option>}
      </For>
    </select>
  );
}

/** Documents: documents of other types somewhere inside them (`$somewhere`), each with a form of its own */
function SomewhereRow(props: { path: Accessor<Path> }) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const entries = () => (form.get(props.path()) as SomewhereSearch[] | undefined) ?? [];
  const types = createMemo(() => documentTypesOf(definitions));
  return (
    <SearchRow name={t("search_somewhere", "Contains")} active={entries().length > 0}>
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
                      onRemove={() => form.remove(at())}
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
      <AddSelect
        label={t("search_add_somewhere", "Add a document it contains")}
        options={types().map((type) => ({ value: type, name: modelName(type) }))}
        onChoose={(type) => form.set([...props.path(), entries().length], { node: { type } })}
      />
    </SearchRow>
  );
}

/** A document that a relation points at: the semantic spaces it is inside, all of them (`$spaces`) */
function SpacesRow(props: { path: Accessor<Path> }) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t } = useTranslations();
  const name = () => t("search_in_spaces", "Inside");
  const chosen = () => (form.get(props.path()) as string[] | undefined) ?? [];
  return (
    <SearchRow name={name()} active={chosen().length > 0}>
      <ChoiceSet
        type={{ type: "str" }}
        label={name()}
        choices={semanticSpacesOf(definitions)}
        value={chosen()}
        onChange={(spaces) => {
          if (spaces.length > 0) form.set(props.path(), spaces);
          else form.remove(props.path());
        }}
      />
    </SearchRow>
  );
}

/**
 * Groups of alternatives (`$any_of`): of each group at least one has to hold. Each alternative is a form of the same
 * type, in a box of its own, with "or" between them.
 */
function AnyOfRow(props: { type: string; path: Accessor<Path>; root?: boolean }) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const groups = () => (form.get(props.path()) as NodeSearch[][] | undefined) ?? [];
  const model = () => getModel(definitions, props.type);
  return (
    <SearchRow name={t("search_any_of", "Any of")} active={groups().length > 0}>
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
                          group.length <= 1 ? form.remove([...props.path(), g()]) : form.remove([...props.path(), g(), a()])
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
function OrderRow(props: { type: string; path: Accessor<Path> }) {
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
    <SearchRow name={name()} active={entries().length > 0}>
      <For each={entries()}>
        {(entry, index) => (
          <div class="flex w-full min-w-0 items-start gap-2">
            <Show when={index() > 0}>
              <span class="self-center text-xs font-semibold text-slate-500 uppercase select-none">
                {t("search_then_by", "then by")}
              </span>
            </Show>
            <select
              class={[compactClass, "min-w-36"]}
              aria-label={t("search_order_n", "Order by, {n}", { n: index() + 1 })}
              value={entry.field}
              onChange={(event) => form.set([...props.path(), index(), "field"], event.currentTarget.value)}
            >
              <For each={fields()}>
                {(field) => (
                  <option value={field} selected={entry.field === field}>
                    {nameOf(field)}
                  </option>
                )}
              </For>
            </select>
            <select
              class={compactClass}
              aria-label={t("search_direction", "Direction of {name}", { name: nameOf(entry.field) })}
              value={entry.direction ?? "asc"}
              onChange={(event) => form.set([...props.path(), index(), "direction"], event.currentTarget.value)}
            >
              <option value="asc" selected={(entry.direction ?? "asc") === "asc"}>
                {t("search_ascending", "ascending")}
              </option>
              <option value="desc" selected={entry.direction === "desc"}>
                {t("search_descending", "descending")}
              </option>
            </select>
            <button
              type="button"
              class={removeConditionClass}
              aria-label={t("remove_item", "Remove {name}", { name: nameOf(entry.field) })}
              onClick={() => form.remove([...props.path(), index()])}
            >
              ✕
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
        <select
          class={compactClass}
          aria-label={t("search_saved", "Saved searches")}
          value={chosen()}
          onChange={(event) => {
            const found = all().find((each) => each.name === event.currentTarget.value);
            setChosen(event.currentTarget.value);
            if (found) props.onLoad(structuredClone(found.form));
          }}
        >
          <option value="" textContent={t("search_saved_placeholder", "Saved searches…")} />
          <For each={all()}>
            {(each) => (
              <option value={each.name} selected={chosen() === each.name}>
                {each.name}
              </option>
            )}
          </For>
        </select>
        <Show when={chosen()}>
          <button
            type="button"
            class={removeConditionClass}
            aria-label={t("search_delete_saved", "Delete the saved search {name}", { name: chosen() })}
            title={t("search_delete_saved", "Delete the saved search {name}", { name: chosen() })}
            onClick={() => {
              setAll(deleteSearch(props.type, chosen()));
              setChosen("");
            }}
          >
            ✕
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
          class={[compactClass, "min-w-48"]}
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
