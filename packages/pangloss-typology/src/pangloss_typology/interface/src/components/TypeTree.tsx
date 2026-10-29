import { ApiError, useApi, useComponent, userIsLoggedIn } from "@pangloss/interface-core";
import type { ListPageProps } from "@pangloss/interface-core";
import { createMemo, createSignal, Errored, For, Loading, Show } from "solid-js";
import { getTree, moveType } from "../api";
import type { TreeNode } from "../api";
import { canMove, targetsFor } from "../tree";

// The list page of a typology: its hierarchy as a tree. Someone who is logged in can move a type
// below another by dragging it onto that type (or onto the top-level strip), or by choosing the
// place from the list on each type, which does the same without a mouse. The server has the last
// word: it refuses a type below itself, and the reason is shown.
export default function TypeTree(props: ListPageProps) {
  const api = useApi();
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  // (read again when it changes, after a move)
  const [version, setVersion] = createSignal(0);
  // (the version is read before the request is made, so a change of it asks again)
  const nodes = createMemo(() => {
    version();
    return getTree(api, props.type);
  });
  const [dragging, setDragging] = createSignal<string | undefined>();
  const [refused, setRefused] = createSignal<string | undefined>();
  const [collapsed, setCollapsed] = createSignal<Record<string, boolean>>({});

  async function move(id: string, to: string | null) {
    setRefused(undefined);
    setDragging(undefined);
    try {
      await moveType(api, props.type, id, to);
      setVersion((v) => v + 1);
    } catch (error) {
      setRefused(error instanceof ApiError ? error.detail : String(error));
    }
  }

  const draggable = () => userIsLoggedIn();
  const mayDrop = (to: string | null) => {
    const id = dragging();
    return id !== undefined && canMove(nodes(), id, to);
  };

  function Row(row: { node: TreeNode; depth: number }) {
    const open = () => !collapsed()[row.node.id];
    return (
      <li>
        <div
          draggable={draggable() ? "true" : "false"}
          data-type-id={row.node.id}
          onDragStart={(event) => {
            setDragging(row.node.id);
            event.dataTransfer?.setData("text/plain", row.node.id);
          }}
          onDragEnd={() => setDragging(undefined)}
          onDragOver={(event) => {
            if (mayDrop(row.node.id)) event.preventDefault();
          }}
          onDrop={(event) => {
            event.preventDefault();
            const id = dragging();
            if (id !== undefined && mayDrop(row.node.id)) void move(id, row.node.id);
          }}
          class={[
            "flex items-center gap-2 rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/70 px-3 py-2 text-sm",
            { "cursor-grab": draggable(), "opacity-50": dragging() === row.node.id },
          ]}
          style={{ "margin-left": `${row.depth * 1.5}rem` }}
        >
          <button
            type="button"
            aria-label={open() ? "Collapse" : "Expand"}
            aria-expanded={open() ? "true" : "false"}
            disabled={row.node.children.length === 0}
            class="w-5 text-slate-600 disabled:opacity-20"
            onClick={() => {
              setCollapsed({ ...collapsed(), [row.node.id]: open() });
            }}
          >
            {open() ? "▾" : "▸"}
          </button>
          <a href={`/${props.type}/${row.node.id}`} class="min-w-0 grow truncate hover:underline">
            {row.node.label}
          </a>
          <Show when={row.node.children.length > 0}>
            <span class="text-xs text-slate-500">{row.node.children.length}</span>
          </Show>
          <Show when={draggable()}>
            <select
              aria-label={`Move ${row.node.label} to`}
              class="max-w-40 rounded-sm border-[0.5px] border-slate-400/70 bg-white px-1 text-xs"
              onChange={(event) => {
                const value = event.currentTarget.value;
                event.currentTarget.value = "";
                if (value !== "") void move(row.node.id, value === "top" ? null : value);
              }}
            >
              <option value="">Move to…</option>
              <Show when={canMove(nodes(), row.node.id, null)}>
                <option value="top">(top level)</option>
              </Show>
              <For each={targetsFor(nodes(), row.node.id).filter((t) => canMove(nodes(), row.node.id, t.id))}>
                {(target) => <option value={target.id}>{`${"– ".repeat(target.depth)}${target.label}`}</option>}
              </For>
            </select>
          </Show>
        </div>
        <Show when={open() && row.node.children.length > 0}>
          <ul class="mt-1 flex flex-col gap-1">
            <For each={row.node.children}>{(child) => <Row node={child} depth={row.depth + 1} />}</For>
          </ul>
        </Show>
      </li>
    );
  }

  return (
    <main class="mx-auto w-full max-w-[100rem] px-6 py-6">
      <Console type={props.type} list />
      <Show when={refused()}>
        {(reason) => (
          <p role="alert" class="mb-3 rounded-sm border-[0.5px] border-red-400 bg-red-50 px-3 py-2 text-sm text-red-800">
            {reason()}
          </p>
        )}
      </Show>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p>Loading…</p>}>
          {/* (always there for someone who can move, hidden until a drag: the rows must not move when it starts) */}
          <Show when={draggable()}>
            <div
              aria-hidden={dragging() === undefined ? "true" : "false"}
              onDragOver={(event) => {
                if (mayDrop(null)) event.preventDefault();
              }}
              onDrop={(event) => {
                event.preventDefault();
                const id = dragging();
                if (id !== undefined && mayDrop(null)) void move(id, null);
              }}
              class={[
                "mb-2 rounded-sm border border-dashed border-slate-400 px-3 py-2 text-center text-xs text-slate-600",
                { invisible: dragging() === undefined },
              ]}
            >
              Drop here for the top level
            </div>
          </Show>
          <Show when={nodes().length > 0} fallback={<p class="text-sm text-slate-600">No types yet.</p>}>
            <ul class="flex flex-col gap-1">
              <For each={nodes()}>{(node) => <Row node={node} depth={0} />}</For>
            </ul>
          </Show>
        </Loading>
      </Errored>
    </main>
  );
}
