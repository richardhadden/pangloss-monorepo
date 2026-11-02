import { createSignal, For, onSettled, Show } from "solid-js";
import { useModels, useTranslations } from "../../context";
import { spaceTint } from "../../primitives";
import { choicesOf, getModel } from "../../schema";
import type { Choice, MenuGroup } from "../../schema";
import { smallButtonClass } from "./styles";

/**
 * A button that opens the menu of the types a field can hold. The types are listed by the hierarchy,
 * in vertical lists split where the types stop having an ancestor in common; an abstract class is
 * shown, so the hierarchy reads, but cannot be chosen. A field that accepts semantic spaces has a
 * section for the plain types and one for each space, with the same types inside it (shown on the
 * colour of the space). With only one thing to choose there is no menu: the button chooses it.
 * The keys move in the menu as in any other: Down (or Up) opens it, Up and Down go through what
 * can be chosen (Home and End to the first and last), Enter chooses, Escape and Tab close it.
 */
export function TypeMenu(props: {
  groups: MenuGroup[];
  /** What the button says */
  label: string;
  /** The name of the button for a screen reader, and its tooltip, if the label (such as +) is not a name */
  title?: string;
  onChoose: (choice: Choice) => void;
  /** The classes of the button, instead of the small button's (to join it on to something) */
  buttonClass?: string;
  /** Open the menu leftwards from the right edge of the button (for a button at the right of a row) */
  alignRight?: boolean;
  /** As wide as what it is in (an add slot at the end of a list) */
  wide?: boolean;
}) {
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const [open, setOpen] = createSignal(false);
  let root: HTMLDivElement | undefined;
  let opener: HTMLButtonElement | undefined;
  const items = () => [...(root?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
  // (after the menu is drawn)
  const focusItem = (which: (all: HTMLElement[]) => HTMLElement | undefined) =>
    setTimeout(() => which(items())?.focus());
  const openMenu = (which: (all: HTMLElement[]) => HTMLElement | undefined) => {
    setOpen(true);
    focusItem(which);
  };
  const close = () => {
    setOpen(false);
    opener?.focus();
  };
  const onKeyDown = (event: KeyboardEvent) => {
    const all = items();
    const at = all.indexOf(document.activeElement as HTMLElement);
    if (event.key === "Escape" && open()) {
      // (only the menu: a dialog it is in stays open)
      event.stopPropagation();
      close();
    } else if (event.key === "Tab") {
      setOpen(false);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const down = event.key === "ArrowDown";
      if (!open()) openMenu((found) => (down ? found[0] : found[found.length - 1]));
      else if (all.length > 0) {
        // (round from the last to the first, and back; from nothing focused, to the first or the last)
        const next = at < 0 ? (down ? 0 : all.length - 1) : (at + (down ? 1 : -1) + all.length) % all.length;
        all[next]!.focus();
      }
    } else if ((event.key === "Home" || event.key === "End") && open()) {
      event.preventDefault();
      (event.key === "Home" ? all[0] : all[all.length - 1])?.focus();
    }
  };
  onSettled(() => {
    // (a click anywhere else closes it)
    const away = (event: MouseEvent) => {
      if (root && !root.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("click", away);
    return () => document.removeEventListener("click", away);
  });
  const choices = () => choicesOf(props.groups);
  const choose = (choice: Choice) => {
    setOpen(false);
    props.onChoose(choice);
  };
  // (a plain section has none; a space has its model's colour, else one by how deep it is)
  const tintOf = (group: MenuGroup) =>
    group.spaces.length === 0
      ? ""
      : spaceTint(
          getModel(definitions, group.spaces[group.spaces.length - 1]!)?.interfaceMeta?.colour,
          group.spaces.length - 1,
        );
  const spaceName = (group: MenuGroup) => group.spaces.map((space) => modelName(space)).join(" › ");
  return (
    <Show when={choices().length > 0}>
      <div
        class={[
          "relative",
          { "inline-block": !props.buttonClass },
          { flex: !!props.buttonClass },
          { "w-full": !!props.wide },
        ]}
        ref={root}
        onKeyDown={onKeyDown}
      >
        <Show
          when={choices().length > 1}
          fallback={
            <button
              type="button"
              class={props.buttonClass ?? smallButtonClass}
              aria-label={props.title}
              title={props.title}
              onClick={() => choose(choices()[0]!)}
            >
              {props.label}
            </button>
          }
        >
          <button
            type="button"
            ref={opener}
            class={props.buttonClass ?? smallButtonClass}
            aria-label={props.title}
            title={props.title}
            aria-haspopup="menu"
            aria-expanded={open() ? "true" : "false"}
            onClick={(event) => {
              if (open()) setOpen(false);
              // (a click with the keyboard, Enter or Space, goes into the menu too)
              else if (event.detail === 0) openMenu((found) => found[0]);
              else setOpen(true);
            }}
          >
            {props.label} <span aria-hidden="true">▾</span>
          </button>
          <Show when={open()}>
            <div
              role="menu"
              class={[
                "absolute top-full z-30 mt-1 flex min-w-max flex-col gap-2 rounded-sm border-[0.5px] border-slate-400/70 bg-white p-2 shadow-lg",
                { "left-0": !props.alignRight },
                { "right-0": props.alignRight },
              ]}
            >
              <For each={props.groups}>
                {(group) => (
                  <section
                    class={["rounded-sm border-[0.5px] border-slate-400/50 p-2", tintOf(group)]}
                  >
                    <Show when={props.groups.length > 1}>
                      <h3 class="mb-1 text-xs font-semibold uppercase select-none">
                        <Show when={group.spaces.length > 0} fallback={t("plain", "Plain")}>
                          {spaceName(group)}
                        </Show>
                      </h3>
                    </Show>
                    <div class="flex items-start gap-6">
                      <For each={group.columns}>
                        {(column) => (
                          <ul class="flex flex-col" role="group">
                            <For each={column}>
                              {(row) => (
                                <li style={{ "padding-left": `${row.depth * 0.75}rem` }}>
                                  <Show
                                    when={row.selectable}
                                    fallback={
                                      <span
                                        class="block px-2 py-1 text-sm text-slate-500 italic"
                                        aria-disabled="true"
                                      >
                                        {modelName(row.name)}
                                      </span>
                                    }
                                  >
                                    <button
                                      type="button"
                                      role="menuitem"
                                      tabindex="-1"
                                      class="block w-full cursor-pointer rounded-sm px-2 py-1 text-left text-sm hover:bg-slate-400/30 focus:bg-slate-400/30 focus:outline-none"
                                      onClick={() => choose({ spaces: group.spaces, type: row.name })}
                                    >
                                      {modelName(row.name)}
                                    </button>
                                  </Show>
                                </li>
                              )}
                            </For>
                          </ul>
                        )}
                      </For>
                    </div>
                  </section>
                )}
              </For>
            </div>
          </Show>
        </Show>
      </div>
    </Show>
  );
}
