import { createMemo, createSignal, untrack, For, Match, Show, Switch } from "solid-js";
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
import { kindTint, spaceTint } from "../../primitives";
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
import { inputClass, smallButtonClass } from "./styles";
import { TypeMenu } from "./TypeMenu";

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** A box for something nested: its type at the head (tinted), what it is called, a fold and a remove button */
function Block(
  props: ParentProps<{
    type: string;
    label?: string;
    tint: string;
    onRemove?: () => void;
  }>,
) {
  const { t, modelName } = useTranslations();
  const [folded, setFolded] = createSignal(false);
  return (
    <div class="w-full rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/50">
      <div class="flex items-stretch border-b-[0.5px] border-slate-400/70">
        <span
          class={[
            "flex shrink-0 items-center px-3 py-1 text-xs font-semibold uppercase select-none",
            props.tint,
          ]}
        >
          {modelName(props.type)}
        </span>
        <span class="min-w-0 flex-1 truncate px-3 py-1 text-sm">{props.label}</span>
        <button
          type="button"
          class="cursor-pointer px-3 text-xs select-none hover:bg-slate-400/30"
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
            class="cursor-pointer px-3 text-xs text-red-800 select-none hover:bg-red-400/30"
            aria-label={t("remove_item", "Remove {name}", { name: modelName(props.type) })}
            onClick={() => props.onRemove?.()}
          >
            ✕
          </button>
        </Show>
      </div>
      <Show when={!folded()}>
        <div class="flex flex-col gap-2 p-3">{props.children}</div>
      </Show>
    </div>
  );
}

/** One labelled row of a form: the name on the left, the editor on the right */
function Row(props: ParentProps<{ name: string; required?: boolean; description?: string | null; bare?: boolean }>) {
  return (
    <Show
      when={!props.bare}
      fallback={<div class="col-span-2 min-w-0">{props.children}</div>}
    >
      <dt class="pt-1 text-xs font-semibold text-slate-500 uppercase" title={props.description ?? undefined}>
        {props.name}
        <Show when={props.required}>
          <span aria-hidden="true"> *</span>
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
 * without its name.
 */
export function ModelFields(props: {
  model: ModelDefinition;
  path: Accessor<Path>;
  env: Env;
  skip?: string[];
  bare?: string;
}) {
  const { fieldName } = useTranslations();
  return (
    <dl class="grid w-full grid-cols-[10rem_minmax(0,1fr)] gap-x-4 gap-y-2">
      <For each={props.model.fields}>
        {(field) => (
          <Show when={!(props.skip ?? []).includes(field.key)}>
            <Row
              name={fieldName(props.model.name, field.name)}
              required={field.required}
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

/** What a Document or an Entity has beside its fields: its label (and, to make one, its id if it can be chosen) */
export function ItemFields(props: {
  model: ModelDefinition;
  path: Accessor<Path>;
  /** Show the id too, for an item that is being made */
  creating?: boolean;
}) {
  const form = useItemForm();
  const { t, fieldName } = useTranslations();
  const text = (key: string) => {
    const value = form.get([...props.path(), key]);
    return typeof value === "string" ? value : "";
  };
  return (
    <div class="flex flex-col gap-2">
      <dl class="grid w-full grid-cols-[10rem_minmax(0,1fr)] gap-x-4 gap-y-2">
        <Row name={t("label", "Label")} required={props.model.requireLabel}>
          <input
            type="text"
            class={inputClass}
            aria-label={t("label", "Label")}
            value={text("label")}
            onInput={(event) => form.set([...props.path(), "label"], event.currentTarget.value)}
          />
        </Row>
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
      <ModelFields
        model={props.model}
        path={props.path}
        env={{}}
      />
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
    <div class="flex w-full flex-col gap-2">
      <div class="flex items-center gap-2">
        <TypeMenu
          groups={groups()}
          label={
            value()
              ? modelName(String(value()!.type))
              : t("add_named", "Add {name}", { name: props.label })
          }
          onChoose={choose}
        />
        <Show when={value() && !props.field.required}>
          <button
            type="button"
            class={smallButtonClass}
            aria-label={t("remove_item", "Remove {name}", { name: props.label })}
            onClick={() => form.remove(props.path())}
          >
            ✕
          </button>
        </Show>
      </div>
      <Show when={model()}>
        <div class="w-full pl-4">
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
    <div class="flex w-full flex-col items-start gap-2">
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
        <div class="flex w-full flex-col items-start gap-2">
          <Show
            when={value()?.id}
            fallback={
              <div class="flex w-full items-center gap-2">
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
                />
                <button
                  type="button"
                  class={smallButtonClass}
                  aria-label={t("remove_item", "Remove {name}", { name: modelName(type()) })}
                  onClick={props.onRemove}
                >
                  ✕
                </button>
              </div>
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
            <div class="w-full pl-4">
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
            "flex w-full flex-col rounded-sm border-[0.5px] border-slate-400/70",
            spaceTint(model()?.interfaceMeta?.colour, Math.floor(props.path().length / 2)),
          ]}
        >
          <div class="flex items-center justify-between">
            <span class="px-3 pt-1 text-xs font-semibold uppercase select-none">{modelName(type())}</span>
            <button
              type="button"
              class="cursor-pointer px-3 text-xs text-red-800 select-none hover:bg-red-400/30"
              aria-label={t("remove_item", "Remove {name}", { name: modelName(type()) })}
              onClick={props.onRemove}
            >
              ✕
            </button>
          </div>
          <div class="flex min-w-0 flex-1 flex-col gap-1 p-2">
            <ModelFields model={model()!} path={props.path} env={childEnv()} bare="contents" />
          </div>
        </div>
      </Match>
      <Match when={model()?.kind === "Document" || model()?.kind === "ReifiedRelationDocument"}>
        <Block
          type={type()}
          label={label()}
          tint={kindTint(model()?.kind, model()?.interfaceMeta?.colour)}
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
        <div class="flex flex-col gap-4 p-6">
          <Show when={problems().length > 0}>
            <ul
              role="alert"
              class="list-disc rounded-sm border-[0.5px] border-red-700/60 bg-red-100/70 p-3 pl-7 text-sm"
            >
              <For each={problems()}>{(problem) => <li>{problem}</li>}</For>
            </ul>
          </Show>
          <Show when={model()}>
            <ItemFields model={model()!} path={() => []} creating />
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
 * Finds an entity of one of `types`, or makes a new one: a + button beside the search (a menu of
 * the types, when there are several) opens the form for the entity in a dialog; the entity made
 * is chosen as if it had been found.
 */
function PickOrCreate(props: { types: string[]; onPick: (entity: Summary) => void }) {
  const definitions = useModels();
  const { t } = useTranslations();
  const [creating, setCreating] = createSignal<string>();
  const groups = createMemo(() => menuGroups(definitions, typeOptions(props.types)));
  return (
    <div class="flex w-full items-start gap-2">
      <EntityPicker types={props.types} onPick={props.onPick} />
      <TypeMenu
        groups={groups()}
        label="+"
        title={t("new_entity", "Make a new one")}
        onChoose={(choice) => setCreating(choice.type)}
      />
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
