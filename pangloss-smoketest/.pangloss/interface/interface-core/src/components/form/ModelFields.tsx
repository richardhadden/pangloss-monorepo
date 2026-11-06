import { action, children, createMemo, createOptimistic, createRenderEffect, createSignal, onSettled, untrack, For, Match, Show, Switch } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";
import type { JSX } from "@solidjs/web";
import {
  createItemFormState,
  ItemFormProvider,
  useApi,
  useComponent,
  useItemForm,
  useModels,
  useToasts,
  useTranslations,
} from "../../context";
import { kindRule, kindTint, spaceTint } from "../../primitives";
import {
  blankItem,
  createFormHooks,
  cleanForSave,
  choicesOf,
  choiceValue,
  envOf,
  filled,
  getModel,
  headlessIn,
  lengthBound,
  menuGroups,
  optionFor,
  reachFor,
  relationLayout,
  resolveOptions,
  wrapEntity,
} from "../../schema";
import type { Choice, Env, FormData, MenuGroup, Path } from "../../schema";
import type {
  AnnotatedValueField,
  EmbeddedField,
  FieldDefinition,
  ModelDefinition,
  NewItemForm,
  RelationField,
  RelationOption,
} from "../../types";
import { createItem } from "../../api";
import type { Summary } from "../../api";
import { EntityPicker } from "./EntityPicker";
import { NewItemFields } from "./NewItemActions";
import { rememberEntity } from "./recent";
import { JsonEditor, LiteralEditor } from "./LiteralEditor";
import {
  addSlotClass,
  choiceButtonClass,
  fieldGridClass,
  fieldRowClass,
  fieldRuleClass,
  inputClass,
  joinedButtonClass,
  joinedRemoveClass,
  headBarClass,
  headButtonClass,
  headMenuButtonClass,
  headRestClass,
  headRestOpenClass,
  nestedClass,
  plainTint,
  smallButtonClass,
  spaceButtonsClass,
  spaceTypeClass,
  typeChipClass,
} from "./styles";
import { TypeChooser, TypeGrid, TypeMenu, useSelectTitle } from "./TypeMenu";
import { revealAdded } from "./reveal";
import { RetypeButtons } from "./Retype";
import { ClipButtons, EmbeddedPasteSlot, RelationPasteSlot, useClipActions } from "./Clip";
import { FieldProblems, useRowProblems, useSaveChecks } from "./Problems";
import { Customised } from "../Customised";

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * Something nested: a head line with its type (a tinted chip), what it is called, any `buttons` of
 * its own (a document's, to change its type), and a remove button (the bar itself folds it); under it, its fields, indented, with a rule in the colour of its type down the left.
 */
function Block(
  props: ParentProps<{
    type: string;
    label?: string;
    tint: string;
    rule: string;
    onRemove?: () => void;
    /** Puts it on the clipboard, copied or cut */
    clip?: { copy: () => void; cut: () => void };
    /** The id of the item it is (a document inside the one edited), to find it by: `?show=` scrolls to it */
    itemId?: string;
    /** Buttons before the fold (they may open menus, so the bar does not cut off what is over its edge) */
    buttons?: JSX.Element;
  }>,
) {
  const { t, modelName } = useTranslations();
  const [folded, setFolded] = createSignal(false);
  // (made once: each read of a prop that is elements makes them again, and one read only to ask whether there
  // are any left a second set, of which the browser said "Hydration key miss ... a detached element was created")
  const buttons = children(() => props.buttons);
  return (
    // (scrolled to, it stops clear of the console bar, with room for a line of what it is in)
    <div class="flex w-full min-w-0 scroll-mt-28 flex-col" data-item-id={props.itemId}>
      <div class={headBarClass}>
        <span data-tint class={[typeChipClass, props.tint || plainTint, props.rule]}>
          {modelName(props.type)}
        </span>
        <div class={buttons() ? headRestOpenClass : headRestClass}>
          {/* (the grey of the bar, with the label in it, folds it; folded, a ▸ says so) */}
          <button
            type="button"
            class="flex min-w-0 flex-1 cursor-pointer items-center gap-2 px-3 py-1 text-left text-sm hover:bg-slate-400/20 focus-visible:bg-slate-400/20 focus-visible:outline-none"
            aria-expanded={folded() ? "false" : "true"}
            aria-label={t("fold", "Fold or unfold {name}", { name: modelName(props.type) })}
            title={t("fold", "Fold or unfold {name}", { name: modelName(props.type) })}
            onClick={() => setFolded(!folded())}
          >
            <Show when={folded()}>
              <span aria-hidden="true" class="shrink-0 text-xs text-slate-500">
                ▸
              </span>
            </Show>
            <span class="min-w-0 truncate">{props.label}</span>
          </button>
          {buttons()}
          {/* (cut, copy, remove) */}
          <Show when={props.clip}>
            <ClipButtons
              name={props.label || modelName(props.type)}
              buttonClass={[headButtonClass, "text-slate-500 hover:bg-slate-400/30"].join(" ")}
              onCopy={() => props.clip!.copy()}
              onCut={() => props.clip!.cut()}
            />
          </Show>
          <Show when={props.onRemove}>
            <button
              type="button"
              class={[headButtonClass, "text-red-800 hover:bg-red-400/30"]}
              aria-label={t("remove_item", "Remove {name}", { name: modelName(props.type) })}
              onClick={() => props.onRemove?.()}
            >
              ✕
            </button>
          </Show>
        </div>
      </div>
      <Show when={!folded()}>
        {/* (the rule starts at the bar: what is under it hangs from the head) */}
        <div class={["ml-2 pt-4", nestedClass, props.rule]}>{props.children}</div>
      </Show>
    </div>
  );
}


/**
 * One labelled row of a form: the name on the left, the editor on the right. A required field has
 * a mark after its name, green once it is `met` (something is in it, and nothing wrong). The row of the field at
 * `path` shows what was found wrong in it when it was saved: its name turns red, with why under it. (An interface
 * module's row in a form is one too: `FieldRow`.)
 */
export function FieldRow(
  props: ParentProps<{
    name: string;
    path?: Path;
    required?: boolean;
    met?: boolean;
    description?: string | null;
    bare?: boolean;
  }>,
) {
  const problems = useRowProblems(() => props.path);
  const bad = () => problems().length > 0;
  return (
    <Show
      when={!props.bare}
      fallback={
        <div class={fieldRowClass} data-problem={bad() ? "" : undefined}>
          <div class="col-span-2 min-w-0">
            <FieldProblems problems={problems()} path={props.path ?? []} />
            {props.children}
          </div>
        </div>
      }
    >
      <div class={fieldRowClass} data-problem={bad() ? "" : undefined}>
        <dt
          class={[
            "pt-2 text-xs font-semibold uppercase transition-colors",
            { "text-slate-500": !bad(), "text-red-700": bad() },
          ]}
        >
          {props.name}
          <Show when={props.required}>
            <span
              aria-hidden="true"
              class={["transition-colors", { "text-green-600": !!props.met && !bad() }]}
            >
              {" *"}
            </span>
          </Show>
          <Show when={props.description}>
            <span class="mt-0.5 block text-xs font-normal text-slate-400 normal-case">{props.description}</span>
          </Show>
          <FieldProblems problems={problems()} path={props.path ?? []} />
        </dt>
        <dd class="flex min-w-0 flex-col items-start gap-1">{props.children}</dd>
      </div>
    </Show>
  );
}

/**
 * The editors of the fields of a model, each in its row, in the order of the model, for the
 * object at `path` of the form. `env` says what the type variables of a generic model stand for
 * here; `skip` leaves fields out (those only in the database, and read-only ones, are never shown), and `bare` is the
 * field (a reified relation's target) shown without its name, first: what the thing holds, then what is said of it.
 */
export function ModelFields(props: {
  model: ModelDefinition;
  path: Accessor<Path>;
  env: Env;
  skip?: string[];
  bare?: string;
  /** What a field is taken to be when it is not set, by key: shown as chosen (a choice), not written */
  defaults?: Record<string, unknown>;
  /** Rows before the fields (`FieldRow`s): those an interface module adds to a new item's form */
  lead?: JSX.Element;
}) {
  const form = useItemForm();
  const { fieldName } = useTranslations();
  // (not those only in the database: the server works them out, whatever is sent; nor those something else keeps up
  // to date, or the model says its forms do not show, which the item's page shows: what the form loaded of them is
  // sent back as it was)
  const hidden = () => props.model.interfaceMeta?.hideOnForms ?? [];
  const editable = () =>
    props.model.fields.filter((field) => !field.dbField && !field.readOnly && !hidden().includes(field.key));
  const fields = () => [
    ...editable().filter((field) => field.key === props.bare),
    ...editable().filter((field) => field.key !== props.bare),
  ];
  return (
    <dl class={fieldGridClass}>
      {props.lead}
      <For each={fields()}>
        {(field) => (
          <Show when={!(props.skip ?? []).includes(field.key)}>
            <FieldRow
              name={fieldName(props.model.name, field.name)}
              path={[...props.path(), field.key]}
              required={field.required}
              met={filled(form.get([...props.path(), field.key]))}
              description={field.description}
              bare={field.key === props.bare}
            >
              <FieldEditor
                field={field}
                modelName={props.model.name}
                path={() => [...props.path(), field.key]}
                env={props.env}
                bare={field.key === props.bare}
                fallback={props.defaults?.[field.key]}
              />
            </FieldRow>
          </Show>
        )}
      </For>
    </dl>
  );
}

/**
 * What a Document or an Entity has beside its fields: its label (and, to make one, its id if it
 * can be chosen). With `title` (the item the page or the dialog is for) the label is a heading,
 * a large box above the rest, rather than a row like the fields.
 */
export function ItemFields(props: {
  model: ModelDefinition;
  path: Accessor<Path>;
  /** Show the id too, for an item that is being made */
  creating?: boolean;
  title?: boolean;
  /** The form of the new item it is (the page's, or a dialog's): for the rows interface modules add (`newItemFields`) */
  newItem?: NewItemForm;
}) {
  const form = useItemForm();
  const { t, fieldName } = useTranslations();
  const text = (key: string) => {
    const value = form.get([...props.path(), key]);
    return typeof value === "string" ? value : "";
  };
  const labelInput = (classes: string) => (
    <input
      type="text"
      class={classes}
      aria-label={t("label", "Label")}
      aria-required={props.model.requireLabel ? "true" : undefined}
      value={text("label")}
      onInput={(event) => form.set([...props.path(), "label"], event.currentTarget.value)}
    />
  );
  return (
    <div class="flex flex-col gap-5">
      <Show when={props.title}>
        <TitleBox
          value={text("label")}
          label={t("label", "Label")}
          path={[...props.path(), "label"]}
          required={props.model.requireLabel}
          onInput={(value) => form.set([...props.path(), "label"], value)}
        />
      </Show>
      <Show when={!props.title || (props.creating && props.model.createWithId)}>
        <dl class={fieldGridClass}>
          <Show when={!props.title}>
            <FieldRow
              name={t("label", "Label")}
              path={[...props.path(), "label"]}
              required={props.model.requireLabel}
              met={text("label") !== ""}
            >
              {labelInput(inputClass)}
            </FieldRow>
          </Show>
          <Show when={props.creating && props.model.createWithId}>
            <FieldRow name={fieldName(props.model.name, "id")} path={[...props.path(), "id"]}>
              <input
                type="text"
                class={inputClass}
                aria-label={t("id", "ID")}
                value={text("id")}
                onInput={(event) => form.set([...props.path(), "id"], event.currentTarget.value)}
              />
            </FieldRow>
          </Show>
        </dl>
      </Show>
      {/* (a rule between the label's row and the first field, as between fields; the heading has its own) */}
      <div class={{ [`border-t pt-5 ${fieldRuleClass}`]: !props.title || !!(props.creating && props.model.createWithId) }}>
        <ModelFields
          model={props.model}
          path={props.path}
          env={{}}
          lead={
            <Show when={props.newItem}>
              {(form) => <NewItemFields type={props.model.name} model={props.model} form={form()} />}
            </Show>
          }
        />
      </div>
    </div>
  );
}

/**
 * The label of the item as a heading: a box in large type, one line high, that grows a line at a
 * time as a long label wraps (to the width of the page, and again when that changes). A label is
 * one line of text, only wrapped: Enter makes no new line, and the line breaks of what is pasted
 * are spaces. What was found wrong with it is shown as at a row: the rule and what it says red.
 */
function TitleBox(props: {
  value: string;
  label: string;
  path: Path;
  required?: boolean;
  onInput: (value: string) => void;
}) {
  const problems = useRowProblems(() => props.path);
  const bad = () => problems().length > 0;
  let box: HTMLTextAreaElement | undefined;
  // (as tall as what is in it: first none, so that it can shrink too)
  const fit = () => {
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${box.scrollHeight}px`;
  };
  // (sized with the DOM, before the page is painted. A label set by code, not typed, may not be in the box yet when
  // this runs: it is put there first, or the box is measured with the old one)
  createRenderEffect(
    () => props.value,
    (value) => {
      if (box && box.value !== value) box.value = value;
      fit();
    },
  );
  onSettled(() => {
    fit();
    // (again when it is wider or narrower: the window, a dialog laid out, a panel opened beside it. Not when only its
    // height changes, which is this)
    if (!box || typeof ResizeObserver === "undefined") return;
    let width = box.clientWidth;
    const observer = new ResizeObserver(() => {
      if (box?.clientWidth === width) return;
      width = box?.clientWidth;
      fit();
    });
    observer.observe(box);
    return () => observer.disconnect();
  });
  return (
    <div data-problem={bad() ? "" : undefined}>
      <textarea
        ref={box}
        rows={1}
        class={[
          "block w-full min-w-0 resize-none overflow-hidden border-b-[0.5px] bg-transparent pt-1 pb-2 text-2xl leading-snug font-semibold placeholder:font-normal focus:outline-none",
          {
            "border-slate-400/70": !bad(),
            "placeholder:text-slate-400": !bad(),
            "focus:border-slate-600": !bad(),
            "border-red-700": bad(),
            "placeholder:text-red-700/70": bad(),
          },
        ]}
        aria-label={props.label}
        aria-invalid={bad() ? "true" : undefined}
        aria-required={props.required ? "true" : undefined}
        placeholder={`${props.label}${props.required ? " *" : ""}`}
        value={props.value}
        onKeyDown={(event) => {
          // (Enter in a one-line field: nothing, rather than a line break, or the form's submit)
          if (event.key === "Enter") event.preventDefault();
        }}
        onInput={(event) => {
          const box = event.currentTarget;
          const flat = box.value.replace(/\r?\n/g, " ");
          if (flat !== box.value) {
            const at = box.selectionStart;
            box.value = flat;
            box.setSelectionRange(at, at);
          }
          props.onInput(flat);
          fit();
        }}
      />
      <FieldProblems problems={problems()} path={props.path} />
    </div>
  );
}

/** The editor for one field, by what kind of field it is */
function FieldEditor(props: {
  field: FieldDefinition;
  modelName: string;
  path: Accessor<Path>;
  env: Env;
  /** Shown without its name: its buttons say only what they do */
  bare?: boolean;
  /** What a literal is taken to be when it is not set */
  fallback?: unknown;
}) {
  const { fieldName } = useTranslations();
  const name = () => fieldName(props.modelName, props.field.name);
  return (
    <Switch fallback={<JsonEditor path={props.path} label={name()} />}>
      <Match when={props.field.kind === "literal"}>
        <LiteralEditor
          type={(props.field as Extract<FieldDefinition, { kind: "literal" }>).type}
          validators={(props.field as Extract<FieldDefinition, { kind: "literal" }>).validators}
          markers={(props.field as Extract<FieldDefinition, { kind: "literal" }>).markers}
          path={props.path}
          label={name()}
          fallback={props.fallback}
        />
      </Match>
      <Match when={props.field.kind === "list"}>
        <LiteralEditor
          type={{ type: "list", item: (props.field as Extract<FieldDefinition, { kind: "list" }>).item }}
          path={props.path}
          label={name()}
        />
      </Match>
      <Match when={props.field.kind === "annotatedValue"}>
        <AnnotatedEditor field={props.field as AnnotatedValueField} path={props.path} label={name()} />
      </Match>
      <Match when={props.field.kind === "embedded"}>
        <EmbeddedEditor field={props.field as EmbeddedField} path={props.path} label={name()} />
      </Match>
      <Match when={props.field.kind === "relation"}>
        <RelationEditor field={props.field as RelationField} path={props.path} env={props.env} label={name()} bare={props.bare} />
      </Match>
    </Switch>
  );
}

/** A value with fields of its own (a text and how certain it is): the value, then the rest */
function AnnotatedEditor(props: { field: AnnotatedValueField; path: Accessor<Path>; label: string }) {
  const definitions = useModels();
  const model = () => getModel(definitions, props.field.model);
  return (
    <div class="flex w-full flex-col gap-2">
      <Show
        when={props.field.valueType}
        fallback={<JsonEditor path={() => [...props.path(), "value"]} label={props.label} />}
      >
        <LiteralEditor
          type={props.field.valueType!}
          path={() => [...props.path(), "value"]}
          label={props.label}
        />
      </Show>
      <Show when={model()}>
        <ModelFields model={model()!} path={props.path} env={{}} skip={["value"]} />
      </Show>
    </div>
  );
}

const typeOptions = (types: string[]): RelationOption[] =>
  types.map((type) => ({ kind: "document", type, edgeModel: null }));

/** An embedded object: its types to choose from (a date is an exact date, a range...), then the fields of the one chosen, under a menu to change the type */
function EmbeddedEditor(props: { field: EmbeddedField; path: Accessor<Path>; label: string }) {
  const form = useItemForm();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const value = () => {
    const at = form.get(props.path());
    return isObject(at) ? at : undefined;
  };
  const groups = createMemo(() => menuGroups(definitions, typeOptions(props.field.types)));
  const model = () => (value() ? getModel(definitions, String(value()!.type)) : undefined);
  const clip = useClipActions(props.path, () => form.remove(props.path()));
  const choose = (choice: Choice) => {
    const next = getModel(definitions, choice.type);
    // (what the two types have in common is kept when the type is changed)
    const kept = Object.fromEntries(
      Object.entries(value() ?? {}).filter(([key]) => next?.fields.some((field) => field.key === key)),
    );
    const added = !value();
    form.set(props.path(), { ...kept, type: choice.type });
    if (added) revealAdded(() => root);
  };
  let root: HTMLDivElement | undefined;
  return (
    <div ref={root} class="flex w-full min-w-0 flex-col">
      <Show
        when={value()}
        fallback={
          <div class="flex w-full flex-col gap-2">
            <TypeChooser
              groups={groups()}
              label={t("add_named", "Add {name}", { name: props.label })}
              buttonClass={addSlotClass}
              onChoose={choose}
            >
              <EmbeddedPasteSlot
                field={props.field}
                onPaste={(pasted) => {
                  form.set(props.path(), pasted);
                  revealAdded(() => root);
                }}
              />
            </TypeChooser>
          </div>
        }
      >
        {/* (the type chosen, which its menu changes, with the remove button joined on; the corners are
            the parts', not clipped by the frame, which would hide the menu that opens below) */}
        <div class="inline-flex self-start rounded-xs border-[0.5px] border-slate-400/70 bg-slate-100/60">
          <TypeMenu
            groups={groups()}
            label={modelName(String(value()!.type))}
            buttonClass="flex cursor-pointer items-center gap-1 rounded-xs px-2 py-1 text-xs font-semibold uppercase select-none hover:bg-slate-300/50 focus:bg-slate-300/50 focus:outline-none"
            onChoose={choose}
          />
          <Show when={clip}>
            <ClipButtons
              name={props.label}
              buttonClass="flex w-6 shrink-0 cursor-pointer items-center justify-center border-l-[0.5px] border-slate-400/70 text-slate-500 select-none hover:bg-slate-300/50 focus:bg-slate-300/50 focus:outline-none"
              onCopy={() => clip!.copy()}
              onCut={() => clip!.cut()}
            />
          </Show>
          <Show when={!props.field.required}>
            <button
              type="button"
              class={[joinedRemoveClass, "rounded-r-xs"]}
              aria-label={t("remove_item", "Remove {name}", { name: props.label })}
              title={t("remove_item", "Remove {name}", { name: props.label })}
              onClick={() => form.remove(props.path())}
            >
              ✕
            </button>
          </Show>
        </div>
      </Show>
      <Show when={model()}>
        <div class={["ml-2 pt-4", nestedClass, "border-slate-300"]}>
          {/* (a model can name an editor of its own, in an interface module: the dates do) */}
          <Customised
            slot="editCard"
            type={String(value()!.type)}
            props={{
              type: String(value()!.type),
              model: model()!,
              field: props.field,
              label: props.label,
              get path() {
                return props.path();
              },
              get value() {
                return value() ?? {};
              },
              onChange: (next) => form.set(props.path(), next),
            }}
            fallback={<ModelFields model={model()!} path={props.path} env={{}} />}
          />
        </div>
      </Show>
    </div>
  );
}

/**
 * A relation: the things it holds (one, or a list), each its own editor, and a way to add one. The
 * entities it can hold are a search to find them, with a button under it for each of the rest (a
 * reified relation, a conjunction...); with a `defaultReifiedType`, the search is for what that
 * holds, and an entity found is put in one. A relation with no entities to search for has a menu of
 * the types it can hold, and the same inside each semantic space it can hold.
 */
function RelationEditor(props: {
  field: RelationField;
  path: Accessor<Path>;
  env: Env;
  label: string;
  bare?: boolean;
}) {
  const form = useItemForm();
  const definitions = useModels();
  const { t } = useTranslations();
  const options = createMemo(() => resolveOptions(props.field.options, props.env));
  const groups = createMemo(() => menuGroups(definitions, options()));
  const layout = createMemo(() =>
    relationLayout(definitions, options(), props.env, props.field.defaultReifiedType),
  );
  const searched = () => layout().search.map((reach) => reach.type);
  const items = () => {
    const at = form.get(props.path());
    if (props.field.many) return Array.isArray(at) ? at : [];
    return isObject(at) ? [at] : [];
  };
  const where = () => (props.field.many ? [...props.path(), items().length] : props.path());
  // (the last item is a block, not a chip: what adds is as far below it as the items are from each other)
  const endsInBlock = () => {
    const last = items().at(-1);
    return isObject(last) && getModel(definitions, String(last.type ?? ""))?.kind !== "Entity";
  };
  // (a list as long as it may be, `MaxLen`, has no way to add more)
  const canAdd = () =>
    props.field.many ? items().length < (lengthBound(props.field.validators, "max") ?? Infinity) : items().length === 0;
  // (the items, side by side or a line each: the last is the one just added)
  let list: HTMLDivElement | undefined;
  const lastAdded = () => (props.field.many ? list?.lastElementChild : list);
  const add = (choice: Choice) => {
    const option = optionFor(options(), choice.type);
    form.set(
      where(),
      choice.spaces.length === 0 && option
        ? blankItem(definitions, choice.type, envOf(option, props.env))
        : choiceValue(definitions, choice),
    );
    revealAdded(lastAdded);
  };
  const only = () => choicesOf(groups());
  const pasteSlot = () => (
    <RelationPasteSlot
      options={options()}
      env={props.env}
      onPaste={(pasted) => {
        form.set(where(), pasted);
        revealAdded(lastAdded);
      }}
    />
  );
  return (
    <div class={["flex w-full min-w-0 flex-col", endsInBlock() ? "gap-6" : "gap-4"]}>
      <Show
        when={props.field.many}
        fallback={
          <Show when={items().length > 0}>
            <div ref={list} class="flex w-full min-w-0">
              <RelationItem
                path={props.path}
                options={options()}
                env={props.env}
                onRemove={() => form.remove(props.path())}
                headless={headlessIn(
                  definitions,
                  { ...props.field, options: options() },
                  String((items()[0] as FormData | undefined)?.type ?? ""),
                )}
              />
            </div>
          </Show>
        }
      >
        {/* (entities as chips side by side; anything bigger, a line of its own) */}
        <Show when={items().length > 0}>
          <div ref={list} class="flex w-full min-w-0 flex-wrap items-start gap-x-2 gap-y-6">
            <For each={items()}>
              {(_, index) => (
                <RelationItem
                  path={() => [...props.path(), index()]}
                  options={options()}
                  env={props.env}
                  onRemove={() => form.remove([...props.path(), index()])}
                />
              )}
            </For>
          </div>
        </Show>
      </Show>
      <Show when={canAdd()}>
        <Show
          when={searched().length > 0}
          fallback={
            <Show
              when={only().length > 0}
              fallback={
                <Show when={props.field.options.length > 0}>
                  <JsonEditor path={props.path} label={props.label} />
                </Show>
              }
            >
              {/* (what can be pasted is the last part of the types to choose from) */}
              <TypeChooser
                groups={groups()}
                label={
                  props.bare ? t("add", "Add") : t("add_named", "Add {name}", { name: props.label })
                }
                buttonClass={addSlotClass}
                onChoose={add}
              >
                {pasteSlot()}
              </TypeChooser>
            </Show>
          }
        >
          <div class="flex w-full min-w-0 flex-col gap-2">
            <PickOrCreate
              types={searched()}
              onPick={(entity) => {
                const found = { type: entity.type, id: entity.id, label: entity.label };
                const reach = reachFor(definitions, layout().search, entity.type);
                const wrapped = reach && reach.wrappers.length > 0;
                form.set(where(), wrapped ? wrapEntity(definitions, reach, found) : found);
                // (an entity alone: the chip lights up, but the cursor stays in the search, for the next; put in a
                // reified relation, the cursor goes to the fields of that, to be filled in)
                revealAdded(lastAdded, !wrapped);
              }}
            />
            <Show when={layout().rest.length > 0}>
              <div class="flex flex-wrap gap-2">
                <For each={layout().rest}>
                  {(choice) => <ChoiceButton choice={choice} onChoose={add} />}
                </For>
              </div>
            </Show>
            {pasteSlot()}
          </div>
        </Show>
      </Show>
    </div>
  );
}

/** A button that adds one of the types of a relation (inside its semantic spaces), in the colour of its type */
function ChoiceButton(props: { choice: Choice; onChoose: (choice: Choice) => void }) {
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const name = () => [...props.choice.spaces, props.choice.type].map((type) => modelName(type)).join(" › ");
  const tint = () => {
    const model = getModel(definitions, props.choice.type);
    return kindTint(model?.kind, model?.interfaceMeta?.colour) || plainTint;
  };
  return (
    <button
      type="button"
      class={[choiceButtonClass, tint()]}
      aria-label={t("add_named", "Add {name}", { name: name() })}
      onClick={() => props.onChoose(props.choice)}
    >
      <span aria-hidden="true">+</span>
      {name()}
    </button>
  );
}

/**
 * One thing in a relation, by what it is. An entity is a chip (or a search, while it is not
 * chosen), with the properties of the relation under it. A semantic space is a band with what is
 * in it inside; the others are boxes with their own fields (a document's, a reified relation's).
 */
function RelationItem(props: {
  path: Accessor<Path>;
  options: RelationOption[];
  env: Env;
  onRemove: () => void;
  /** It is all its field can hold, and the field holds one, and must: no head (`InterfaceMeta(headless=True)`) */
  headless?: boolean;
}) {
  const form = useItemForm();
  const definitions = useModels();
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, modelName } = useTranslations();
  const value = () => {
    const at = form.get(props.path());
    return isObject(at) ? at : undefined;
  };
  const type = () => String(value()?.type ?? "");
  const model = () => getModel(definitions, type());
  const option = () => optionFor(props.options, type());
  const childEnv = () => {
    const found = option();
    return found ? envOf(found, props.env) : {};
  };
  const edgeModel = () => {
    const found = option();
    return found && "edgeModel" in found && found.edgeModel
      ? getModel(definitions, found.edgeModel)
      : undefined;
  };
  const label = () => (typeof value()?.label === "string" ? String(value()!.label) : undefined);
  const clip = useClipActions(props.path, () => props.onRemove(), () => {
    const found = option();
    return found && "edgeModel" in found ? found.edgeModel : null;
  });
  return (
    <Switch fallback={<JsonEditor path={props.path} label={type()} />}>
      <Match when={model()?.kind === "Entity"}>
        <div
          class={[
            // (no gap: the rule of the properties hangs from the chip)
            "flex min-w-0 flex-col items-start",
            // (a chip alone is as wide as itself, beside the others; a search, or a chip with properties, the whole line)
            { "w-full": !value()?.id || !!edgeModel() },
            { "max-w-full": !!value()?.id && !edgeModel() },
          ]}
        >
          <Show
            when={value()?.id}
            fallback={
              <PickOrCreate
                types={[type()]}
                onPick={(entity) =>
                  form.set(props.path(), {
                    ...value(),
                    type: entity.type,
                    id: entity.id,
                    label: entity.label,
                  })
                }
                onRemove={props.onRemove}
                removeLabel={t("remove_item", "Remove {name}", { name: modelName(type()) })}
              />
            }
          >
            <ReferenceChip
              type={type()}
              label={label() ?? String(value()?.id)}
              onRemove={props.onRemove}
              onCopy={clip?.copy}
              onCut={clip?.cut}
              removeLabel={t("remove_item", "Remove {name}", { name: label() ?? type() })}
            />
          </Show>
          <Show when={edgeModel() && value()?.id}>
            <div class={["ml-2 pt-3", nestedClass, kindRule("Entity", model()?.interfaceMeta?.colour)]}>
              <ModelFields
                model={edgeModel()!}
                path={() => [...props.path(), "edgeProperties"]}
                env={{}}
              />
            </div>
          </Show>
        </div>
      </Match>
      <Match when={model()?.kind === "SemanticSpace"}>
        <div
          data-tint
          class={[
            "flex w-full min-w-0 flex-col rounded-xs",
            spaceTint(model()?.interfaceMeta?.colour, Math.floor(props.path().length / 2)),
          ]}
        >
          <div class="flex items-center justify-between">
            <span class={spaceTypeClass}>{modelName(type())}</span>
            <div class={spaceButtonsClass}>
              <Show when={clip}>
                <ClipButtons
                  name={modelName(type())}
                  buttonClass={[headButtonClass, "h-7 text-slate-600 hover:bg-slate-400/30"].join(" ")}
                  onCopy={() => clip!.copy()}
                  onCut={() => clip!.cut()}
                />
              </Show>
              <button
                type="button"
                class={[headButtonClass, "h-7 text-red-800 hover:bg-red-400/30"]}
                aria-label={t("remove_item", "Remove {name}", { name: modelName(type()) })}
                onClick={props.onRemove}
              >
                ✕
              </button>
            </div>
          </div>
          <div class="flex min-w-0 flex-1 flex-col gap-4 p-3">
            <ModelFields model={model()!} path={props.path} env={childEnv()} bare="contents" />
          </div>
        </div>
      </Match>
      <Match when={model()?.kind === "Document" || model()?.kind === "ReifiedRelationDocument"}>
        <Block
          type={type()}
          label={label()}
          tint={kindTint(model()?.kind, model()?.interfaceMeta?.colour)}
          rule={kindRule(model()?.kind, model()?.interfaceMeta?.colour)}
          onRemove={props.onRemove}
          clip={clip}
          itemId={typeof value()?.id === "string" ? String(value()!.id) : undefined}
          buttons={
            <RetypeButtons
              type={type()}
              options={props.options}
              name={label() || modelName(type())}
              buttonClass={[headMenuButtonClass, "text-slate-500 hover:bg-slate-400/30"].join(" ")}
              value={value}
              onRetype={(next) => form.set(props.path(), next)}
            />
          }
        >
          <ItemFields model={model()!} path={props.path} />
        </Block>
      </Match>
      <Match when={props.headless && model()}>
        {/* (a reified relation with no head: what it holds, then its own fields, as if they were the field's) */}
        <div class="flex w-full min-w-0 flex-col">
          <ModelFields model={model()!} path={props.path} env={childEnv()} bare="target" />
        </div>
      </Match>
      <Match when={model()}>
        {/* (a reified relation, a conjunction: its own fields, and what it holds without the name of the field) */}
        <Block
          type={type()}
          tint={kindTint(model()?.kind, model()?.interfaceMeta?.colour)}
          rule={kindRule(model()?.kind, model()?.interfaceMeta?.colour)}
          onRemove={props.onRemove}
          clip={clip}
        >
          <ModelFields
            model={model()!}
            path={props.path}
            env={childEnv()}
            bare={model()?.kind === "ReifiedRelation" ? "target" : undefined}
          />
        </Block>
      </Match>
    </Switch>
  );
}

/**
 * A dialog to make an entity of one of the types of `groups` without leaving the form. With several
 * types it shows them first, laid out by the hierarchy (a `TypeGrid`); the one chosen opens its form,
 * and Back goes to the types again. With one type the form is shown at once.
 */
function EntityCreateDialog(props: {
  groups: MenuGroup[];
  onCreated: (entity: Summary) => void;
  onClose: () => void;
  /** What the form of the type chosen starts with, over the blank item (a date filled in, say) */
  initial?: (type: string) => Record<string, unknown>;
  /** What every item made in the form starts with, the item itself and each added to it (see `createItemFormState`) */
  fill?: (item: FormData) => FormData;
}) {
  const Modal = useComponent("Modal");
  const { t, modelName } = useTranslations();
  const choices = () => choicesOf(props.groups);
  const [type, setType] = createSignal(untrack(() => (choices().length === 1 ? choices()[0]!.type : undefined)));
  const selectTitle = useSelectTitle(() => props.groups);
  const title = () => (type() ? t("new_item", "New {type}", { type: modelName(type()!) }) : selectTitle());
  return (
    <Modal title={title()} onClose={props.onClose} size="lg">
      <Show
        when={type()}
        fallback={
          <div class="flex flex-col gap-6 p-6">
            <div class="overflow-hidden rounded-xs border-[0.5px] border-dashed border-slate-400/80 bg-white/60">
              <TypeGrid groups={props.groups} onChoose={(choice) => setType(choice.type)} autofocus />
            </div>
            <div class="flex justify-end gap-2">
              <button type="button" class={smallButtonClass} onClick={props.onClose}>
                {t("cancel", "Cancel")}
              </button>
            </div>
          </div>
        }
      >
        {(chosen) => (
          <EntityCreateForm
            type={chosen()}
            initial={props.initial}
            fill={props.fill}
            onBack={choices().length > 1 ? () => setType(undefined) : undefined}
            onCreated={props.onCreated}
            onClose={props.onClose}
          />
        )}
      </Show>
    </Modal>
  );
}

/**
 * The form of an entity of `type` in the dialog: its own form (a fresh state, so nothing of the item
 * behind it is touched), and Save makes the entity and hands it back. With `onBack` (it was chosen
 * from the types) the cursor goes into the form, and Back goes to the types again.
 */
function EntityCreateForm(props: {
  type: string;
  initial?: (type: string) => Record<string, unknown>;
  fill?: (item: FormData) => FormData;
  onBack?: () => void;
  onCreated: (entity: Summary) => void;
  onClose: () => void;
}) {
  const api = useApi();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const type = untrack(() => props.type);
  const fill = untrack(() => props.fill);
  const started = { ...blankItem(definitions, type), ...untrack(() => props.initial?.(type)) };
  const state = createItemFormState(fill ? fill(started) : started, { fill, binder: createFormHooks(definitions) });
  const model = getModel(definitions, type);
  // (while it is being made: back to false when that is over, whatever the answer)
  const [saving, setSaving] = createOptimistic(false);
  const toasts = useToasts();
  let root: HTMLDivElement | undefined;
  const checks = useSaveChecks(state, () => root);
  // (how it is sent instead of being made, if an interface module has said: `NewItemForm.sendBy`)
  let sender: Parameters<NewItemForm["sendBy"]>[0];
  const newItemForm: NewItemForm = {
    get: (path) => state.get(path),
    set: (path, value) => state.set(path, value),
    sendBy: (given) => {
      sender = given;
    },
  };
  // (what comes of it is `save`'s, once it is over)
  const make = action(function* (body: FormData) {
    setSaving(true);
    if (sender) return (yield sender(body)) as Summary;
    return (yield createItem(api, type, body)) as Summary;
  });
  async function save() {
    if (!checks.check()) return;
    const body = cleanForSave(definitions, state.plain());
    delete body.type;
    let created: Summary;
    try {
      created = await make(body);
    } catch (error) {
      checks.refused(error);
      return;
    }
    toasts?.show(
      t("toast_created", "{type} “{label}” created", {
        type: modelName(created.type),
        label: created.label,
      }),
    );
    props.onCreated(created);
  }
  onSettled(() => {
    // (the types it was chosen from are gone, and the cursor with them: into the form)
    if (props.onBack) root?.querySelector<HTMLElement>("input, textarea, select")?.focus();
  });
  return (
    <ItemFormProvider state={state}>
      <div ref={root} class="flex flex-col gap-6 p-6">
        <Show when={model}>
          <ItemFields model={model!} path={() => []} creating title newItem={newItemForm} />
        </Show>
        <div class="flex gap-2">
          <Show when={props.onBack}>
            <button type="button" class={smallButtonClass} onClick={() => props.onBack?.()}>
              ‹ {t("back", "Back")}
            </button>
          </Show>
          <span class="flex-1" />
          <button type="button" class={smallButtonClass} onClick={props.onClose}>
            {t("cancel", "Cancel")}
          </button>
          <button type="button" class={smallButtonClass} disabled={saving()} onClick={() => void save()}>
            {t("save", "Save")}
          </button>
        </div>
      </div>
    </ItemFormProvider>
  );
}

/**
 * Finds an entity of one of `types`, or makes a new one: a + button joined on to the end of the
 * search opens a dialog that shows the types (when there are several) and then the form for the
 * entity; the entity made is chosen as if it had been found. With `onRemove`, a remove button is
 * joined on after it (for a place in a list that has no entity yet). With `createTypes`, the + makes those instead
 * (more than are searched for: documents too, with `onCreated`).
 */
export function PickOrCreate(props: {
  types: string[];
  onPick: (entity: Summary) => void;
  onRemove?: () => void;
  removeLabel?: string;
  /** What the search box says before anything is typed (by default, the types it finds) */
  placeholder?: string;
  /** What the form of a new one starts with, over the blank item */
  initial?: (type: string) => Record<string, unknown>;
  /** What every item made in its form starts with (see `createItemFormState`) */
  fill?: (item: FormData) => FormData;
  /** The types the + makes, if not those searched for */
  createTypes?: string[];
  /** Called with one that was made, instead of `onPick` (by default it is picked as if it had been found) */
  onCreated?: (entity: Summary) => void;
}) {
  const definitions = useModels();
  const { t } = useTranslations();
  const [creating, setCreating] = createSignal(false);
  const groups = createMemo(() => menuGroups(definitions, typeOptions(props.createTypes ?? props.types)));
  return (
    <div class="w-full min-w-0">
      <EntityPicker types={props.types} onPick={props.onPick} placeholder={props.placeholder}>
        <Show when={choicesOf(groups()).length > 0}>
          <button
            type="button"
            class={joinedButtonClass}
            aria-label={t("new_entity", "Make a new one")}
            title={t("new_entity", "Make a new one")}
            aria-haspopup="dialog"
            onClick={() => setCreating(true)}
          >
            +
          </button>
        </Show>
        <Show when={props.onRemove}>
          <button
            type="button"
            class={joinedRemoveClass}
            aria-label={props.removeLabel}
            title={props.removeLabel}
            onClick={() => props.onRemove?.()}
          >
            ✕
          </button>
        </Show>
      </EntityPicker>
      <Show when={creating()}>
        <EntityCreateDialog
          groups={groups()}
          initial={props.initial}
          fill={props.fill}
          onClose={() => setCreating(false)}
          onCreated={(made) => {
            setCreating(false);
            if (getModel(definitions, made.type)?.kind === "Entity") rememberEntity(made);
            (props.onCreated ?? props.onPick)(made);
          }}
        />
      </Show>
    </div>
  );
}

/**
 * A dialog that makes a new entity of one of `types` (Entities, or Documents that can be made on their own): the types
 * first, when there are several (Back goes to them again), then the form of the one chosen, which starts with what
 * `initial` gives for it (and `fill`, with every item added in it); Save makes it and hands it to `onCreated`. For an
 * interface module that offers to make one where there is no field to put it in (a day of a calendar, say).
 */
export function NewEntityDialog(props: {
  types: string[];
  onCreated: (entity: Summary) => void;
  onClose: () => void;
  initial?: (type: string) => Record<string, unknown>;
  fill?: (item: FormData) => FormData;
}) {
  const definitions = useModels();
  const groups = createMemo(() => menuGroups(definitions, typeOptions(props.types)));
  return (
    <EntityCreateDialog
      groups={groups()}
      initial={props.initial}
      fill={props.fill}
      onClose={props.onClose}
      onCreated={(made) => {
        // (an entity is offered again when one is searched for; a document is not searched for)
        if (getModel(definitions, made.type)?.kind === "Entity") rememberEntity(made);
        props.onCreated(made);
      }}
    />
  );
}
