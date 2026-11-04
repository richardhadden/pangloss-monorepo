import { ApiError, useApi, useComponent, useNavExpanded, userIsLoggedIn, useTranslations } from "@pangloss/interface-core";
import type { ListPageProps, ModelDefinition } from "@pangloss/interface-core";
import { invoke } from "@solidjs/web/server-functions";
import { createSignal, Errored, flush, For, Loading, onSettled, Show, untrack } from "solid-js";
import type { Edit, TreeNode, TypeOut } from "../api";
import { treeFeed } from "../feed";
import { createTypeTree } from "../state";
import { dropTarget, findNode, zoneAt } from "../tree";
import { LabelsForm } from "./LabelsForm";
import { TypeTag } from "./TypeTag";

/** Where a drag over a row would put the type: below the row's type (`into`), or beside it, shown above or below it */
type Mark = { id: string; to: string | null; mark: "into" | "above" | "below" };

const reasonOf = (error: unknown) =>
  error instanceof ApiError ? error.detail : error instanceof Error ? error.message : String(error);

// (a class for each key, as the object form wants: all on or all off together)
// (a button that is a segment at the end of a chip, and its icon)
const segmentButton =
  "flex w-7 shrink-0 cursor-pointer items-center justify-center border-l-[0.5px] border-slate-400/70 text-slate-500 select-none hover:bg-slate-200/70 hover:text-slate-800 active:bg-slate-300/70";
const iconClass = "size-3.5 select-none";

const classesWhen = (on: boolean, classes: string): Record<string, boolean> =>
  Object.fromEntries(classes.split(" ").map((name) => [name, on]));

// The list page of a typology: its hierarchy as an outline, which follows the server as it changes (a live feed).
// Someone who is logged in moves a type by dragging its row: dropped on the middle of another row it goes below that
// type, on its top or bottom edge beside it (beside a top-level type is the top level). Their pencil on a row makes its
// label a text field. A move or a new label is shown at once; the server has the last word, and what it refuses is
// undone and said.
export default function TypeTree(props: ListPageProps) {
  const Console = useComponent("Console");
  const { t } = useTranslations();
  const { navPinned } = useNavExpanded();
  // (the feed is opened in the browser only: the server would have the tree to send once, and the browser would not
  // open the feed again when it takes the page over; until then, it is loading)
  const [inBrowser, setInBrowser] = createSignal(false);
  onSettled(() => {
    setInBrowser(true);
  });
  // (where a new type is being made, in a dialog: below a type, or at the top level, `null`)
  const [adding, setAdding] = createSignal<string | null | undefined>();
  // (the other languages a label can be given in are what the model has as fields)
  const languages = () =>
    (props.model?.fields ?? [])
      .map((f) => f.name)
      .filter((name) => name.startsWith("label_"))
      .map((name) => name.slice("label_".length));
  return (
    <main class={["w-full py-8", { "px-8": navPinned(), "px-20": !navPinned() }]}>
      <Console type={props.type} list onNew={() => setAdding(null)} />
      <Show when={inBrowser()} fallback={<p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>}>
        <Hierarchy
          type={props.type}
          model={props.model}
          languages={languages()}
          adding={adding()}
          onAdd={setAdding}
        />
      </Show>
    </main>
  );
}

/** The hierarchy, from the feed, and what is done to it */
function Hierarchy(props: {
  type: string;
  model: ModelDefinition;
  languages: string[];
  /** Where a new type is being made: below a type, at the top level (`null`), or nowhere */
  adding: string | null | undefined;
  onAdd: (at: string | null | undefined) => void;
}) {
  const api = useApi();
  const ErrorMessage = useComponent("ErrorMessage");
  const { t, modelName } = useTranslations();
  const type = untrack(() => props.type);
  const { tree, move, rename, add } = createTypeTree({
    type,
    feed: (signal) => invoke(treeFeed, { signal }, type),
    api,
  });
  const [dragging, setDragging] = createSignal<string | undefined>();
  const [over, setOver] = createSignal<Mark | undefined>();
  const [editing, setEditing] = createSignal<string | undefined>();
  const [refused, setRefused] = createSignal<string | undefined>();
  const [collapsed, setCollapsed] = createSignal<Record<string, boolean>>({});
  const loggedIn = () => userIsLoggedIn();

  const said = (error: unknown) => setRefused(reasonOf(error));

  /** Where the drag over `id`'s row would put the type, from where the pointer is on the row (none: not allowed) */
  function markAt(event: DragEvent, id: string): Mark | undefined {
    const dragged = dragging();
    if (dragged === undefined) return undefined;
    const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const offset = event.clientY - box.top;
    const zone = zoneAt(offset, box.height);
    const to = dropTarget(tree.nodes, dragged, id, zone);
    if (to === undefined) return undefined;
    return { id, to, mark: zone === "into" ? "into" : offset < box.height / 2 ? "above" : "below" };
  }

  /** Marks where the drag over `id`'s row would put the type, and allows the drop there; or takes the mark away */
  function markOver(event: DragEvent, id: string) {
    const found = markAt(event, id);
    if (found) {
      event.preventDefault();
      const now = over();
      if (now?.id !== found.id || now.mark !== found.mark) setOver(found);
    } else if (over()?.id === id) setOver(undefined);
  }

  function endDrag() {
    setDragging(undefined);
    setOver(undefined);
  }

  function Row(row: { node: TreeNode; depth: number }) {
    const open = () => !collapsed()[row.node.id];
    const hasChildren = () => row.node.children.length > 0;
    const mark = () => (over()?.id === row.node.id ? over()!.mark : undefined);
    const draggable = () => loggedIn() && editing() !== row.node.id;
    return (
      <li>
        <div
          draggable={draggable() ? "true" : "false"}
          data-type-id={row.node.id}
          data-depth={row.depth}
          data-drop={mark()}
          onDragStart={(event) => {
            setRefused(undefined);
            setDragging(row.node.id);
            event.dataTransfer?.setData("text/plain", row.node.id);
            if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
          }}
          onDragEnd={endDrag}
          // (entering a part of the row is as much a drag over it: a drop is allowed where both are cancelled)
          onDragEnter={(event) => markOver(event, row.node.id)}
          onDragOver={(event) => markOver(event, row.node.id)}
          onDragLeave={(event) => {
            const into = event.relatedTarget as Node | null;
            if (into && (event.currentTarget as HTMLElement).contains(into)) return;
            if (over()?.id === row.node.id) setOver(undefined);
          }}
          onDrop={(event) => {
            event.preventDefault();
            const dragged = dragging();
            const found = markAt(event, row.node.id);
            endDrag();
            if (dragged !== undefined && found) {
              setRefused(undefined);
              // (the drag's own state is the page's at once, not held until the move is acknowledged)
              flush();
              move(dragged, found.to).catch(said);
            }
          }}
          class={[
            "group relative flex min-h-8 items-center gap-1 rounded-xs pr-2 text-sm",
            {
              "cursor-grab": draggable(),
              "opacity-40": dragging() === row.node.id,
            },
            classesWhen(
              mark() === "above",
              "before:pointer-events-none before:absolute before:inset-x-0 before:-top-px before:h-0.5 before:rounded-full before:bg-sky-500",
            ),
            classesWhen(
              mark() === "below",
              "after:pointer-events-none after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:rounded-full after:bg-sky-500",
            ),
          ]}
        >
          <Show when={hasChildren()} fallback={<span class="w-6 shrink-0" />}>
            <button
              type="button"
              aria-label={open() ? t("typology_collapse", "Collapse") : t("typology_expand", "Expand")}
              aria-expanded={open() ? "true" : "false"}
              class="flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-xs text-slate-500 hover:bg-slate-200/80 hover:text-slate-800"
              onClick={() => setCollapsed({ ...collapsed(), [row.node.id]: open() })}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
                stroke-linecap="round"
                stroke-linejoin="round"
                class={["size-3.5 transition-transform select-none", { "rotate-90": open() }]}
                aria-hidden="true"
              >
                <polyline points="9 6 15 12 9 18" />
              </svg>
            </button>
          </Show>
          {/* (a chip, as a reference is: its type or a handle, the label, the number of subtypes when they are folded away, and its buttons) */}
          <span
            class={[
              "inline-flex max-w-full min-w-0 items-stretch overflow-hidden rounded-xs border-[0.5px]",
              {
                // (being edited, or where a drop would put the dragged type below this one: sky)
                "border-slate-400/70": editing() !== row.node.id && mark() !== "into",
                "bg-slate-100/70": mark() !== "into",
                "border-sky-500": editing() === row.node.id || mark() === "into",
                "bg-sky-100": mark() === "into",
                "ring-1": editing() === row.node.id || mark() === "into",
                "ring-sky-400/60": editing() === row.node.id || mark() === "into",
              },
            ]}
          >
            {/* (someone who reads sees what it is, as a reference chip says it; someone who changes it, its handles) */}
            <Show when={!loggedIn()}>
              <TypeTag model={props.model} />
            </Show>
            <Show when={loggedIn()}>
              {/* (the whole row is dragged: this shows that it can be) */}
              <span
                data-handle
                aria-hidden="true"
                class="flex w-5 shrink-0 cursor-grab items-center justify-center border-r-[0.5px] border-slate-400/70 text-slate-400 select-none"
              >
                <svg viewBox="0 0 10 16" fill="currentColor" class="h-3.5 w-2 select-none">
                  <circle cx="2" cy="3" r="1.25" />
                  <circle cx="8" cy="3" r="1.25" />
                  <circle cx="2" cy="8" r="1.25" />
                  <circle cx="8" cy="8" r="1.25" />
                  <circle cx="2" cy="13" r="1.25" />
                  <circle cx="8" cy="13" r="1.25" />
                </svg>
              </span>
            </Show>
            <Show
              when={editing() === row.node.id}
              fallback={
                <a
                  href={`/${props.type}/${row.node.id}`}
                  draggable="false"
                  class="min-w-0 truncate px-2 py-1 hover:bg-slate-200/70 active:bg-slate-300/70"
                >
                  {row.node.label}
                </a>
              }
            >
              <LabelField
                label={row.node.label}
                onDone={(label) => {
                  setEditing(undefined);
                  if (label === undefined) return;
                  setRefused(undefined);
                  // (the field goes at once, not when the new label is acknowledged)
                  flush();
                  rename(row.node.id, label).catch(said);
                }}
              />
            </Show>
            {/* (how many subtypes, while they are folded away: open, they are there to see) */}
            <Show when={hasChildren() && !open()}>
              <span
                data-count
                title={t("typology_subtype_count", "{count} subtypes", { count: row.node.children.length })}
                class="flex shrink-0 items-center border-l-[0.5px] border-slate-400/70 bg-white/70 px-2 text-xs text-slate-600 tabular-nums"
              >
                {row.node.children.length}
              </span>
            </Show>
            <Show when={loggedIn() && editing() !== row.node.id}>
              <button
                type="button"
                aria-label={t("typology_edit_label", "Edit the label of {name}", { name: row.node.label })}
                title={t("typology_edit_label", "Edit the label of {name}", { name: row.node.label })}
                class={segmentButton}
                onClick={() => setEditing(row.node.id)}
              >
                {/* (a pencil) */}
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  class={iconClass}
                  aria-hidden="true"
                >
                  <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                </svg>
              </button>
              <button
                type="button"
                aria-label={t("typology_add_subtype", "Add a subtype of {name}", { name: row.node.label })}
                title={t("typology_add_subtype", "Add a subtype of {name}", { name: row.node.label })}
                class={segmentButton}
                onClick={() => props.onAdd(row.node.id)}
              >
                {/* (a branch down and to the right, with a plus at its end) */}
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  class={iconClass}
                  aria-hidden="true"
                >
                  <path d="M5 3v9a4 4 0 0 0 4 4h4" />
                  <path d="M18 12v8M14 16h8" />
                </svg>
              </button>
            </Show>
          </span>
        </div>
        <Show when={open() && hasChildren()}>
          {/* (the subtypes under a hairline from the chevron of their supertype) */}
          <ul class="mt-1 ml-3 flex flex-col gap-1 border-l-[0.5px] border-slate-300 pl-2">
            <For each={row.node.children}>{(child) => <Row node={child} depth={row.depth + 1} />}</For>
          </ul>
        </Show>
      </li>
    );
  }

  return (
    <>
      <Show when={refused()}>
        {(reason) => (
          <p role="alert" class="mb-3 rounded-xs border-[0.5px] border-red-400 bg-red-50 px-3 py-2 text-sm text-red-800">
            {reason()}
          </p>
        )}
      </Show>
      <Show when={loggedIn()}>
        <AddTopLevel class="mb-3" onClick={() => props.onAdd(null)} />
      </Show>
      <Show when={props.adding !== undefined}>
        <NewTypeDialog
          title={
            props.adding === null
              ? t("typology_new_top", "New top-level {type}", { type: modelName(type) })
              : t("typology_new_subtype", "New subtype of {name}", {
                  name: findNode(tree.nodes, props.adding ?? "")?.label ?? "",
                })
          }
          languages={props.languages}
          onClose={() => props.onAdd(undefined)}
          create={(fields) => add({ ...fields, supertype: props.adding ?? null })}
          onMade={(made) => {
            props.onAdd(undefined);
            // (a new subtype is shown: what it is below is opened)
            if (made.supertype) setCollapsed({ ...collapsed(), [made.supertype]: false });
          }}
        />
      </Show>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
          <Show when={tree.state === "ready"} fallback={<p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>}>
            <Show
              when={tree.nodes.length > 0}
              fallback={<p class="text-sm text-slate-600">{t("typology_no_types", "No types yet.")}</p>}
            >
              <ul class="flex flex-col gap-1" onDragEnd={endDrag}>
                <For each={tree.nodes}>{(node) => <Row node={node} depth={0} />}</For>
              </ul>
            </Show>
            <Show when={loggedIn() && tree.nodes.length > 0}>
              <AddTopLevel class="mt-3" onClick={() => props.onAdd(null)} />
            </Show>
          </Show>
        </Loading>
      </Errored>
    </>
  );
}

/**
 * A label as a text field, focused with the label selected: Enter or leaving it is done with the new label (none if it
 * is empty or as it was), Escape is done with none. Done once.
 */
function LabelField(props: { label: string; onDone: (label: string | undefined) => void }) {
  const { t } = useTranslations();
  const original = untrack(() => props.label);
  let done = false;
  const finish = (value: string | undefined) => {
    if (done) return;
    done = true;
    const label = value?.trim();
    props.onDone(label && label !== original ? label : undefined);
  };
  return (
    <input
      ref={(input) =>
        queueMicrotask(() => {
          input.focus();
          input.select();
        })
      }
      value={original}
      aria-label={t("typology_label_of", "Label of {name}", { name: original })}
      class="w-72 max-w-full min-w-0 bg-white px-2 py-1 text-sm outline-none"
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          finish(event.currentTarget.value);
        } else if (event.key === "Escape") {
          event.preventDefault();
          finish(undefined);
        }
      }}
      onBlur={(event) => finish(event.currentTarget.value)}
    />
  );
}

/** The button that makes a type at the top level (above the tree and below it) */
function AddTopLevel(props: { class: string; onClick: () => void }) {
  const { t } = useTranslations();
  return (
    <button
      type="button"
      class={[
        "flex w-fit cursor-pointer items-center gap-2 rounded-xs border-[0.5px] border-dashed border-slate-400 px-3 py-1 text-xs font-semibold text-slate-600 uppercase select-none hover:border-slate-500 hover:bg-slate-100 hover:text-slate-900",
        props.class,
      ]}
      onClick={() => props.onClick()}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        class="size-3.5 select-none"
        aria-hidden="true"
      >
        <path d="M12 5v14M5 12h14" />
      </svg>
      {t("typology_add_top", "Add a top-level type")}
    </button>
  );
}

/**
 * A new type, in a dialog: its labels and description. It stays open while the API makes it, and says why if it
 * does not; once it is made, `onMade` (the tree shows it at once).
 */
function NewTypeDialog(props: {
  title: string;
  languages: string[];
  onClose: () => void;
  create: (fields: Edit & { label: string }) => Promise<TypeOut>;
  onMade: (made: TypeOut) => void;
}) {
  const Modal = useComponent("Modal");
  const { t } = useTranslations();
  const [busy, setBusy] = createSignal(false);
  const [problem, setProblem] = createSignal<string | undefined>();
  return (
    <Modal title={props.title} onClose={props.onClose}>
      <div class="flex flex-col gap-3 p-4">
        <Show when={problem()}>
          {(reason) => (
            <p role="alert" class="rounded-xs border-[0.5px] border-red-400 bg-red-50 px-3 py-2 text-sm text-red-800">
              {reason()}
            </p>
          )}
        </Show>
        <LabelsForm
          initial={{ label: "", labels: {}, description: null }}
          languages={props.languages}
          autofocus
          busy={busy()}
          saveLabel={t("typology_add", "Add")}
          onCancel={props.onClose}
          onSave={(fields) => {
            setBusy(true);
            setProblem(undefined);
            props
              .create({ ...fields, description: fields.description || undefined })
              .then(props.onMade, (error: unknown) => {
                setProblem(reasonOf(error));
                setBusy(false);
              });
          }}
        />
      </div>
    </Modal>
  );
}
