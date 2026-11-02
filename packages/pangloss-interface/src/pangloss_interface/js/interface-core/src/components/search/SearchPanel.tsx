import { createContext, createMemo, createSignal, For, Match, onCleanup, Show, Switch, untrack, useContext } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";
import type { JSX } from "@solidjs/web";
import { createItemFormState, useComponent, useModels, useTranslations } from "../../context";
import type { ItemFormState } from "../../context";
import { kindRule, kindTint } from "../../primitives";
import {
  getModel,
  incomingSourcesOf,
  menuGroups,
  operatorsOf,
  searchFieldsOf,
  searchKindOf,
  targetsEntities,
} from "../../schema";
import type {
  FieldSearch,
  IncomingSearch,
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

// (the button that takes a condition out: as tall as the boxes of the row, however tall the row grows)
const removeConditionClass =
  "inline-flex shrink-0 cursor-pointer items-center self-start rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/60 px-2 py-1.5 text-xs leading-5 text-red-800 select-none hover:bg-red-400/30";

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
  const clear = () => {
    state.set(["fields"], {});
    state.remove(["mentions"]);
    state.set(["incoming"], []);
    emit();
  };
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
            "grid transition-[grid-template-rows,opacity] duration-300",
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
            <div class="rounded-b-sm border-[0.5px] border-t-0 border-slate-400/70 bg-slate-200/40">
              <div class="px-6 pt-6 pb-5">
                <NodeFields type={props.type} path={() => []} root />
              </div>
              <div class="flex items-center justify-end gap-2 border-t-[0.5px] border-slate-400/50 px-6 py-2">
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
function NodeFields(props: { type: string; path: Accessor<Path>; root?: boolean }) {
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
        "shrink-0 cursor-pointer self-start rounded-sm border-[0.5px] px-2 py-1.5 text-xs leading-5 font-semibold uppercase select-none",
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

/** One field of the form: the toggle for not, its operator, and what it is compared with */
function ConditionRow(props: { type: string; field: SearchField; name: string; path: Accessor<Path> }) {
  const form = useSearchForm();
  const definitions = useModels();
  const { t } = useTranslations();
  const ops = createMemo(() => operatorsOf(definitions, props.field));
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
    <SearchRow name={props.name} active={isActive(search())}>
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
            onClick={() => form.remove(props.path())}
          >
            ✕
          </button>
        </Show>
      </div>
      <Show when={op() === "match" && search()?.node?.type}>
        <NestedNode
          type={search()!.node!.type}
          targets={props.field.targets ?? []}
          path={() => [...props.path(), "node"]}
          onRetype={(type) => form.set([...props.path(), "node"], { type })}
        />
      </Show>
    </SearchRow>
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
function ChoiceSet(props: { type: FieldType; label: string; value: unknown[]; onChange: (values: unknown[]) => void }) {
  const definitions = useModels();
  const { t, memberName } = useTranslations();
  const options = (): { value: unknown; name: string }[] => {
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
        <option value="">{`+ ${t("search_add_referring", "Add what refers to it")}`}</option>
        <For each={sources()}>
          {(source, index) => <option value={String(index())}>{sourceName(source)}</option>}
        </For>
      </select>
    </SearchRow>
  );
}
