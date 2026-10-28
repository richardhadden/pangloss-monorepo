import { For, Match, Show, Switch } from "solid-js";
import type { ParentProps } from "solid-js";
import { useComponent, useModels } from "../context";
import { kindTint, spaceTint } from "../primitives";
import { getModel } from "../schema";
import type { FieldDefinition, ItemContentsProps, ModelDefinition } from "../types";

type Data = Record<string, unknown>;

const isObject = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);

// (nothing to show: the row is left out)
const isEmpty = (value: unknown) =>
  value === null ||
  value === undefined ||
  value === "" ||
  (Array.isArray(value) && value.length === 0);

/** The name of a field to read: `activity_type` as "activity type" (the case is the style's) */
const humanise = (name: string) => name.replace(/_/g, " ");

/** A key on the left, its contents on the right */
function Row(props: ParentProps<{ name: string }>) {
  return (
    <>
      <dt class="pt-1 text-xs font-semibold text-slate-500 uppercase">{props.name}</dt>
      <dd class="flex min-w-0 flex-col items-start gap-1">{props.children}</dd>
    </>
  );
}

/**
 * The rows of an object: a key and its contents for each field of its model, in the order of
 * the model, the keys in a column on the left and the contents on the right. Fields with
 * nothing in them are left out. What refers to the object from elsewhere (`incoming`) follows,
 * as chips.
 */
function Fields(props: { value: Data; model: ModelDefinition | undefined; depth: number }) {
  return (
    <dl class="grid grid-cols-[10rem_minmax(0,1fr)] gap-x-4 gap-y-2">
      <For each={props.model?.fields ?? []}>
        {(field) => (
          <Show when={!isEmpty(props.value[field.key])}>
            <Row name={humanise(field.name)}>
              <Value value={props.value[field.key]} field={field} depth={props.depth} />
            </Row>
          </Show>
        )}
      </For>
      <For each={props.model?.incoming ?? []}>
        {(incoming) => (
          <Show when={!isEmpty(props.value[incoming.key])}>
            <Row name={humanise(incoming.name)}>
              <Value value={props.value[incoming.key]} depth={props.depth} asChip />
            </Row>
          </Show>
        )}
      </For>
    </dl>
  );
}

/** A text, a number, a yes or no, a list, or an object */
function Value(props: { value: unknown; field?: FieldDefinition; depth: number; asChip?: boolean }) {
  return (
    <Switch
      fallback={<span class="text-sm break-words whitespace-pre-wrap">{String(props.value)}</span>}
    >
      <Match when={Array.isArray(props.value)}>
        <For each={props.value as unknown[]}>
          {(item) => <Value value={item} field={props.field} depth={props.depth} asChip={props.asChip} />}
        </For>
      </Match>
      <Match when={isObject(props.value)}>
        <ObjectValue
          value={props.value as Data}
          field={props.field}
          depth={props.depth}
          asChip={props.asChip}
        />
      </Match>
      <Match when={typeof props.value === "boolean"}>
        <span class="text-sm">{props.value ? "Yes" : "No"}</span>
      </Match>
    </Switch>
  );
}

/**
 * An object in a field. An Entity is a chip. A semantic space is a band, with what is in it
 * inside. An embedded object is only its rows, indented (it is in one place only). Anything else
 * (a Document inside, a reified relation, a conjunction, an annotated value) is a block with its
 * type at the head and its own rows.
 */
function ObjectValue(props: { value: Data; field?: FieldDefinition; depth: number; asChip?: boolean }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const definitions = useModels();
  const type = () => (typeof props.value.type === "string" ? props.value.type : undefined);
  // (an annotated value has no type of its own in the JSON: the field says which it is)
  const model = () =>
    getModel(definitions, type() ?? "") ??
    (props.field?.kind === "annotatedValue" ? getModel(definitions, props.field.model) : undefined);
  const label = () => (typeof props.value.label === "string" ? props.value.label : undefined);
  const isChip = () => type() !== undefined && (props.asChip || model()?.kind === "Entity");
  const isSpace = () => model()?.kind === "SemanticSpace";
  const isEmbedded = () => model()?.kind === "Embedded";
  return (
    <Switch
      fallback={
        <div class="w-full rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/50">
          <div class="flex items-stretch border-b-[0.5px] border-slate-400/70">
            <span
              class={[
                "flex shrink-0 items-center border-r-[0.5px] border-slate-400/70 px-3 py-1 text-xs font-semibold uppercase select-none",
                kindTint(model()?.kind, model()?.interfaceMeta?.colour),
              ]}
            >
              {type() ?? model()?.name}
            </span>
            <Show when={label()}>
              <span class="min-w-0 flex-1 truncate px-3 py-1 text-sm">{label()}</span>
            </Show>
          </div>
          <div class="p-3">
            <Fields value={props.value} model={model()} depth={props.depth} />
          </div>
        </div>
      }
    >
      <Match when={isChip()}>
        <ReferenceChip
          type={type() ?? ""}
          label={label() ?? String(props.value.id ?? "")}
          href={`/${type()}/${props.value.id}`}
          edgeProperties={isObject(props.value.edgeProperties) ? props.value.edgeProperties : undefined}
        />
      </Match>
      <Match when={isEmbedded()}>
        {/* (it is in this one place only: no box, no type, only its fields, indented to show they go together) */}
        <div class="w-full pl-4">
          <Fields value={props.value} model={model()} depth={props.depth} />
        </div>
      </Match>
      <Match when={isSpace()}>
        <div
          class={[
            "flex w-full items-stretch rounded-sm border-[0.5px] border-slate-400/70",
            spaceTint(model()?.interfaceMeta?.colour, props.depth),
          ]}
        >
          <span class="flex shrink-0 items-center px-3 text-xs font-semibold uppercase select-none">
            {type()}
          </span>
          <div class="flex min-w-0 flex-1 flex-col gap-1 p-1">
            <Value value={props.value.contents} depth={props.depth + 1} />
          </div>
        </div>
      </Match>
    </Switch>
  );
}

/**
 * The contents of one Document or Entity, laid out by its model: keys on the left, contents
 * on the right, and what is nested inside nested the same way, to any depth.
 */
export function ItemContents(props: ItemContentsProps) {
  const definitions = useModels();
  const model = () =>
    getModel(definitions, typeof props.item.type === "string" ? props.item.type : "");
  return <Fields value={props.item} model={model()} depth={0} />;
}
