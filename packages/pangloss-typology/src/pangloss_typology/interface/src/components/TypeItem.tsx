import {
  ApiError,
  kindTint,
  smallButtonClass,
  useApi,
  useComponent,
  userIsLoggedIn,
  useTranslations,
} from "@pangloss/interface-core";
import type { ItemPageProps } from "@pangloss/interface-core";
import { action, createMemo, createSignal, Errored, For, Loading, refresh, Show } from "solid-js";
import { editType, getView, setConcrete } from "../api";
import { LabelsForm, termClass } from "./LabelsForm";
import { TypeTag } from "./TypeTag";

const PAGE = 50;

// The item page of a type (under the console bar of the page): where it sits in the hierarchy, its
// labels (and, for someone who is logged in, a form to change them), its subtypes, and the entities
// that have it. The entities are those with the type or any type below it, unless that is turned off.
export default function TypeItem(props: ItemPageProps) {
  const api = useApi();
  const ErrorMessage = useComponent("ErrorMessage");
  const { t, modelName } = useTranslations();
  const [includeSubtypes, setIncludeSubtypes] = createSignal(true);
  const [limit, setLimit] = createSignal(PAGE);
  const [refused, setRefused] = createSignal<string | undefined>();
  const [editing, setEditing] = createSignal(false);
  // (read again after a change: `refresh(view)`)
  const view = createMemo(() =>
    getView(api, props.type, props.id, { includeSubtypes: includeSubtypes(), limit: limit() }),
  );
  // The other languages a label can be given in, and whether the type can also be another class,
  // are what its model has as fields
  const languages = () =>
    props.model.fields.map((f) => f.name).filter((name) => name.startsWith("label_")).map((name) => name.slice("label_".length));
  const switchable = () => props.model.fields.some((f) => f.name === "is_concrete");

  // Makes a change, and reads the type again once it is made: true if it was; what the server refuses is said
  const changing = action(function* (work: () => Promise<unknown>) {
    try {
      yield work();
    } catch (error) {
      setRefused(error instanceof ApiError ? error.detail : String(error));
      return false;
    }
    yield refresh(view);
    return true;
  });
  function attempt(work: () => Promise<unknown>): Promise<boolean> {
    setRefused(undefined);
    // (a type that cannot be read again is shown by the page's boundary)
    return changing(work).catch(() => false);
  }

  return (
    <div class="flex flex-col gap-8">
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
          <Show when={refused()}>
            {(reason) => (
              <p role="alert" class="rounded-xs border-[0.5px] border-red-400 bg-red-50 px-3 py-2 text-sm text-red-800">
                {reason()}
              </p>
            )}
          </Show>

          <nav aria-label={t("typology_path", "Path")} class="-mt-2 flex flex-wrap items-center gap-1.5 text-sm text-slate-500">
            <a href={`/${props.type}`} class="hover:text-slate-900 hover:underline">
              {t("typology_all", "All")}
            </a>
            <For each={[...view().parents].reverse()}>
              {(parent) => (
                <>
                  <span aria-hidden="true" class="text-slate-400 select-none">›</span>
                  <a href={`/${props.type}/${parent.id}`} class="hover:text-slate-900 hover:underline">
                    {parent.label}
                  </a>
                </>
              )}
            </For>
            <span aria-hidden="true" class="text-slate-400 select-none">›</span>
            <span class="font-semibold text-slate-900">{view().label}</span>
          </nav>

          <section class="flex flex-col gap-3">
            <div class={sectionHead}>
              <h2 class={headingClass}>{t("typology_labels", "Labels")}</h2>
              <Show when={userIsLoggedIn() && !editing()}>
                <button type="button" class={smallButtonClass} onClick={() => setEditing(true)}>
                  {t("typology_edit_labels", "Edit labels")}
                </button>
              </Show>
            </div>
            <Show when={!editing()}>
              <dl class="grid grid-cols-[minmax(4rem,auto)_1fr] items-baseline gap-x-6 gap-y-1.5 text-sm">
                <dt class={termClass}>{t("typology_default_label", "default")}</dt>
                <dd>{view().label}</dd>
                <For each={languages()}>
                  {(code) => (
                    <>
                      <dt class={termClass}>{code}</dt>
                      <dd class={{ "text-slate-400": !view().labels[code], italic: !view().labels[code] }}>
                        {view().labels[code] ?? t("typology_not_translated_shown", "(not translated: the default is shown)")}
                      </dd>
                    </>
                  )}
                </For>
              </dl>
              <Show when={view().description}>
                <p class="max-w-prose text-sm text-slate-700">{view().description}</p>
              </Show>
            </Show>
            <Show when={editing()}>
              <LabelsForm
                initial={view()}
                languages={languages()}
                onCancel={() => setEditing(false)}
                onSave={async (edit) => {
                  if (await attempt(() => editType(api, props.type, props.id, edit))) setEditing(false);
                }}
              />
            </Show>
          </section>

          <Show when={switchable()}>
            <label class="flex w-fit items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                class="accent-sky-600"
                checked={view().is_concrete}
                disabled={!userIsLoggedIn()}
                onChange={(event) => {
                  const on = event.currentTarget.checked;
                  event.currentTarget.checked = !on; // (the page shows what the server says)
                  void attempt(() => setConcrete(api, props.type, props.id, on));
                }}
              />
              {t("typology_concrete", "Also a concrete entity (a relation that takes the other class takes this type)")}
            </label>
          </Show>

          <section class="flex flex-col gap-3">
            <div class={sectionHead}>
              <h2 class={headingClass}>{t("typology_subtypes", "Subtypes")}</h2>
            </div>
            <Show
              when={view().subtypes.length > 0}
              fallback={<p class="text-sm text-slate-500">{t("typology_none", "None.")}</p>}
            >
              {/* (each a chip, as in the tree: the type, the label, and what is below it) */}
              <ul class="flex flex-wrap gap-2">
                <For each={view().subtypes}>
                  {(subtype) => (
                    <li class="inline-flex max-w-full min-w-0 items-stretch overflow-hidden rounded-xs border-[0.5px] border-slate-400/70 bg-slate-100/70 text-sm">
                      <TypeTag model={props.model} />
                      <a
                        href={`/${props.type}/${subtype.id}`}
                        class="min-w-0 truncate px-2 py-1 hover:bg-slate-200/70 active:bg-slate-300/70"
                      >
                        {subtype.label}
                      </a>
                      <span class="flex shrink-0 items-center border-l-[0.5px] border-slate-400/70 bg-white/70 px-2 text-xs text-slate-600 tabular-nums">
                        {t("typology_counts", "{subtypes} subtypes · {entities} entities", {
                          subtypes: subtype.subtype_count,
                          entities: subtype.entity_count,
                        })}
                      </span>
                    </li>
                  )}
                </For>
              </ul>
            </Show>
          </section>

          <section class="flex flex-col gap-3">
            <div class={sectionHead}>
              <h2 class={headingClass}>
                {t("typology_entities_with", "Entities with this type ({count})", { count: view().entities.total })}
              </h2>
              {/* (a toggle as the interface's are, a pill pressed in or not; an unseen checkbox over all of it, for
                  the pointer, the keyboard and a screen reader) */}
              <label
                class={[
                  "relative flex cursor-pointer items-center gap-1.5 rounded-xs border-[0.5px] px-2 py-1 text-xs font-semibold uppercase select-none has-focus-visible:ring-1 has-focus-visible:ring-sky-400/60",
                  { "border-slate-500 bg-slate-400/50 text-slate-900 hover:bg-slate-400/60": includeSubtypes() },
                  { "border-slate-400/70 bg-white/80 text-slate-500 hover:bg-slate-200/70": !includeSubtypes() },
                ]}
              >
                <input
                  type="checkbox"
                  class="absolute inset-0 cursor-pointer appearance-none opacity-0"
                  checked={includeSubtypes()}
                  onChange={(event) => {
                    setIncludeSubtypes(event.currentTarget.checked);
                    setLimit(PAGE);
                  }}
                />
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="3"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  class={["size-3 select-none", { invisible: !includeSubtypes() }]}
                  aria-hidden="true"
                >
                  <polyline points="5 12 10 17 19 7" />
                </svg>
                {t("typology_including_subtypes", "including subtypes")}
              </label>
            </div>
            <Show
              when={view().entities.items.length > 0}
              fallback={<p class="text-sm text-slate-500">{t("typology_none", "None.")}</p>}
            >
              <ul class="flex flex-col gap-1.5">
                <For each={view().entities.items}>
                  {(entity) => (
                    <li class="flex items-stretch overflow-hidden rounded-xs border-[0.5px] border-slate-400/70 bg-slate-100/70">
                      <span
                        class={[
                          "flex shrink-0 items-center px-3 text-xs font-semibold uppercase select-none",
                          kindTint("Entity"),
                        ]}
                      >
                        {modelName(entity.type)}
                      </span>
                      <a href={`/${entity.type}/${entity.id}`} class={[rowClass, "grow"]}>
                        <span class="min-w-0 truncate">{entity.label}</span>
                      </a>
                    </li>
                  )}
                </For>
              </ul>
            </Show>
            <Show when={view().entities.next}>
              <button type="button" class={[smallButtonClass, "w-fit"]} onClick={() => setLimit(limit() + PAGE)}>
                {t("typology_show_more", "Show more")}
              </button>
            </Show>
          </section>
        </Loading>
      </Errored>
    </div>
  );
}

// (a section's heading, on a hairline, with what it has to do at its right end)
const sectionHead = "flex min-h-7 items-center justify-between gap-4 border-b-[0.5px] border-slate-400/70 pb-1";
const headingClass = "text-xs font-semibold text-slate-600 uppercase";
const rowClass = "flex min-w-0 items-center gap-3 px-3 py-2 text-sm hover:bg-slate-200/60";
