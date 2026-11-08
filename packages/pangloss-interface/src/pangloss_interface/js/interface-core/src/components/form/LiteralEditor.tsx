import { createSignal, For, Match, Show, Switch, untrack } from "solid-js";
import type { Accessor } from "solid-js";
import { useItemForm, useModels, useTranslations } from "../../context";
import type { FieldMarker, FieldType, Validator } from "../../types";
import type { Path } from "../../schema";
import {
  addSlotClass,
  dateTimeWidthClass,
  dateWidthClass,
  inputClass,
  joinedFrameClass,
  joinedRemoveClass,
  numberWidthClass,
  smallButtonClass,
} from "./styles";
import { allowOnly, decimalCharacters, NumberInput } from "./NumberInput";
import { revealAdded } from "./reveal";

type Typed<T extends FieldType["type"]> = Extract<FieldType, { type: T }>;

// (the number a validator of the field gives for an attribute of the input: `Ge(1)` is `min="1"`)
function limit(validators: Validator[] | undefined, name: string, key: string): number | undefined {
  const found = validators?.find((validator) => validator.name === name)?.[key];
  return typeof found === "number" ? found : undefined;
}

/** How wide an input for a value of the type is: short for what is always short (a number, a date), else "" (the whole width) */
function widthOf(type: FieldType): string {
  if (type.type === "int" || type.type === "float") return numberWidthClass;
  if (type.type === "date" || type.type === "time") return dateWidthClass;
  if (type.type === "datetime") return dateTimeWidthClass;
  return "";
}

// (what a text means, as the browser's input for it: a URL or an email address has one; the rest is text)
const INPUT_TYPE_OF_FORMAT: Record<string, string> = { url: "url", email: "email" };

/** The `type` of the input for a text (`str`) of the format, or "text" */
export function textInputType(type: FieldType): string {
  const format = "format" in type ? type.format : undefined;
  return (format && INPUT_TYPE_OF_FORMAT[format]) || "text";
}

// (more choices than this are a dropdown; as many or fewer, pills to click)
const MAX_PILLS = 8;

/**
 * One of a few values, as pills side by side, the chosen one filled; clicking it again chooses none
 * (a field that must have one says so when the form is saved). A radio group to a screen reader.
 * With none chosen, the one the field is taken to be (`value` is then that) is filled as well.
 */
function ChoicePills(props: {
  label: string;
  options: { value: string; name: string }[];
  value: string;
  onChoose: (value: string) => void;
}) {
  return (
    <div role="radiogroup" aria-label={props.label} class="flex flex-wrap gap-1.5">
      <For each={props.options}>
        {(option) => {
          const chosen = () => props.value === option.value;
          return (
            <button
              type="button"
              role="radio"
              aria-checked={chosen() ? "true" : "false"}
              class={[
                "cursor-pointer rounded-full border-[0.5px] px-3 py-1 text-sm select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400/60",
                chosen()
                  ? "border-slate-700 bg-slate-700 text-white hover:bg-slate-600"
                  : "border-slate-400/70 bg-white/80 text-slate-700 hover:bg-slate-200/70",
              ]}
              onClick={() => props.onChoose(chosen() ? "" : option.value)}
            >
              {option.name}
            </button>
          );
        }}
      </For>
    </div>
  );
}

// (a value in a single box, which the remove button of a list can be joined on to)
const joinable = (type: FieldType) =>
  ["int", "float", "str", "decimal", "date", "datetime", "time", "duration", "enum", "literal"].includes(type.type);

/** A value of the type that is not a literal the form knows (or that is in a list of the field's): the JSON, to edit as it is */
export function JsonEditor(props: { path: Accessor<Path>; label: string }) {
  const form = useItemForm();
  const { t } = useTranslations();
  // (what is there when it is drawn: then the box is its own, as what is typed may not be JSON yet)
  const [text, setText] = createSignal(untrack(() => JSON.stringify(form.get(props.path()) ?? null, null, 2)));
  const [bad, setBad] = createSignal(false);
  return (
    <div class="w-full">
      <textarea
        class={[inputClass, "font-mono", { "border-red-700": bad() }]}
        rows={4}
        aria-label={props.label}
        aria-invalid={bad() ? "true" : "false"}
        value={text()}
        onInput={(event) => {
          setText(event.currentTarget.value);
          try {
            form.set(props.path(), JSON.parse(event.currentTarget.value));
            setBad(false);
          } catch {
            setBad(true);
          }
        }}
      />
      <Show when={bad()}>
        <p class="text-xs text-red-800" role="alert">
          {t("invalid_json", "This is not valid JSON, so it is not changed")}
        </p>
      </Show>
    </div>
  );
}

/** A list of literals: each is an editor of its own, with a button to take it out, and one to add */
function ListEditor(props: {
  item: FieldType;
  path: Accessor<Path>;
  label: string;
  validators?: Validator[];
}) {
  const form = useItemForm();
  const { t } = useTranslations();
  const items = () => (form.get(props.path()) as unknown[] | undefined) ?? [];
  const blank = () => (props.item.type === "typedDict" ? {} : props.item.type === "bool" ? false : "");
  return (
    <div class={["flex w-full flex-col gap-1.5", widthOf(props.item)]}>
      {/* (by place, not by value: the value changes with every key) */}
      <For each={items()} keyed={false}>
        {(_, index) => (
          <Show
            when={joinable(props.item)}
            fallback={
              <div class="flex w-full items-start gap-2">
                <LiteralEditor
                  type={props.item}
                  path={() => [...props.path(), index]}
                  label={`${props.label} ${index + 1}`}
                />
                <button
                  type="button"
                  class={smallButtonClass}
                  aria-label={t("remove_item", "Remove {name}", { name: `${props.label} ${index + 1}` })}
                  onClick={() => form.remove([...props.path(), index])}
                >
                  ✕
                </button>
              </div>
            }
          >
            <div class={joinedFrameClass}>
              <LiteralEditor
                type={props.item}
                path={() => [...props.path(), index]}
                label={`${props.label} ${index + 1}`}
              />
              <button
                type="button"
                class={joinedRemoveClass}
                aria-label={t("remove_item", "Remove {name}", { name: `${props.label} ${index + 1}` })}
                title={t("remove_item", "Remove {name}", { name: `${props.label} ${index + 1}` })}
                onClick={() => form.remove([...props.path(), index])}
              >
                ✕
              </button>
            </div>
          </Show>
        )}
      </For>
      <button
        type="button"
        class={addSlotClass}
        aria-label={t("add_to", "Add to {name}", { name: props.label })}
        onClick={(event) => {
          const slot = event.currentTarget;
          form.set([...props.path(), items().length], blank());
          // (the new one is just before the slot)
          revealAdded(() => slot.previousElementSibling);
        }}
      >
        + {t("add", "Add")}
      </button>
    </div>
  );
}

/**
 * An input for a value of a literal type, at `path` of the form: text, a number, a yes or no, a
 * date, a choice of an enum's members, the parts of a typed dict, or a list of these.
 */
export function LiteralEditor(props: {
  type: FieldType;
  path: Accessor<Path>;
  /** The name of the input for a screen reader */
  label: string;
  validators?: Validator[];
  /** How it is edited (`Slider`) */
  markers?: FieldMarker[];
  /** What it is taken to be when it is not set: a choice shows it as chosen (it is not written) */
  fallback?: unknown;
}) {
  const form = useItemForm();
  const definitions = useModels();
  const { memberName, fieldName } = useTranslations();
  const value = () => form.get(props.path());
  const text = () => (value() === null || value() === undefined ? "" : String(value()));
  const chosen = () => text() || (props.fallback === null || props.fallback === undefined ? "" : String(props.fallback));
  const write = (next: unknown) => form.set(props.path(), next);
  const members = () => definitions.enums[(props.type as Typed<"enum">).enum]?.members ?? [];
  // (`Slider()` on a number with both bounds: a range, with the number beside it, and its `unit`)
  const slider = () => {
    const marker = props.markers?.find((each) => each.name === "Slider");
    const min = limit(props.validators, "Ge", "ge") ?? limit(props.validators, "Gt", "gt");
    const max = limit(props.validators, "Le", "le") ?? limit(props.validators, "Lt", "lt");
    if (!marker || min === undefined || max === undefined) return undefined;
    const step = typeof marker.step === "number" ? marker.step : props.type.type === "int" ? 1 : (max - min) / 100;
    const unit = typeof marker.unit === "string" ? marker.unit : "";
    return { min, max, step, unit };
  };
  return (
    <Switch
      fallback={
        <JsonEditor path={props.path} label={props.label} />
      }
    >
      <Match when={props.type.type === "bool"}>
        <input
          type="checkbox"
          class="size-4"
          aria-label={props.label}
          checked={value() === true}
          onChange={(event) => write(event.currentTarget.checked)}
        />
      </Match>
      <Match when={(props.type.type === "int" || props.type.type === "float") && slider()}>
        {(found) => (
          <div class="flex w-full items-center gap-3">
            {/* (as tall as its handle: a thinner box crops the handle where what holds it clips) */}
            <input
              type="range"
              class="h-5 min-w-0 flex-1 cursor-pointer accent-slate-600"
              aria-label={props.label}
              aria-valuetext={`${text()}${found().unit}`}
              min={found().min}
              max={found().max}
              step={found().step}
              value={text() === "" ? found().min : text()}
              onInput={(event) => write(Number(event.currentTarget.value))}
            />
            <span class="w-12 shrink-0 text-right text-sm text-slate-700 tabular-nums" data-slider-value>
              {text()}
              {found().unit}
            </span>
          </div>
        )}
      </Match>
      <Match when={props.type.type === "int" || props.type.type === "float"}>
        <NumberInput
          class={["w-full", numberWidthClass].join(" ")}
          label={props.label}
          step={props.type.type === "int" ? 1 : "any"}
          min={limit(props.validators, "Ge", "ge")}
          max={limit(props.validators, "Le", "le")}
          value={text()}
          onInput={(typed) => write(typed === "" ? "" : Number(typed))}
        />
      </Match>
      <Match when={props.type.type === "str" || props.type.type === "decimal" || props.type.type === "duration"}>
        <input
          type={textInputType(props.type)}
          class={inputClass}
          aria-label={props.label}
          inputmode={props.type.type === "decimal" ? "decimal" : undefined}
          // (a duration is written as ISO 8601: a day, two hours and a half is P1DT2H30M)
          placeholder={props.type.type === "duration" ? "P1DT2H30M" : undefined}
          // (a decimal is a number: what is not in one is refused as it is typed)
          onBeforeInput={props.type.type === "decimal" ? allowOnly(decimalCharacters) : undefined}
          maxlength={limit(props.validators, "MaxLen", "max_length")}
          value={text()}
          onInput={(event) => write(event.currentTarget.value)}
        />
      </Match>
      <Match when={props.type.type === "date"}>
        <input
          type="date"
          class={[inputClass, dateWidthClass]}
          aria-label={props.label}
          value={text()}
          onInput={(event) => write(event.currentTarget.value)}
        />
      </Match>
      <Match when={props.type.type === "time"}>
        <input
          type="time"
          step={1}
          class={[inputClass, dateWidthClass]}
          aria-label={props.label}
          value={text()}
          onInput={(event) => write(event.currentTarget.value)}
        />
      </Match>
      <Match when={props.type.type === "datetime"}>
        <input
          type="datetime-local"
          class={[inputClass, dateTimeWidthClass]}
          aria-label={props.label}
          value={text().slice(0, 16)}
          onInput={(event) => write(event.currentTarget.value)}
        />
      </Match>
      <Match when={props.type.type === "enum" && members().length <= MAX_PILLS}>
        <ChoicePills
          label={props.label}
          options={members().map((member) => ({
            value: String(member.value),
            name: memberName((props.type as Typed<"enum">).enum, member.name),
          }))}
          value={chosen()}
          onChoose={write}
        />
      </Match>
      <Match
        when={
          props.type.type === "literal" &&
          (props.type as Typed<"literal">).values.length <= MAX_PILLS
        }
      >
        <ChoicePills
          label={props.label}
          options={(props.type as Typed<"literal">).values.map((option) => ({
            value: String(option),
            name: String(option),
          }))}
          value={chosen()}
          onChoose={write}
        />
      </Match>
      <Match when={props.type.type === "enum"}>
        <select
          class={inputClass}
          aria-label={props.label}
          value={chosen()}
          onChange={(event) => write(event.currentTarget.value)}
        >
          <option value=""></option>
          <For each={members()}>
            {(member) => (
              <option value={String(member.value)} selected={chosen() === String(member.value)}>
                {memberName((props.type as Typed<"enum">).enum, member.name)}
              </option>
            )}
          </For>
        </select>
      </Match>
      <Match when={props.type.type === "literal"}>
        <select
          class={inputClass}
          aria-label={props.label}
          value={chosen()}
          onChange={(event) => write(event.currentTarget.value)}
        >
          <option value=""></option>
          <For each={(props.type as Typed<"literal">).values}>
            {(option) => (
              <option value={String(option)} selected={chosen() === String(option)}>
                {String(option)}
              </option>
            )}
          </For>
        </select>
      </Match>
      <Match when={props.type.type === "list"}>
        <ListEditor
          item={(props.type as Typed<"list">).item}
          path={props.path}
          label={props.label}
          validators={props.validators}
        />
      </Match>
      <Match when={props.type.type === "typedDict"}>
        <div class="grid w-full grid-cols-[8rem_minmax(0,1fr)] items-center gap-x-4 gap-y-2">
          <For each={Object.entries((props.type as Typed<"typedDict">).fields)}>
            {([key, fieldType]) => (
              <>
                <span class="text-xs font-semibold text-slate-500 uppercase">
                  {fieldName("", key)}
                </span>
                <LiteralEditor
                  type={fieldType}
                  path={() => [...props.path(), key]}
                  label={`${props.label} ${fieldName("", key)}`}
                />
              </>
            )}
          </For>
        </div>
      </Match>
    </Switch>
  );
}
