import { createEffect, createMemo, createSignal, onSettled, untrack, For, Match, Show, Switch } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";
import {
  createItemFormState,
  ItemFormProvider,
  useApi,
  useComponent,
  useItemForm,
  useModels,
  useTranslations,
} from "../../context";
import { kindRule, kindTint, spaceTint } from "../../primitives";
import {
  blankItem,
  cleanForSave,
  choicesOf,
  choiceValue,
  envOf,
  getModel,
  menuGroups,
  optionFor,
  resolveOptions,
} from "../../schema";
import type { Choice, Env, FormData, Path } from "../../schema";
import type {
  AnnotatedValueField,
  EmbeddedField,
  FieldDefinition,
  ModelDefinition,
  RelationField,
  RelationOption,
} from "../../types";
import { createItem, ApiError, problemsOf } from "../../api";
import type { Summary } from "../../api";
import { EntityPicker } from "./EntityPicker";
import { JsonEditor, LiteralEditor } from "./LiteralEditor";
import {
  addSlotClass,
  inputClass,
  joinedButtonClass,
  joinedRemoveClass,
  headBarClass,
  headButtonClass,
  headLabelClass,
  nestedClass,
  plainTint,
  smallButtonClass,
  typeChipClass,
} from "./styles";
import { TypeMenu } from "./TypeMenu";

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * Something nested: a head line with its type (a tinted chip), what it is called, a fold and a
 * remove button; under it, its fields, indented, with a rule in the colour of its type down the left.
 */
function Block(
  props: ParentProps<{
    type: string;
    label?: string;
    tint: string;
    rule: string;
    onRemove?: () => void;
  }>,
) {
  const { t, modelName } = useTranslations();
  const [folded, setFolded] = createSignal(false);
  return (
    <div class="flex w-full min-w-0 flex-col">
      <div class={headBarClass}>
        <span class={[typeChipClass, props.tint || plainTint]}>{modelName(props.type)}</span>
        <span class={headLabelClass}>{props.label}</span>
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
      <Show when={!folded()}>
        {/* (the rule starts at the bar: what is under it hangs from the head) */}
        <div class={["ml-2 pt-4", nestedClass, props.rule]}>{props.children}</div>
      </Show>
    </div>
  );
}

// (the names of the fields in a column on the left, their editors beside them)
const fieldGridClass = "grid w-full grid-cols-[10rem_minmax(0,1fr)] gap-x-6 gap-y-5";

/**
 * Whether a field has something in it, for its required mark: not nothing, an empty text or an empty
 * list; a thing that is only its type (an entity not yet chosen) is nothing, and so is an annotated
 * value without its value. (Only for the mark: whether it is valid is the API's to say.)
 */
function filled(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.some(filled);
  if (isObject(value)) {
    if ("value" in value) return filled(value.value);
    return Object.keys(value).some((key) => key !== "type");
  }
  return true;
}

/**
 * One labelled row of a form: the name on the left, the editor on the right. A required field has
 * a mark after its name, green once it is `met` (something is in it).
 */
function Row(
  props: ParentProps<{
    name: string;
    required?: boolean;
    met?: boolean;
    description?: string | null;
    bare?: boolean;
  }>,
) {
  return (
    <Show
      when={!props.bare}
      fallback={<div class="col-span-2 min-w-0">{props.children}</div>}
    >
      <dt class="pt-2 text-xs font-semibold text-slate-500 uppercase">
        {props.name}
        <Show when={props.required}>
          <span
            aria-hidden="true"
            class={["transition-colors", { "text-green-600": !!props.met }]}
          >
            {" *"}
          </span>
        </Show>
        <Show when={props.description}>
          <span class="mt-0.5 block text-xs font-normal text-slate-400 normal-case">{props.description}</span>
        </Show>
      </dt>
      <dd class="flex min-w-0 flex-col items-start gap-1">{props.children}</dd>
    </Show>
  );
}

/**
 * The editors of the fields of a model, each in its row, in the order of the model, for the
 * object at `path` of the form. `env` says what the type variables of a generic model stand for
 * here; `skip` leaves fields out, and `bare` is the field (a reified relation's target) shown
 * without its name, first: what the thing holds, then what is said of it.
 */
export function ModelFields(props: {
  model: ModelDefinition;
  path: Accessor<Path>;
  env: Env;
  skip?: string[];
  bare?: string;
}) {
  const form = useItemForm();
  const { fieldName } = useTranslations();
  const fields = () => [
    ...props.model.fields.filter((field) => field.key === props.bare),
    ...props.model.fields.filter((field) => field.key !== props.bare),
  ];
  return (
    <dl class={fieldGridClass}>
      <For each={fields()}>
        {(field) => (
          <Show when={!(props.skip ?? []).includes(field.key)}>
            <Row
              name={fieldName(props.model.name, field.name)}
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
              />
            </Row>
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
          required={props.model.requireLabel}
          onInput={(value) => form.set([...props.path(), "label"], value)}
        />
      </Show>
      <Show when={!props.title || (props.creating && props.model.createWithId)}>
        <dl class={fieldGridClass}>
          <Show when={!props.title}>
            <Row name={t("label", "Label")} required={props.model.requireLabel} met={text("label") !== ""}>
              {labelInput(inputClass)}
            </Row>
          </Show>
          <Show when={props.creating && props.model.createWithId}>
            <Row name={fieldName(props.model.name, "id")}>
              <input
                type="text"
                class={inputClass}
                aria-label={t("id", "ID")}
                value={text("id")}
                onInput={(event) => form.set([...props.path(), "id"], event.currentTarget.value)}
              />
            </Row>
          </Show>
        </dl>
      </Show>
      <ModelFields
        model={props.model}
        path={props.path}
        env={{}}
      />
    </div>
  );
}

/**
 * The label of the item as a heading: a box in large type, one line high, that grows a line at a
 * time as a long label wraps (to the width of the page, and again when that changes). A label is
 * one line of text, only wrapped: Enter makes no new line, and the line breaks of what is pasted
 * are spaces.
 */
function TitleBox(props: {
  value: string;
  label: string;
  required?: boolean;
  onInput: (value: string) => void;
}) {
  let box: HTMLTextAreaElement | undefined;
  // (as tall as what is in it: first none, so that it can shrink too)
  const fit = () => {
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${box.scrollHeight}px`;
  };
  createEffect(
    () => props.value,
    () => {
      fit();
    },
  );
  onSettled(() => {
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  });
  return (
    <textarea
      ref={box}
      rows={1}
      class="block w-full min-w-0 resize-none overflow-hidden border-b-[0.5px] border-slate-400/70 bg-transparent pt-1 pb-2 text-2xl leading-snug font-semibold placeholder:font-normal placeholder:text-slate-400 focus:border-slate-600 focus:outline-none"
      aria-label={props.label}
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
}) {
  const { fieldName } = useTranslations();
  const name = () => fieldName(props.modelName, props.field.name);
  return (
    <Switch fallback={<JsonEditor path={props.path} label={name()} />}>
      <Match when={props.field.kind === "literal"}>
        <LiteralEditor
          type={(props.field as Extract<FieldDefinition, { kind: "literal" }>).type}
          validators={(props.field as Extract<FieldDefinition, { kind: "literal" }>).validators}
          path={props.path}
          label={name()}
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

/** An embedded object: a menu of its types (a date is an exact date, a range...), then the fields of the one chosen */
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
  const choose = (choice: Choice) => {
    const next = getModel(definitions, choice.type);
    // (what the two types have in common is kept when the type is changed)
    const kept = Object.fromEntries(
      Object.entries(value() ?? {}).filter(([key]) => next?.fields.some((field) => field.key === key)),
    );
    form.set(props.path(), { ...kept, type: choice.type });
  };
  return (
    <div class="flex w-full min-w-0 flex-col">
      <Show
        when={value()}
        fallback={
          <TypeMenu
            groups={groups()}
            label={t("add_named", "Add {name}", { name: props.label })}
            buttonClass={addSlotClass}
            wide
            onChoose={choose}
          />
        }
      >
        {/* (the type chosen, which its menu changes, with the remove button joined on) */}
        <div class="inline-flex self-start overflow-hidden rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/60">
          <TypeMenu
            groups={groups()}
            label={modelName(String(value()!.type))}
            buttonClass="flex cursor-pointer items-center gap-1 px-2 py-1 text-xs font-semibold uppercase select-none hover:bg-slate-300/50 focus:bg-slate-300/50 focus:outline-none"
            onChoose={choose}
          />
          <Show when={!props.field.required}>
            <button
              type="button"
              class={joinedRemoveClass}
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
          <ModelFields model={model()!} path={props.path} env={{}} />
        </div>
      </Show>
    </div>
  );
}

/**
 * A relation: the things it holds (one, or a list), each its own editor, and a way to add one. A
 * relation to entities only is a search to find them; otherwise a menu of the types it can hold,
 * and the same inside each semantic space it can hold.
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
  const entityTypes = createMemo(() =>
    options().every((option) => option.kind === "entity")
      ? options().flatMap((option) => ("type" in option ? [option.type] : []))
      : [],
  );
  const items = () => {
    const at = form.get(props.path());
    if (props.field.many) return Array.isArray(at) ? at : [];
    return isObject(at) ? [at] : [];
  };
  const where = () => (props.field.many ? [...props.path(), items().length] : props.path());
  const canAdd = () => props.field.many || items().length === 0;
  const add = (choice: Choice) => {
    const option = optionFor(options(), choice.type);
    form.set(
      where(),
      choice.spaces.length === 0 && option
        ? blankItem(definitions, choice.type, envOf(option, props.env))
        : choiceValue(definitions, choice),
    );
  };
  const only = () => choicesOf(groups());
  return (
    <div class="flex w-full min-w-0 flex-col gap-4">
      <Show
        when={props.field.many}
        fallback={
          <Show when={items().length > 0}>
            <RelationItem
              path={props.path}
              options={options()}
              env={props.env}
              onRemove={() => form.remove(props.path())}
            />
          </Show>
        }
      >
        {/* (entities as chips side by side; anything bigger, a line of its own) */}
        <Show when={items().length > 0}>
          <div class="flex w-full min-w-0 flex-wrap items-start gap-x-2 gap-y-6">
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
          when={entityTypes().length > 0}
          fallback={
            <Show
              when={only().length > 0}
              fallback={
                <Show when={props.field.options.length > 0}>
                  <JsonEditor path={props.path} label={props.label} />
                </Show>
              }
            >
              <TypeMenu
                groups={groups()}
                label={
                  props.bare ? t("add", "Add") : t("add_named", "Add {name}", { name: props.label })
                }
                buttonClass={addSlotClass}
                wide
                onChoose={add}
              />
            </Show>
          }
        >
          <PickOrCreate
            types={entityTypes()}
            onPick={(entity) => form.set(where(), { type: entity.type, id: entity.id, label: entity.label })}
          />
        </Show>
      </Show>
    </div>
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
  return (
    <Switch fallback={<JsonEditor path={props.path} label={type()} />}>
      <Match when={model()?.kind === "Entity"}>
        <div
          class={[
            "flex min-w-0 flex-col items-start gap-3",
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
              removeLabel={t("remove_item", "Remove {name}", { name: label() ?? type() })}
            />
          </Show>
          <Show when={edgeModel() && value()?.id}>
            <div class={["ml-2", nestedClass, kindRule("Entity", model()?.interfaceMeta?.colour)]}>
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
          class={[
            "flex w-full min-w-0 flex-col rounded-sm border-[0.5px] border-slate-400/70",
            spaceTint(model()?.interfaceMeta?.colour, Math.floor(props.path().length / 2)),
          ]}
        >
          <div class="flex items-center justify-between">
            <span class="px-3 pt-2 text-xs font-semibold uppercase select-none">{modelName(type())}</span>
            <button
              type="button"
              class="cursor-pointer self-stretch px-3 pt-1 text-xs text-red-800 select-none hover:bg-red-400/30"
              aria-label={t("remove_item", "Remove {name}", { name: modelName(type()) })}
              onClick={props.onRemove}
            >
              ✕
            </button>
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
        >
          <ItemFields model={model()!} path={props.path} />
        </Block>
      </Match>
      <Match when={model()}>
        {/* (a reified relation, a conjunction: its own fields, and what it holds without the name of the field) */}
        <Block
          type={type()}
          tint={kindTint(model()?.kind, model()?.interfaceMeta?.colour)}
          rule={kindRule(model()?.kind, model()?.interfaceMeta?.colour)}
          onRemove={props.onRemove}
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
 * A dialog to make an entity of `type` without leaving the form: its own form (a fresh state, so
 * nothing of the item behind it is touched), and Save makes the entity and hands it back.
 */
function EntityCreateDialog(props: {
  type: string;
  onCreated: (entity: Summary) => void;
  onClose: () => void;
}) {
  const Modal = useComponent("Modal");
  const api = useApi();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const state = createItemFormState(blankItem(definitions, untrack(() => props.type)));
  const model = () => getModel(definitions, props.type);
  const [saving, setSaving] = createSignal(false);
  const [problems, setProblems] = createSignal<string[]>([]);
  async function save() {
    setSaving(true);
    setProblems([]);
    try {
      const body = cleanForSave(definitions, state.plain());
      delete body.type;
      props.onCreated(await createItem(api, props.type, body));
    } catch (error) {
      setProblems(error instanceof ApiError ? problemsOf(error) : [String(error)]);
    } finally {
      setSaving(false);
    }
  }
  return (
    <Modal title={t("new_item", "New {type}", { type: modelName(props.type) })} onClose={props.onClose} size="lg">
      <ItemFormProvider state={state}>
        <div class="flex flex-col gap-6 p-6">
          <Show when={problems().length > 0}>
            <ul
              role="alert"
              class="list-disc rounded-sm border-[0.5px] border-red-700/60 bg-red-100/70 p-3 pl-7 text-sm"
            >
              <For each={problems()}>{(problem) => <li>{problem}</li>}</For>
            </ul>
          </Show>
          <Show when={model()}>
            <ItemFields model={model()!} path={() => []} creating title />
          </Show>
          <div class="flex justify-end gap-2">
            <button type="button" class={smallButtonClass} onClick={props.onClose}>
              {t("cancel", "Cancel")}
            </button>
            <button
              type="button"
              class={smallButtonClass}
              disabled={saving()}
              onClick={() => void save()}
            >
              {t("save", "Save")}
            </button>
          </div>
        </div>
      </ItemFormProvider>
    </Modal>
  );
}

/**
 * Finds an entity of one of `types`, or makes a new one: a + button joined on to the end of the
 * search (a menu of the types, when there are several) opens the form for the entity in a dialog;
 * the entity made is chosen as if it had been found. With `onRemove`, a remove button is joined
 * on after it (for a place in a list that has no entity yet).
 */
function PickOrCreate(props: {
  types: string[];
  onPick: (entity: Summary) => void;
  onRemove?: () => void;
  removeLabel?: string;
}) {
  const definitions = useModels();
  const { t } = useTranslations();
  const [creating, setCreating] = createSignal<string>();
  const groups = createMemo(() => menuGroups(definitions, typeOptions(props.types)));
  return (
    <div class="w-full min-w-0">
      <EntityPicker types={props.types} onPick={props.onPick}>
        <TypeMenu
          groups={groups()}
          label="+"
          title={t("new_entity", "Make a new one")}
          buttonClass={joinedButtonClass}
          alignRight
          onChoose={(choice) => setCreating(choice.type)}
        />
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
          type={creating()!}
          onClose={() => setCreating(undefined)}
          onCreated={(entity) => {
            setCreating(undefined);
            props.onPick(entity);
          }}
        />
      </Show>
    </div>
  );
}
