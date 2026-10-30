import { ApiError, useApi, useComponent, userIsLoggedIn } from "@pangloss/interface-core";
import type { ItemPageProps } from "@pangloss/interface-core";
import { createMemo, createSignal, Errored, For, Loading, Show } from "solid-js";
import { editType, getView, setConcrete } from "../api";
import type { Edit, TypeView } from "../api";

const PAGE = 50;

// The item page of a type (under the console bar of the page): where it sits in the hierarchy, its
// labels (and, for someone who is logged in, a form to change them), its subtypes, and the entities
// that have it. The entities are those with the type or any type below it, unless that is turned off.
export default function TypeItem(props: ItemPageProps) {
  const api = useApi();
  const ErrorMessage = useComponent("ErrorMessage");
  const [version, setVersion] = createSignal(0);
  const [includeSubtypes, setIncludeSubtypes] = createSignal(true);
  const [limit, setLimit] = createSignal(PAGE);
  const [refused, setRefused] = createSignal<string | undefined>();
  const [editing, setEditing] = createSignal(false);
  const view = createMemo(() => {
    version();
    return getView(api, props.type, props.id, { includeSubtypes: includeSubtypes(), limit: limit() });
  });
  // The other languages a label can be given in, and whether the type can also be another class,
  // are what its model has as fields
  const languages = () =>
    props.model.fields.map((f) => f.name).filter((name) => name.startsWith("label_")).map((name) => name.slice("label_".length));
  const switchable = () => props.model.fields.some((f) => f.name === "is_concrete");

  async function attempt(work: () => Promise<unknown>) {
    setRefused(undefined);
    try {
      await work();
      setVersion((v) => v + 1);
      return true;
    } catch (error) {
      setRefused(error instanceof ApiError ? error.detail : String(error));
      return false;
    }
  }

  return (
    <div class="flex flex-col gap-6">
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p>Loading…</p>}>
          <Show when={refused()}>
            {(reason) => (
              <p role="alert" class="rounded-sm border-[0.5px] border-red-400 bg-red-50 px-3 py-2 text-sm text-red-800">
                {reason()}
              </p>
            )}
          </Show>

          <nav aria-label="Path" class="flex flex-wrap items-center gap-1 text-sm text-slate-600">
            <a href={`/${props.type}`} class="hover:underline">
              All
            </a>
            <For each={[...view().parents].reverse()}>
              {(parent) => (
                <>
                  <span aria-hidden="true">›</span>
                  <a href={`/${props.type}/${parent.id}`} class="hover:underline">
                    {parent.label}
                  </a>
                </>
              )}
            </For>
            <span aria-hidden="true">›</span>
            <span class="font-semibold text-slate-900">{view().label}</span>
          </nav>

          <section class="flex flex-col gap-2">
            <h2 class="text-sm font-semibold uppercase text-slate-600">Labels</h2>
            <Show when={!editing()}>
              <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt class="text-slate-500">default</dt>
                <dd>{view().label}</dd>
                <For each={languages()}>
                  {(code) => (
                    <>
                      <dt class="text-slate-500">{code}</dt>
                      <dd class={{ "text-slate-400": !view().labels[code] }}>
                        {view().labels[code] ?? "(not translated: the default is shown)"}
                      </dd>
                    </>
                  )}
                </For>
              </dl>
              <Show when={view().description}>
                <p class="text-sm">{view().description}</p>
              </Show>
              <Show when={userIsLoggedIn()}>
                <button type="button" class="pg-button w-fit" onClick={() => setEditing(true)}>
                  Edit labels
                </button>
              </Show>
            </Show>
            <Show when={editing()}>
              <LabelsForm
                view={view()}
                languages={languages()}
                onCancel={() => setEditing(false)}
                onSave={async (edit) => {
                  if (await attempt(() => editType(api, props.type, props.id, edit))) setEditing(false);
                }}
              />
            </Show>
          </section>

          <Show when={switchable()}>
            <label class="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={view().is_concrete}
                disabled={!userIsLoggedIn()}
                onChange={(event) => {
                  const on = event.currentTarget.checked;
                  event.currentTarget.checked = !on; // (the page shows what the server says)
                  void attempt(() => setConcrete(api, props.type, props.id, on));
                }}
              />
              Also a concrete entity (a relation that takes the other class takes this type)
            </label>
          </Show>

          <section class="flex flex-col gap-2">
            <h2 class="text-sm font-semibold uppercase text-slate-600">Subtypes</h2>
            <Show when={view().subtypes.length > 0} fallback={<p class="text-sm text-slate-500">None.</p>}>
              <ul class="flex flex-col gap-1">
                <For each={view().subtypes}>
                  {(subtype) => (
                    <li class="flex items-center gap-3 rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/70 px-3 py-2 text-sm">
                      <a href={`/${props.type}/${subtype.id}`} class="min-w-0 grow truncate hover:underline">
                        {subtype.label}
                      </a>
                      <span class="text-xs text-slate-500">
                        {subtype.subtype_count} subtypes · {subtype.entity_count} entities
                      </span>
                    </li>
                  )}
                </For>
              </ul>
            </Show>
          </section>

          <section class="flex flex-col gap-2">
            <div class="flex items-center gap-4">
              <h2 class="text-sm font-semibold uppercase text-slate-600">
                Entities with this type ({view().entities.total})
              </h2>
              <label class="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={includeSubtypes()}
                  onChange={(event) => {
                    setIncludeSubtypes(event.currentTarget.checked);
                    setLimit(PAGE);
                  }}
                />
                including subtypes
              </label>
            </div>
            <Show when={view().entities.items.length > 0} fallback={<p class="text-sm text-slate-500">None.</p>}>
              <ul class="flex flex-col gap-1">
                <For each={view().entities.items}>
                  {(entity) => (
                    <li class="flex items-center gap-3 rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/70 px-3 py-2 text-sm">
                      <span class="text-xs font-semibold uppercase">{entity.type}</span>
                      <a href={`/${entity.type}/${entity.id}`} class="min-w-0 truncate hover:underline">
                        {entity.label}
                      </a>
                    </li>
                  )}
                </For>
              </ul>
            </Show>
            <Show when={view().entities.next}>
              <button type="button" class="pg-button w-fit" onClick={() => setLimit(limit() + PAGE)}>
                Show more
              </button>
            </Show>
          </section>
        </Loading>
      </Errored>
    </div>
  );
}

function LabelsForm(props: {
  view: TypeView;
  languages: string[];
  onCancel: () => void;
  onSave: (edit: Edit) => void;
}) {
  let form!: HTMLFormElement;
  return (
    <form
      ref={form}
      class="flex flex-col gap-2 text-sm"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(form);
        const labels: Record<string, string> = {};
        for (const code of props.languages) {
          const text = String(data.get(`label_${code}`) ?? "").trim();
          if (text !== "") labels[code] = text;
        }
        props.onSave({
          label: String(data.get("label") ?? ""),
          description: String(data.get("description") ?? ""),
          labels,
        });
      }}
    >
      <label class="flex flex-col gap-1">
        default
        <input name="label" required value={props.view.label} class="rounded-sm border-[0.5px] border-slate-400/70 px-2 py-1" />
      </label>
      <For each={props.languages}>
        {(code) => (
          <label class="flex flex-col gap-1">
            {code}
            <input
              name={`label_${code}`}
              value={props.view.labels[code] ?? ""}
              placeholder="(not translated)"
              class="rounded-sm border-[0.5px] border-slate-400/70 px-2 py-1"
            />
          </label>
        )}
      </For>
      <label class="flex flex-col gap-1">
        description
        <textarea name="description" class="rounded-sm border-[0.5px] border-slate-400/70 px-2 py-1">
          {props.view.description ?? ""}
        </textarea>
      </label>
      <div class="flex gap-2">
        <button type="submit" class="pg-button">
          Save
        </button>
        <button type="button" class="pg-button" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
