import { action, children, createEffect, createMemo, createOptimistic, createRenderEffect, createSignal, onSettled, untrack, For, Match, Show, Switch } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";
import type { JSX } from "@solidjs/web";
import {
  createItemFormState,
  ItemFormProvider,
  useApi,
  useComponent,
  useItemForm,
  useModels,
  useModules,
  useToasts,
  useTranslations,
} from "../../context";
import type { ItemFormState } from "../../context";
import { buttonClass, kindRule, kindTint, spaceTint } from "../../primitives";
import {
  blankItem,
  createFormHooks,
  derivesLabel,
  isAutomatic,
  cleanForSave,
  choicesOf,
  choiceValue,
  inSpaces,
  spaceOptions,
  envOf,
  filled,
  getModel,
  labelledContents,
  headlessIn,
  lengthBound,
  menuGroups,
  optionFor,
  reachFor,
  relationLayout,
  resolveOptions,
  wrapEntity,
  editableFields,
  urlsField,
  companionToSend,
  creationContext,
  entitySlotPaths,
  formPathOf,
  getAt,
  isEntitySlot,
  offeredCompanions,
  refusalsByForm,
  sentPartIndexes,
  startCompanion,
  withNewEntity,
} from "../../schema";
import type {
  Choice,
  CompanionSent,
  CreationContext,
  Env,
  FormData,
  LabelledContent,
  MenuGroup,
  Path,
} from "../../schema";
import type {
  AnnotatedValueField,
  CompanionDefinition,
  EmbeddedField,
  FieldDefinition,
  ModelDefinition,
  NewItemForm,
  RelationField,
  RelationOption,
} from "../../types";
import { ApiError, createItem, createWithCompanions } from "../../api";
import type { Summary } from "../../api";
import { CITATION, CitationChips, CitationPicker } from "../Citation";
import { EntityPicker } from "./EntityPicker";
import { EditItemFields, NewItemFields } from "./NewItemActions";
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
  spacePaddingClass,
  spaceTypeClass,
  typeChipClass,
} from "./styles";
import { TypeChooser, TypeGrid, TypeMenu, useSelectTitle } from "./TypeMenu";
import { revealAdded } from "./reveal";
import { RetypeButtons } from "./Retype";
import { ClipButtons, EmbeddedPasteSlot, RelationPasteSlot, useClipActions } from "./Clip";
import { FieldProblems, useRowProblems, useSaveChecks } from "./Problems";
import { Customised, PartActions } from "../Customised";
import { Head } from "../Head";
import { holdsId, NestingProvider, startsFolded, useNesting, useRevealed } from "../nesting";

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
    /**
     * What leads the bar, straight after its type: what an interface module adds to the part (`partActions`), apart
     * from the buttons that cut, copy and remove it at the other end, so that one is not pressed for the other
     */
    lead?: JSX.Element;
    /** Open though it is nested deep enough to start folded (what is to be shown is inside it) */
    startOpen?: boolean;
    /** What it holds, shown as chips on the bar while it is folded (for what has no label of its own to show there) */
    contents?: LabelledContent[];
  }>,
) {
  const { t, modelName, fieldName } = useTranslations();
  const ReferenceChip = useComponent("ReferenceChip");
  // (a block this deep starts folded, and what it holds is made when it is unfolded: see `nesting.ts`)
  const nesting = useNesting();
  const { folds } = useItemForm();
  const [folded, setFolded] = createSignal(untrack(folds.allFolded) || (startsFolded(nesting) && !untrack(() => props.startOpen)));
  // (the button in the console: not a click from before this block was made)
  const orderMadeAfter = untrack(folds.order);
  createEffect(folds.order, (order) => {
    if (order && order !== orderMadeAfter) setFolded(order.fold || startsFolded(nesting));
  });
  onSettled(() => folds.register());
  // (made once: each read of a prop that is elements makes them again, and one read only to ask whether there
  // are any left a second set, of which the browser said "Hydration key miss ... a detached element was created")
  const buttons = children(() => props.buttons);
  const lead = children(() => props.lead);
  return (
    // (scrolled to, it stops clear of the console bar, with room for a line of what it is in)
    <div class="flex w-full min-w-0 scroll-mt-28 flex-col" data-item-id={props.itemId}>
      <div class={headBarClass}>
        <span data-type-info={props.type} data-tint class={[typeChipClass, props.tint || plainTint, props.rule]}>
          {modelName(props.type)}
        </span>
        <div class={buttons() ? headRestOpenClass : headRestClass}>
          {lead()}
          {/* (the grey of the bar, with the label in it, folds it; folded, a ▸ says so) */}
          <div class="relative flex min-w-0 flex-1">
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
            {/* (over the button, not in it, as a chip can be a link; a click goes through to the button) */}
            <Show when={folded() && props.contents?.length}>
              <div data-folded-contents class="pointer-events-none absolute inset-y-0 right-2 left-7 flex items-center gap-2 overflow-hidden">
                <For each={props.contents}>
                  {(item) => (
                    <span class="flex min-w-0 items-center gap-1.5">
                      <For each={item.fields}>
                        {(field) => (
                          <span class="shrink-0 text-xs font-semibold text-slate-500 uppercase">{fieldName(field.model, field.name)}</span>
                        )}
                      </For>
                      <ReferenceChip type={item.type} label={item.label} />
                    </span>
                  )}
                </For>
              </div>
            </Show>
          </div>
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
        <div class={["ml-2 pt-4", nestedClass, props.rule]}>
          <NestingProvider value={nesting + 1}>{props.children}</NestingProvider>
        </div>
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
    /** Drawn before the name */
    icon?: JSX.Element;
  }>,
) {
  const problems = useRowProblems(() => props.path);
  const bad = () => problems().length > 0;
  return (
    <Show
      when={!props.bare}
      fallback={
        <div class={fieldRowClass} data-problem={bad() ? "" : undefined}>
          <div class="col-span-full min-w-0">
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
          <Show when={props.icon} fallback={props.name}>
            {props.icon}
            {props.name}
          </Show>
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
  /** Rows before those of the fields (an interface module's: each a `FieldRow`) */
  before?: JSX.Element;
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
  const editable = () => editableFields(props.model);
  const fields = () => [
    ...editable().filter((field) => field.key === props.bare),
    ...editable().filter((field) => field.key !== props.bare),
  ];
  return (
    <dl class={fieldGridClass}>
      {props.before}
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
 * What a Document or an Entity has beside its fields: its label and, if it can have them, its URIs.
 * With `title` (the item the page or the dialog is for) the label is a heading,
 * a large box above the rest, rather than a row like the fields.
 */
export function ItemFields(props: {
  model: ModelDefinition;
  path: Accessor<Path>;
  title?: boolean;
  /** The cursor starts in the box of the label (`title`), as on the page of a new item */
  focusLabel?: boolean;
  /** It is the form that edits an item: for the rows interface modules add (`editItemFields`) */
  editing?: boolean;
  /** The form of the new item it is (the page's, or a dialog's): for the rows interface modules add (`newItemFields`) */
  newItem?: NewItemForm;
}) {
  const form = useItemForm();
  const { t } = useTranslations();
  const urls = () => urlsField(props.model);
  const text = (key: string) => {
    const value = form.get([...props.path(), key]);
    return typeof value === "string" ? value : "";
  };
  // (a label its template works out: locked, with a pencil to write it by hand, and ↺ to have it worked out again.
  // implementation_docs/label-templates.md)
  const derived = () => derivesLabel(props.model);
  const automatic = () => {
    const node = form.get(props.path());
    return derived() && typeof node === "object" && node !== null && isAutomatic(node as FormData);
  };
  const setAutomatic = (auto: boolean) => form.set([...props.path(), "labelAuto"], auto);
  const labelInput = (classes: string) => (
    <div class="flex w-full min-w-0 items-center gap-1">
      <input
        type="text"
        class={[classes, { "bg-slate-100/80 text-slate-600": automatic() }]}
        aria-label={t("label", "Label")}
        aria-required={props.model.requireLabel ? "true" : undefined}
        readonly={automatic()}
        placeholder={automatic() ? t("label_worked_out", "Worked out from what is filled in") : undefined}
        value={text("label")}
        onInput={(event) => form.set([...props.path(), "label"], event.currentTarget.value)}
      />
      <Show when={derived()}>
        <LabelLock automatic={automatic()} onChange={setAutomatic} />
      </Show>
    </div>
  );
  return (
    <div class="flex flex-col gap-5">
      <Show when={props.title}>
        <TitleBox
          value={text("label")}
          label={t("label", "Label")}
          path={[...props.path(), "label"]}
          required={props.model.requireLabel}
          focus={props.focusLabel}
          lockable={derived()}
          readOnly={automatic()}
          onLock={setAutomatic}
          placeholder={automatic() ? t("label_worked_out", "Worked out from what is filled in") : undefined}
          onInput={(value) => form.set([...props.path(), "label"], value)}
        />
      </Show>
      <Show when={!props.title || urls()}>
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
          <Show when={urls()}>
            {(field) => (
              <FieldRow name={t("uris", "URIs")} path={[...props.path(), field().key]}>
                <LiteralEditor
                  type={{ type: "list", item: field().item }}
                  path={() => [...props.path(), field().key]}
                  label={t("uris", "URIs")}
                />
              </FieldRow>
            )}
          </Show>
        </dl>
      </Show>
      {/* (a rule between the label's row and the first field, as between fields; the heading has its own) */}
      <div class={{ [`border-t pt-5 ${fieldRuleClass}`]: !props.title || !!urls() }}>
        <ModelFields
          model={props.model}
          path={props.path}
          env={{}}
          lead={
            <>
              <Show when={props.newItem}>
                {(form) => <NewItemFields type={props.model.name} model={props.model} form={form()} />}
              </Show>
              <Show when={props.editing}>
                <EditItemFields type={props.model.name} model={props.model} get={form.get} />
              </Show>
            </>
          }
        />
      </div>
    </div>
  );
}

/**
 * The button beside a label that a template works out: the pencil (it is locked: write it by hand), or ↺ (it was
 * written by hand: have it worked out again from what the item holds)
 */
function LabelLock(props: { automatic: boolean; onChange: (automatic: boolean) => void }) {
  const { t } = useTranslations();
  const name = () =>
    props.automatic
      ? t("label_write_by_hand", "Write the label by hand")
      : t("label_work_out", "Work the label out from what is filled in");
  return (
    <button
      type="button"
      class={buttonClass("ordinary", "sm", true)}
      aria-label={name()}
      title={name()}
      aria-pressed={props.automatic ? "false" : "true"}
      onClick={() => props.onChange(!props.automatic)}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="square"
        class="size-3.5"
        aria-hidden="true"
      >
        <Show
          when={props.automatic}
          fallback={<path d="M4 12a8 8 0 1 0 2.5-5.8M4 4v4h4" />}
        >
          <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
        </Show>
      </svg>
    </button>
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
  focus?: boolean;
  /** A label its template can work out: `LabelLock` beside it */
  lockable?: boolean;
  /** Worked out by its template: not typed in (`LabelLock` unlocks it) */
  readOnly?: boolean;
  onLock?: (automatic: boolean) => void;
  placeholder?: string;
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
    // (not a label worked out by its template, which is not typed in)
    if (props.focus && !props.readOnly) box?.focus();
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
    <div class="relative" data-problem={bad() ? "" : undefined}>
      <textarea
        ref={box}
        rows={1}
        readonly={props.readOnly}
        class={[
          "block w-full min-w-0 resize-none overflow-hidden border-b-[0.5px] bg-transparent pt-1 pb-2 text-2xl leading-snug font-semibold placeholder:font-normal focus:outline-none",
          {
            // (room for the lock at the right)
            "pr-9": !!props.lockable,
            "text-slate-600": !!props.readOnly,
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
        placeholder={props.placeholder ?? `${props.label}${props.required ? " *" : ""}`}
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
      <Show when={props.lockable}>
        <div class="absolute top-1.5 right-0">
          <LabelLock automatic={!!props.readOnly} onChange={(auto) => props.onLock?.(auto)} />
        </div>
      </Show>
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
      <Match when={props.field.kind === "annotatedValue" && (props.field as AnnotatedValueField).many}>
        <AnnotatedListEditor field={props.field as AnnotatedValueField} path={props.path} label={name()} />
      </Match>
      <Match when={props.field.kind === "annotatedValue" && !(props.field as AnnotatedValueField).many}>
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

/** A list of values with fields of their own: each as one is, with a button to remove it, and one to add */
function AnnotatedListEditor(props: { field: AnnotatedValueField; path: Accessor<Path>; label: string }) {
  const form = useItemForm();
  const { t } = useTranslations();
  const items = () => (form.get(props.path()) as unknown[] | undefined) ?? [];
  return (
    <div class="flex w-full flex-col gap-2">
      {/* (by place, not by value: the value changes with every key) */}
      <For each={items()} keyed={false}>
        {(_, index) => (
          <div class="flex w-full items-start gap-2">
            <AnnotatedEditor
              field={props.field}
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
        )}
      </For>
      <button
        type="button"
        class={addSlotClass}
        aria-label={t("add_to", "Add to {name}", { name: props.label })}
        onClick={(event) => {
          const slot = event.currentTarget;
          form.set([...props.path(), items().length], {});
          // (the new one is just before the slot)
          revealAdded(() => slot.previousElementSibling);
        }}
      >
        + {t("add", "Add")}
      </button>
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
            typeInfo={String(value()!.type)}
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
  // (what the form is given and may not change: the new entity in a companion's part)
  const fixed = () => form.fixed?.(props.path()) ?? false;
  // (a list as long as it may be, `MaxLen`, has no way to add more)
  const canAdd = () =>
    !fixed() &&
    (props.field.many ? items().length < (lengthBound(props.field.validators, "max") ?? Infinity) : items().length === 0);
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
  // (in the box of types, under a semantic space's types: what fits inside it, pasted in a new space of that kind)
  const pasteInSpace = (spaces: string[], close: () => void) => (
    <RelationPasteSlot
      options={spaceOptions(options(), props.env, spaces) ?? []}
      env={props.env}
      onPaste={(pasted) => {
        close();
        form.set(where(), inSpaces(definitions, spaces, pasted));
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
                fixed={fixed()}
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
                  fixed={fixed()}
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
                inSpace={pasteInSpace}
              >
                {pasteSlot()}
              </TypeChooser>
            </Show>
          }
        >
          <div class="flex w-full min-w-0 flex-col gap-2">
            <PickOrCreate
              types={searched()}
              context={() => creationContext(form.plain(), props.path())}
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
  /** It is given, and not to be changed or removed (`ItemFormState.fixed`) */
  fixed?: boolean;
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
  // (the part the page is to scroll to is inside it: it starts open, however deep)
  const revealed = useRevealed();
  const holdsRevealed = () => {
    const id = revealed();
    return id !== null && holdsId(value(), id);
  };
  return (
    <Switch fallback={<JsonEditor path={props.path} label={type()} />}>
      <Match when={type() === CITATION}>
        {/* (a citation of another document: what it cites, chosen by a search and never typed) */}
        <Show
          when={value()?.targetId}
          fallback={
            <CitationPicker
              cites={(() => {
                const found = option();
                return found && "cites" in found ? (found.cites ?? []) : [];
              })()}
              onPick={(cited) => form.set(props.path(), { ...value(), ...cited })}
              onRemove={props.fixed ? undefined : props.onRemove}
            />
          }
        >
          <CitationChips
            value={value()!}
            onRemove={props.fixed ? undefined : props.onRemove}
            onSeen={() => form.set([...props.path(), "changedSinceCited"], false)}
          />
        </Show>
      </Match>
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
                context={() => creationContext(form.plain(), props.path())}
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
            <Show
              when={!props.fixed}
              fallback={
                // (the new entity, in a companion's part: as it is typed, and nothing to do to it)
                <ReferenceChip
                  type={type()}
                  label={label() || t("companion_new_entity", "The new {type}", { type: modelName(type()) })}
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
            <span data-type-info={type()} class={spaceTypeClass}>{modelName(type())}</span>
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
          <div class={["flex min-w-0 flex-1 flex-col gap-4", spacePaddingClass]}>
            <ModelFields model={model()!} path={props.path} env={childEnv()} bare="contents" />
          </div>
        </div>
      </Match>
      <Match when={model()?.kind === "Document" || model()?.kind === "ReifiedRelationDocument"}>
        {/* (a model can name an editor of its own for where it is held, in an interface module: the unreconciled
            mentions of review do) */}
        <Customised
          slot="editCard"
          type={type()}
          props={{
            type: type(),
            model: model()!,
            label: label() ?? "",
            get path() {
              return props.path();
            },
            get value() {
              return value() ?? {};
            },
            onChange: (next) => form.set(props.path(), next),
            onRemove: props.onRemove,
            get option() {
              return option();
            },
          }}
          fallback={
        <Block
          type={type()}
          label={label()}
          tint={kindTint(model()?.kind, model()?.interfaceMeta?.colour)}
          rule={kindRule(model()?.kind, model()?.interfaceMeta?.colour)}
          // (a part of a companion is given: not removed, cut or retyped, so that the new entity's place stays)
          onRemove={props.fixed ? undefined : props.onRemove}
          clip={props.fixed ? undefined : clip}
          itemId={typeof value()?.id === "string" ? String(value()!.id) : undefined}
          startOpen={holdsRevealed()}
          buttons={
            <RetypeButtons
              type={type()}
              // (none to change to)
              options={props.fixed ? [] : props.options}
              name={label() || modelName(type())}
              buttonClass={[headMenuButtonClass, "text-slate-500 hover:bg-slate-400/30"].join(" ")}
              value={value}
              onRetype={(next) => form.set(props.path(), next)}
            />
          }
        >
          <ItemFields model={model()!} path={props.path} />
        </Block>
          }
        />
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
          // (found by its id too, as a document is: `?show=` scrolls to it)
          itemId={typeof value()?.id === "string" ? String(value()!.id) : undefined}
          startOpen={holdsRevealed()}
          contents={labelledContents(value(), definitions)}
          // (what an interface module adds to the part's bar: a button to confirm it, say)
          lead={
            <PartActions
              type={type()}
              item={value() ?? {}}
              page="edit"
              place="bar"
              changed={form.changed}
              replace={(next) => form.set(props.path(), next)}
            />
          }
        >
          <ModelFields
            model={model()!}
            path={props.path}
            env={childEnv()}
            bare={model()?.kind === "ReifiedRelation" ? "target" : undefined}
            // (what an interface module shows of the part that is not to be changed: the URIs a toolchain gave)
            before={<PartActions type={type()} item={value() ?? {}} page="edit" place="body" Row={FieldRow} />}
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
  /** Where it is made (the form behind, and the relation): which companions are offered. None: on its own */
  context?: () => CreationContext | null;
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
            context={props.context}
            onBack={choices().length > 1 ? () => setType(undefined) : undefined}
            onCreated={props.onCreated}
            onClose={props.onClose}
          />
        )}
      </Show>
    </Modal>
  );
}

/** A companion offered in the form of a new entity: its declaration, what it started as, and its own form */
interface CompanionForm {
  companion: CompanionDefinition;
  started: FormData;
  state: ItemFormState;
}

/**
 * The companions offered with a new entity of `type` (implementation_docs/companion-documents.md), each with a form of its
 * own that follows the entity's label as it is typed (the new entity is in each part's place for it), for
 * `CompanionSections` to show and `saveWithCompanions` to send
 */
function useCompanionForms(
  type: string,
  entity: ItemFormState,
  context: CreationContext | null,
): CompanionForm[] {
  const definitions = useModels();
  const modules = useModules();
  const label = () => {
    const value = entity.get(["label"]);
    return typeof value === "string" ? value : "";
  };
  return offeredCompanions(definitions, type, context).map((companion) => {
    const started = startCompanion(definitions, companion, { type, label: untrack(label) }, context);
    const fixed = (path: Path) =>
      // (its parts are given: none added or taken away; and the entity in each)
      (companion.field !== null && path.length === 1 && path[0] === companion.field.key) ||
      isEntitySlot(companion, (at) => state.get(at), path);
    const state: ItemFormState = createItemFormState(started, {
      binder: createFormHooks(definitions, modules.labelFormatter),
      fixed,
    });
    // (the entity's label as it is typed, into each of its places: only the label is followed)
    createEffect(label, (now) =>
      untrack(() => {
        const document = state.plain();
        const next = withNewEntity(definitions, companion, document, { type, label: now });
        for (const path of entitySlotPaths(companion, document)) {
          if (JSON.stringify(getAt(document, path)) !== JSON.stringify(getAt(next, path))) state.set(path, getAt(next, path));
        }
      }),
    );
    return { companion, started, state };
  });
}

/** What of the companions is to be sent (those with a part changed), with what is checked before (the entity kept in) */
function companionsToSend(definitions: ReturnType<typeof useModels>, forms: CompanionForm[]) {
  return forms.flatMap((form) => {
    const now = form.state.plain();
    const document = companionToSend(definitions, form.companion, form.started, now);
    if (!document) return [];
    delete document.type;
    return [
      {
        form,
        document: cleanForSave(definitions, document),
        sent: { companion: form.companion, parts: sentPartIndexes(definitions, form.companion, form.started, now) },
      },
    ];
  });
}

/**
 * The companions offered with a new entity of `type` (`entity` is its form; `context` where it is made, `null` on its
 * own), and what saving them takes: `prepare` checks each that has a part changed and gives what is to be sent (or
 * `null`: something is wrong, and shown); `refused` shows a 422 of the route in the form each problem is about (it
 * gives `false` for an answer that is not one); `madeText` is the toast's text. For the dialog that makes an entity
 * and the page of a new one (`ItemForm`)
 */
export function useCompanions(
  type: string,
  entity: ItemFormState,
  context: CreationContext | null,
  root: () => HTMLElement | undefined,
) {
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const forms = useCompanionForms(type, entity, context);
  const checks = forms.map((entry) =>
    useSaveChecks(entry.state, root, {
      item: () =>
        companionToSend(definitions, entry.companion, entry.started, entry.state.plain(), { keepEntity: true }) ??
        entry.state.plain(),
      place: (path) =>
        formPathOf(
          entry.companion,
          sentPartIndexes(definitions, entry.companion, entry.started, entry.state.plain()),
          path,
        ),
    }),
  );
  let sending: ReturnType<typeof companionsToSend> = [];
  return {
    forms,
    /** Whether any has been changed (reactive): the page asks before it is left */
    edited: () => forms.some((entry) => entry.state.edited()),
    prepare(): { name: string; document: FormData }[] | null {
      sending = companionsToSend(definitions, forms);
      for (const each of sending) {
        if (!checks[forms.indexOf(each.form)]!.check()) return null;
      }
      return sending.map((each) => ({ name: each.form.companion.name, document: each.document }));
    },
    refused(error: unknown, entityChecks: { refused: (error: unknown) => void }): boolean {
      if (!(error instanceof ApiError) || error.status !== 422 || sending.length === 0) return false;
      const sent: CompanionSent[] = sending.map((each) => each.sent);
      refusalsByForm(error.detail, sent).forEach((detail, index) => {
        if (detail === null) return;
        const refusal = new ApiError(422, detail, error.body);
        if (index === 0) entityChecks.refused(refusal);
        else checks[forms.indexOf(sending[index - 1]!.form)]!.refused(refusal);
      });
      return true;
    },
    madeText(made: { item: Summary; companions: Summary[] }): string {
      const named = { type: modelName(made.item.type), label: made.item.label };
      if (made.companions.length === 0) return t("toast_created", "{type} “{label}” created", named);
      return t("toast_created_with", "{type} “{label}” created, with {others}", {
        ...named,
        others: made.companions
          .map((c) => t("toast_item", "{type} “{label}”", { type: modelName(c.type), label: c.label }))
          .join(", "),
      });
    },
  };
}

/**
 * The companions under the form of a new entity: each a document with its own head (its type, its label as it is
 * worked out) and fields, said to be written only if something in it is filled in
 */
export function CompanionSections(props: { forms: CompanionForm[]; entity: string }) {
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  return (
    <For each={props.forms}>
      {(entry) => {
        const model = getModel(definitions, entry.companion.document);
        const colour = model?.interfaceMeta?.colour;
        const label = () => {
          const value = entry.state.get(["label"]);
          return typeof value === "string" ? value : undefined;
        };
        return (
          <Show when={model}>
            <section class="flex flex-col gap-2" data-companion={entry.companion.name}>
              <p class="text-xs font-semibold text-slate-500 uppercase">
                {t("companion_offered", "Also made with the {entity}, if anything in it is filled in", {
                  entity: modelName(props.entity),
                })}
              </p>
              <ItemFormProvider state={entry.state}>
                <Head
                  type={entry.companion.document}
                  tint={kindTint(model!.kind, colour)}
                  rule={kindRule(model!.kind, colour)}
                  label={label()}
                />
                <div class={["mt-3 ml-2", nestedClass, kindRule(model!.kind, colour)]}>
                  <ItemFields model={model!} path={() => []} />
                </div>
              </ItemFormProvider>
            </section>
          </Show>
        );
      }}
    </For>
  );
}

/**
 * The form of an entity of `type` in the dialog: its own form (a fresh state, so nothing of the item
 * behind it is touched), and Save makes the entity and hands it back. With `onBack` (it was chosen
 * from the types) the cursor goes into the form, and Back goes to the types again. Under it, the companions
 * offered where it is made (`context`): those filled in are made with it, in one transaction
 */
function EntityCreateForm(props: {
  type: string;
  initial?: (type: string) => Record<string, unknown>;
  fill?: (item: FormData) => FormData;
  context?: () => CreationContext | null;
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
  const modules = useModules();
  const state = createItemFormState(fill ? fill(started) : started, {
    fill,
    binder: createFormHooks(definitions, modules.labelFormatter),
  });
  const model = getModel(definitions, type);
  // (while it is being made: back to false when that is over, whatever the answer)
  const [saving, setSaving] = createOptimistic(false);
  const toasts = useToasts();
  let root: HTMLDivElement | undefined;
  const checks = useSaveChecks(state, () => root);
  const companions = useCompanions(type, state, untrack(() => props.context?.() ?? null), () => root);
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
  const make = action(function* (body: FormData, sending: { name: string; document: FormData }[]) {
    setSaving(true);
    if (sending.length === 0) {
      const item = (yield sender ? sender(body) : createItem(api, type, body)) as Summary;
      return { item, companions: [] as Summary[] };
    }
    return (yield createWithCompanions(api, type, body, sending)) as { item: Summary; companions: Summary[] };
  });
  async function save() {
    if (!checks.check()) return;
    const sending = companions.prepare();
    if (sending === null) return;
    if (sending.length > 0 && sender) {
      // (a module sends the entity its own way: what is written with it cannot go that way too)
      toasts?.show(
        t("companion_not_sent", "Not saved: this {type} is sent another way, and cannot be made with what is filled in under it", {
          type: modelName(type),
        }),
        "error",
      );
      return;
    }
    const body = cleanForSave(definitions, state.plain());
    delete body.type;
    let made: { item: Summary; companions: Summary[] };
    try {
      made = await make(body, sending);
    } catch (error) {
      if (!companions.refused(error, checks)) checks.refused(error);
      return;
    }
    toasts?.show(companions.madeText(made));
    props.onCreated(made.item);
  }
  onSettled(() => {
    // (the types it was chosen from are gone, and the cursor with them: into the form)
    if (props.onBack) root?.querySelector<HTMLElement>("input, textarea, select")?.focus();
  });
  return (
    <div ref={root} class="flex flex-col gap-6 p-6">
      <ItemFormProvider state={state}>
        <Show when={model}>
          <ItemFields model={model!} path={() => []} title newItem={newItemForm} />
        </Show>
      </ItemFormProvider>
      <Show when={companions.forms.length > 0}>
        <CompanionSections forms={companions.forms} entity={type} />
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
  /** Where a new one is made (the form it is in, and the relation): which companions are offered with it */
  context?: () => CreationContext | null;
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
          context={props.context}
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
