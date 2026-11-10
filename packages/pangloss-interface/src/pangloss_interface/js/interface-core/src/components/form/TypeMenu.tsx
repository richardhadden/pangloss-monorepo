import { createMemo, createSignal, flush, For, onSettled, Show } from "solid-js";
import type { JSX } from "@solidjs/web";
import type { ParentProps } from "solid-js";
import { useModels, useTranslations } from "../../context";
import { kindTint, spaceTint } from "../../primitives";
import { ancestry, choicesOf, getModel, typeColumns } from "../../schema";
import type { Choice, MenuGroup, TypeRow } from "../../schema";
import type { ModelDefinitions } from "../../types";
import { plainTint, smallButtonClass } from "./styles";

// (the types with no space round them have no tint; a space has its model's colour, else one by how deep it is)
const groupTint = (definitions: ModelDefinitions, group: MenuGroup) =>
  group.spaces.length === 0
    ? ""
    : spaceTint(
        getModel(definitions, group.spaces[group.spaces.length - 1]!)?.interfaceMeta?.colour,
        group.spaces.length - 1,
      );

/**
 * A button that opens the menu of the types a field can hold. The types are listed by the hierarchy,
 * in vertical lists split where the types stop having an ancestor in common; an abstract class is
 * shown, so the hierarchy reads, but cannot be chosen. A field that accepts semantic spaces has the
 * types on their own, then a section for each space, headed by its name, with the same types inside
 * it (shown on the colour of the space). With only one thing to choose there is no menu: the button chooses it.
 * The keys move in the menu as in any other: Down (or Up) opens it, Up and Down go through what
 * can be chosen (Home and End to the first and last), Enter chooses, Escape and Tab close it. A type in
 * `unavailable` is in the menu, greyed, with the reason under its name, and cannot be chosen; so with one
 * to choose and some that cannot be, it is still a menu, and with none to choose, a menu that says why.
 */
export function TypeMenu(props: {
  groups: MenuGroup[];
  /** What the button says */
  label: string;
  /** The type the label names, when it does: Alt on the button describes it (`TypeInfoPopup`) */
  typeInfo?: string;
  /** The name of the button for a screen reader, and its tooltip, if the label (such as +) is not a name */
  title?: string;
  onChoose: (choice: Choice) => void;
  /** The classes of the button, instead of the small button's (to join it on to something) */
  buttonClass?: string;
  /** Open the menu leftwards from the right edge of the button (for a button at the right of a row) */
  alignRight?: boolean;
  /** As wide as what it is in (an add slot at the end of a list) */
  wide?: boolean;
  /** Types that are shown but cannot be chosen, each with why */
  unavailable?: Record<string, string>;
  /** A number to show after the name of a type (how many there are of it) */
  counts?: Record<string, number>;
}) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  const [open, setOpen] = createSignal(false);
  // (how far left of the button's left edge it opens: as far as it would go past the right of the window)
  const [shift, setShift] = createSignal(0);
  let root: HTMLDivElement | undefined;
  let opener: HTMLButtonElement | undefined;
  let menu: HTMLDivElement | undefined;
  const items = () => [...(root?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
  // (drawn, then measured: one that would go past the right of the window is moved left, by as much, and no further
  // than the left of the window)
  const show = () => {
    setShift(0);
    setOpen(true);
    flush();
    if (props.alignRight || !menu) return;
    const box = menu.getBoundingClientRect();
    const over = box.right - (window.innerWidth - 8);
    if (over > 0) {
      setShift(Math.min(over, Math.max(0, box.left - 8)));
      flush();
    }
  };
  const openMenu = (which: (all: HTMLElement[]) => HTMLElement | undefined) => {
    show();
    // (the menu drawn, then into it)
    which(items())?.focus();
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
  const reasonFor = (type: string) => props.unavailable?.[type];
  const listed = () => choicesOf(props.groups);
  const choices = () => listed().filter((choice) => reasonFor(choice.type) === undefined);
  const choose = (choice: Choice) => {
    setOpen(false);
    props.onChoose(choice);
  };
  const tintOf = (group: MenuGroup) => groupTint(definitions, group);
  // (a type's button is in the colour of its type, as its chip is; one with none has the plain one)
  const chipTint = (name: string) => {
    const model = getModel(definitions, name);
    return kindTint(model?.kind, model?.interfaceMeta?.colour) || plainTint;
  };
  // (the name inside a button or an abstract class's line, indented by how deep it is)
  const indent = (row: TypeRow) => ({ "padding-left": `${0.75 + row.depth * 1}rem` });
  const spaceName = (group: MenuGroup) => group.spaces.map((space) => modelName(space)).join(" › ");
  return (
    <Show when={listed().length > 0}>
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
          when={choices().length !== 1 || listed().length > 1}
          fallback={
            <button
              data-type-info={props.typeInfo}
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
            data-type-info={props.typeInfo}
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
              else show();
            }}
          >
            {props.label} <span aria-hidden="true">▾</span>
          </button>
          <Show when={open()}>
            <div
              role="menu"
              ref={menu}
              class={[
                "absolute top-full z-30 mt-1 flex min-w-max flex-col gap-2 rounded-xs border-[0.5px] border-slate-400/70 bg-white p-2 shadow-lg",
                { "right-0": !!props.alignRight },
              ]}
              style={props.alignRight ? undefined : { left: `${-shift()}px` }}
            >
              <For each={props.groups}>
                {(group) => (
                  <section
                    class={["rounded-xs border-[0.5px] border-slate-400/50 p-2", tintOf(group)]}
                  >
                    <Show when={group.spaces.length > 0}>
                      <h3 class="mb-1 text-xs font-semibold uppercase select-none">{spaceName(group)}</h3>
                    </Show>
                    {/* (as the open chooser draws them, `TypeGrid`: each list a block, each type a button in the
                        colour of its type, as its chip is; an abstract class a line of the block) */}
                    <div class="flex items-start gap-3">
                      <For each={group.columns}>
                        {(column) => (
                          <ul
                            class="flex w-max flex-col divide-y-[0.5px] divide-slate-400/70 overflow-hidden rounded-xs border-[0.5px] border-slate-400/70 bg-white"
                            role="group"
                          >
                            <For each={column}>
                              {(row) => (
                                <li class="flex flex-col">
                                  <Show
                                    when={row.selectable && reasonFor(row.name) === undefined}
                                    fallback={
                                      <Show
                                        when={row.selectable}
                                        fallback={
                                          <span
                                            data-type-info={row.name}
                                            class="bg-slate-50 py-1 pr-4 text-xs text-slate-500 italic select-none"
                                            style={indent(row)}
                                            aria-disabled="true"
                                          >
                                            {modelName(row.name)}
                                          </span>
                                        }
                                      >
                                        {/* (in the menu, so the arrow keys reach it and a screen reader says why, but not chosen) */}
                                        <button
                                          data-type-info={row.name}
                                          type="button"
                                          role="menuitem"
                                          tabindex="-1"
                                          aria-disabled="true"
                                          data-unavailable
                                          class="block w-full max-w-xs min-w-28 cursor-not-allowed bg-slate-50 py-1.5 pr-4 text-left text-xs font-semibold text-slate-500 uppercase focus:bg-slate-400/20 focus:outline-none"
                                          style={indent(row)}
                                        >
                                          {modelName(row.name)}
                                          <span class="block text-xs font-normal whitespace-normal normal-case" data-reason>
                                            {reasonFor(row.name)}
                                          </span>
                                        </button>
                                      </Show>
                                    }
                                  >
                                    <button
                                      data-type-info={row.name}
                                      type="button"
                                      role="menuitem"
                                      tabindex="-1"
                                      class={[
                                        "flex w-full min-w-28 cursor-pointer items-center gap-3 py-1.5 pr-4 text-left text-xs font-semibold whitespace-nowrap uppercase select-none hover:shadow-[inset_0_0_0_100vmax_rgb(15_23_42/0.08)] focus:shadow-[inset_0_0_0_100vmax_rgb(15_23_42/0.12)] focus:outline-none active:shadow-[inset_0_0_0_100vmax_rgb(15_23_42/0.16)]",
                                        chipTint(row.name),
                                      ]}
                                      style={indent(row)}
                                      onClick={() => choose({ spaces: group.spaces, type: row.name })}
                                    >
                                      <span class="flex-1">{modelName(row.name)}</span>
                                      <Show when={props.counts?.[row.name] !== undefined}>
                                        <span class="font-normal tabular-nums opacity-70" data-count>
                                          {props.counts![row.name]}
                                        </span>
                                      </Show>
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

/** The type that all of `names` come from (the conjunctions left out), if they have one */
export function commonType(definitions: ModelDefinitions, names: string[]): string | undefined {
  const chains = [...new Set(names)]
    .filter((name) => getModel(definitions, name)?.kind !== "Conjunction")
    .map((name) => ancestry(definitions, name));
  if (chains.length === 0) return undefined;
  let at = 0;
  while (chains.every((chain) => chain[at] !== undefined && chain[at] === chains[0]![at])) at++;
  return at > 0 ? chains[0]![at - 1] : undefined;
}

/** What a box of types says it is for: Select Statement type…, by the type they all come from */
export function useSelectTitle(groups: () => MenuGroup[]) {
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const common = createMemo(() => commonType(definitions, choicesOf(groups()).map((choice) => choice.type)));
  return () =>
    common()
      ? t("select_type_of", "Select {name} type…", { name: modelName(common()!) })
      : t("select_type", "Select a type…");
}

/**
 * The types of `groups` laid out open, in zones one under another: the types on their own at the
 * top; then each semantic space, on its colour, with the same types inside it, its name at the top
 * left; then the conjunctions, on slate. Each type is a button in the colour of its type, as its
 * chip is; the buttons of a list are joined into one block, the names inside indented to show the
 * hierarchy (an abstract class is a line of the block, not a button). The types are one stop for
 * Tab; the arrow keys go through them (Home and End to the first and last). With `autofocus`, the
 * cursor goes into them when they are drawn. `spaceFooter` is drawn at the bottom of each space's zone (what can be
 * pasted into a new space of that kind).
 */
export function TypeGrid(props: {
  groups: MenuGroup[];
  onChoose: (choice: Choice) => void;
  autofocus?: boolean;
  spaceFooter?: (spaces: string[]) => JSX.Element;
}) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  const keyOf = (choice: Choice) => [...choice.spaces, choice.type].join("/");
  // (the one of the buttons that Tab goes to: the last one gone to, else the first)
  const [current, setCurrent] = createSignal<string>();
  // (in the order they are drawn, zone by zone)
  const tabStop = () => {
    const keys = zones().flatMap((zone) =>
      zone.columns.flat().filter((row) => row.selectable).map((row) => keyOf({ spaces: zone.spaces, type: row.name })),
    );
    return keys.includes(current() ?? "") ? current() : keys[0];
  };
  // (the conjunctions of the types on their own go to their zone at the bottom, those inside a space
  // stay in it; the lists of each are made again without the others, so they split as they would alone)
  const zones = createMemo(() => {
    const isConjunction = (name: string) => getModel(definitions, name)?.kind === "Conjunction";
    const namesOf = (group: MenuGroup, conjunctions: boolean) =>
      group.columns
        .flat()
        .filter((row) => row.selectable && isConjunction(row.name) === conjunctions)
        .map((row) => row.name);
    const columnsOf = (names: string[]) => (names.length > 0 ? typeColumns(definitions, names) : []);
    const found: { spaces: string[]; columns: TypeRow[][]; class: string }[] = [];
    const plain = props.groups.find((group) => group.spaces.length === 0);
    if (plain) found.push({ spaces: [], columns: columnsOf(namesOf(plain, false)), class: "" });
    for (const group of props.groups) {
      if (group.spaces.length === 0) continue;
      found.push({
        spaces: group.spaces,
        columns: [...columnsOf(namesOf(group, false)), ...columnsOf(namesOf(group, true))],
        class: groupTint(definitions, group),
      });
    }
    if (plain) found.push({ spaces: [], columns: columnsOf(namesOf(plain, true)), class: "bg-slate-400/20" });
    return found.filter((zone) => zone.columns.length > 0);
  });
  let root: HTMLDivElement | undefined;
  const onKeyDown = (event: KeyboardEvent) => {
    const all = [...(root?.querySelectorAll<HTMLElement>("button[data-choice]") ?? [])];
    const at = all.indexOf(document.activeElement as HTMLElement);
    if (at < 0 || all.length === 0) return;
    const next =
      event.key === "ArrowDown" || event.key === "ArrowRight"
        ? (at + 1) % all.length
        : event.key === "ArrowUp" || event.key === "ArrowLeft"
          ? (at - 1 + all.length) % all.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? all.length - 1
              : undefined;
    if (next === undefined) return;
    event.preventDefault();
    all[next]!.focus();
  };
  onSettled(() => {
    if (props.autofocus) root?.querySelector<HTMLElement>('button[data-choice][tabindex="0"]')?.focus();
  });
  const spaceName = (spaces: string[]) => spaces.map((space) => modelName(space)).join(" › ");
  // (a button is in the colour of its type, as its chip is; a type with none has the plain one)
  const tintOf = (name: string) => {
    const model = getModel(definitions, name);
    return kindTint(model?.kind, model?.interfaceMeta?.colour) || plainTint;
  };
  // (the name inside a button or an abstract class's line, indented by how deep it is)
  const indent = (row: TypeRow) => ({ "padding-left": `${0.75 + row.depth * 1}rem` });
  return (
    <div ref={root} class="flex flex-col" onKeyDown={onKeyDown}>
      <For each={zones()}>
        {(zone) => (
          <section
            class={[
              "flex flex-col gap-2 px-3 pt-2 pb-3",
              { "border-t-[0.5px] border-dashed border-slate-400/60": zone.class !== "" },
              zone.class,
            ]}
          >
            <Show when={zone.spaces.length > 0}>
              <h3 class="text-xs font-semibold uppercase select-none">{spaceName(zone.spaces)}</h3>
            </Show>
            <div class="flex flex-wrap items-start gap-3">
              <For each={zone.columns}>
                {(column) => (
                  <ul class="flex w-max flex-col divide-y-[0.5px] divide-slate-400/70 overflow-hidden rounded-xs border-[0.5px] border-slate-400/70 bg-white shadow-xs">
                    <For each={column}>
                      {(row) => (
                        <li class="flex flex-col">
                          <Show
                            when={row.selectable}
                            fallback={
                              <span
                                data-type-info={row.name}
                                class="bg-slate-50 py-1 pr-4 text-xs text-slate-500 italic select-none"
                                style={indent(row)}
                                aria-disabled="true"
                              >
                                {modelName(row.name)}
                              </span>
                            }
                          >
                            <button
                              data-type-info={row.name}
                              type="button"
                              data-choice
                              tabindex={tabStop() === keyOf({ spaces: zone.spaces, type: row.name }) ? 0 : -1}
                              autofocus={
                                props.autofocus && tabStop() === keyOf({ spaces: zone.spaces, type: row.name })
                              }
                              class={[
                                "min-w-28 cursor-pointer py-1.5 pr-4 text-left text-xs font-semibold whitespace-nowrap uppercase select-none hover:shadow-[inset_0_0_0_100vmax_rgb(15_23_42/0.08)] focus:shadow-[inset_0_0_0_100vmax_rgb(15_23_42/0.12)] focus:outline-none active:shadow-[inset_0_0_0_100vmax_rgb(15_23_42/0.16)]",
                                tintOf(row.name),
                              ]}
                              style={indent(row)}
                              onFocus={() => setCurrent(keyOf({ spaces: zone.spaces, type: row.name }))}
                              onClick={() => props.onChoose({ spaces: zone.spaces, type: row.name })}
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
            <Show when={zone.spaces.length > 0 && props.spaceFooter}>{props.spaceFooter!(zone.spaces)}</Show>
          </section>
        )}
      </For>
    </div>
  );
}

/**
 * The add button of a field (Add statements), which opens, in its place, a box of the types the field
 * can hold (a `TypeGrid`), under a title bar that names what is chosen (Select statement type…, by
 * the type they all come from). Choosing one, Escape, the close button, a click elsewhere or Tab out
 * of it close the box. With only one thing to choose the button chooses it. What is given as
 * `children` (what can be pasted here) is under the button; `inSpace` is drawn at the bottom of each semantic
 * space's zone of the box (what can be pasted into a new space of that kind), and given what closes the box.
 */
export function TypeChooser(
  props: ParentProps<{
    groups: MenuGroup[];
    /** What the button says (Add statements), and the name of the box for a screen reader */
    label: string;
    onChoose: (choice: Choice) => void;
    /** The classes of the button */
    buttonClass?: string;
    inSpace?: (spaces: string[], close: () => void) => JSX.Element;
  }>,
) {
  const { t } = useTranslations();
  const choices = () => choicesOf(props.groups);
  const title = useSelectTitle(() => props.groups);
  let root: HTMLDivElement | undefined;
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      // (only the box: a dialog it is in stays open)
      event.stopPropagation();
      close(true);
    }
  };
  const [open, setOpen] = createSignal(false);
  let wrapper: HTMLDivElement | undefined;
  const openBox = () => {
    setOpen(true);
    // (after the click that opened it, not during it: the box is drawn in the button's place, and the click, going on
    // to the document, would find itself outside it and close it; then all of it in view, and the cursor in the types)
    setTimeout(() => {
      root?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
      root?.querySelector<HTMLElement>('button[data-choice][tabindex="0"]')?.focus({ preventScroll: true });
    });
  };
  // (back to the button, which is drawn again in the box's place)
  const close = (refocus: boolean) => {
    setOpen(false);
    if (!refocus) return;
    flush();
    wrapper?.querySelector<HTMLElement>("button[aria-expanded]")?.focus();
  };
  const choose = (choice: Choice) => {
    setOpen(false);
    props.onChoose(choice);
  };
  onSettled(() => {
    // (a click anywhere else closes it; the path is the one when it was clicked, as the button is gone once the box opens)
    const away = (event: MouseEvent) => {
      if (open() && wrapper && !event.composedPath().includes(wrapper)) setOpen(false);
    };
    document.addEventListener("click", away);
    return () => document.removeEventListener("click", away);
  });
  return (
    <Show when={choices().length > 0}>
      <div ref={wrapper} class="flex w-full flex-col gap-2">
        <Show
          when={open()}
          fallback={
            <Show
              when={choices().length > 1}
              fallback={
                <button type="button" class={props.buttonClass ?? smallButtonClass} onClick={() => choose(choices()[0]!)}>
                  {props.label}
                </button>
              }
            >
              <button
                type="button"
                class={props.buttonClass ?? smallButtonClass}
                aria-expanded="false"
                onClick={openBox}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    openBox();
                  }
                }}
              >
                {props.label} <span aria-hidden="true">▾</span>
              </button>
            </Show>
          }
        >
        <div
          ref={root}
          role="group"
          aria-label={props.label}
          class="flex w-full flex-col overflow-hidden rounded-xs border-[0.5px] border-dashed border-slate-400/80 bg-white/60"
          onKeyDown={onKeyDown}
          onFocusOut={(event) => {
            // (Tab out of it closes it)
            const to = event.relatedTarget;
            if (to instanceof Node && root && !root.contains(to)) setOpen(false);
          }}
        >
          <div class="flex items-stretch border-b-[0.5px] border-dashed border-slate-400/80 bg-slate-100 text-xs font-semibold tracking-wide text-slate-700 uppercase select-none">
            <span class="flex flex-1 items-center gap-2 px-3 py-1.5">
              <span aria-hidden="true" class="text-sm leading-none text-slate-500">
                +
              </span>
              {title()}
            </span>
            <button
              type="button"
              class="flex w-8 shrink-0 cursor-pointer items-center justify-center border-l-[0.5px] border-dashed border-slate-400/80 text-slate-500 hover:bg-slate-300/50 hover:text-slate-800 focus:bg-slate-300/50 focus:outline-none"
              aria-label={t("close", "Close")}
              title={t("close", "Close")}
              onClick={() => close(true)}
            >
              ✕
            </button>
          </div>
          <TypeGrid
            groups={props.groups}
            onChoose={choose}
            spaceFooter={props.inSpace && ((spaces) => props.inSpace!(spaces, () => setOpen(false)))}
          />
        </div>
        </Show>
        {props.children}
      </div>
    </Show>
  );
}
