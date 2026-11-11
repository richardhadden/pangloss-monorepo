import { createSignal, createUniqueId, For, Show } from "solid-js";
import { useModels, useTranslations } from "../../context";
import { buttonClass, kindTint } from "../../primitives";
import { getModel } from "../../schema";

/** One thing to choose; `group` heads the options after it while it is the same */
export interface MenuOption {
  value: string;
  label: string;
  group?: string;
  /** A model the option is of: shown before the label as a type is everywhere, a tinted chip */
  type?: string;
}

// (a box that chooses, as a text box looks: the same hairline, height and text; open, it is joined on to its list,
// as the search for an entity is)
const FIELD =
  "flex h-8 w-full min-w-0 cursor-pointer items-center gap-2 border-[0.5px] bg-white/80 pr-2 pl-2 text-left text-sm select-none focus:outline-none";
const SMALL_FIELD =
  "flex h-6.5 w-full min-w-0 cursor-pointer items-center gap-2 border-[0.5px] bg-white/80 pr-1.5 pl-2 text-left text-sm select-none focus:outline-none";

/**
 * A menu that chooses one of `options`, for the search form: a box as a text box is (`field`, 32px; `small`, 26px, as
 * the buttons beside it), or a button that adds something (`add`: `+ label`, the dashed button). Its list opens under
 * it, as the search for an entity does. The keys are those of a select: Down, Up, Enter or Space open it; Up, Down,
 * Home and End go through it; Enter or Space chooses; Escape and Tab close it. The focus stays on the button (the
 * list is its `aria-activedescendant`).
 */
export function MenuSelect(props: {
  /** Its name, for a screen reader (and the tests) */
  label: string;
  options: MenuOption[];
  /** The value chosen (a `field`: shown in the box) */
  value?: string;
  /** What the box says when nothing is chosen; what an `add` button says (after its +) */
  placeholder?: string;
  look?: "field" | "small" | "add";
  /** Classes of its width (`w-36`; as wide as it is, by default) */
  class?: string;
  onChoose: (value: string) => void;
}) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  const tintOf = (type: string) => {
    const model = getModel(definitions, type);
    return kindTint(model?.kind, model?.interfaceMeta?.colour) || "bg-slate-400/20 text-slate-800";
  };
  const id = createUniqueId();
  const [open, setOpen] = createSignal(false);
  const [active, setActive] = createSignal(0);
  const look = () => props.look ?? "field";
  const chosen = () => props.options.find((option) => option.value === props.value);
  const optionId = (index: number) => `${id}-${index}`;
  const show = (index: number) => {
    setActive(index);
    // (the active option in view, in a long list)
    queueMicrotask(() => document.getElementById(optionId(index))?.scrollIntoView?.({ block: "nearest" }));
  };
  const openAt = (index: number) => {
    setOpen(true);
    show(Math.max(0, index));
  };
  const chosenIndex = () => props.options.findIndex((option) => option.value === props.value);
  const choose = (index: number) => {
    const option = props.options[index];
    setOpen(false);
    if (option) props.onChoose(option.value);
  };
  const onKeyDown = (event: KeyboardEvent) => {
    const last = props.options.length - 1;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const down = event.key === "ArrowDown";
      if (!open()) openAt(chosenIndex() >= 0 ? chosenIndex() : down ? 0 : last);
      else show(Math.min(last, Math.max(0, active() + (down ? 1 : -1))));
    } else if ((event.key === "Home" || event.key === "End") && open()) {
      event.preventDefault();
      show(event.key === "Home" ? 0 : last);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      // (Enter in the search form searches at once: not when it chooses)
      event.stopPropagation();
      if (open()) choose(active());
      else openAt(chosenIndex());
    } else if (event.key === "Escape" && open()) {
      // (only the list: a dialog or panel it is in stays open)
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  };
  const fieldFrame = () => [
    look() === "small" ? SMALL_FIELD : FIELD,
    { "rounded-xs border-slate-400/70 hover:border-slate-500 focus-visible:border-slate-600": !open() },
    { "rounded-t-xs border-slate-600": open() },
  ];
  const groupAt = (index: number) => {
    const group = props.options[index]?.group;
    return group !== undefined && group !== props.options[index - 1]?.group ? group : undefined;
  };
  return (
    <div class={["relative", props.class ?? "w-fit"]}>
      <button
        type="button"
        role="combobox"
        aria-label={props.label}
        aria-haspopup="listbox"
        aria-expanded={open() ? "true" : "false"}
        aria-controls={id}
        aria-activedescendant={open() ? optionId(active()) : undefined}
        data-value={props.value}
        class={look() === "add" ? buttonClass("add", "sm") : fieldFrame()}
        onClick={() => (open() ? setOpen(false) : openAt(chosenIndex()))}
        onKeyDown={onKeyDown}
        onBlur={() => setOpen(false)}
      >
        <Show
          when={look() !== "add"}
          fallback={<>+ {props.placeholder}</>}
        >
          <span class={["min-w-0 flex-1 truncate", { "text-slate-500": !chosen() }]}>
            {chosen()?.label ?? props.placeholder ?? " "}
          </span>
          <svg
            viewBox="0 0 24 24"
            class={["size-3.5 shrink-0 fill-none stroke-current stroke-2 text-slate-500 transition-transform select-none", { "rotate-180": open() }]}
            stroke-linecap="square"
            aria-hidden="true"
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </Show>
      </button>
      <Show when={open()}>
        <ul
          id={id}
          role="listbox"
          aria-label={props.label}
          class={[
            // (a long list scrolls up and down, never across: the room of its scroll bar is kept, where one takes room)
            "absolute top-full left-0 z-30 max-h-72 w-max max-w-sm overflow-x-hidden overflow-y-auto [scrollbar-gutter:stable] border-[0.5px] border-slate-600 bg-white shadow-lg",
            // (joined on to a box, at least as wide as it; under a button, a little below it)
            { "-mt-px min-w-full rounded-tr-xs rounded-b-xs": look() !== "add" },
            { "mt-1 min-w-48 rounded-xs": look() === "add" },
          ]}
        >
          <For each={props.options}>
            {(option, index) => (
              <>
                <Show when={groupAt(index())}>
                  <li
                    role="presentation"
                    class="border-t-[0.5px] border-slate-400/30 bg-slate-400/10 px-3 pt-1.5 pb-1 text-xs font-semibold text-slate-500 uppercase select-none first:border-t-0"
                  >
                    {groupAt(index())}
                  </li>
                </Show>
                <li
                  id={optionId(index())}
                  role="option"
                  data-value={option.value}
                  // (what a screen reader says of one with a type: the type, then the label)
                  aria-label={option.type ? `${modelName(option.type)} · ${option.label}` : undefined}
                  aria-selected={option.value === props.value ? "true" : "false"}
                  class={[
                    "flex cursor-pointer items-center gap-2 border-t-[0.5px] border-slate-400/30 px-3 py-1.5 text-sm select-none first:border-t-0",
                    { "bg-slate-400/25": active() === index() },
                    { "font-semibold": option.value === props.value },
                  ]}
                  // (the button keeps the focus, so the list is not closed before the click)
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseMove={() => setActive(index())}
                  onClick={() => choose(index())}
                >
                  <Show when={option.type}>
                    <span
                      data-type-info={option.type}
                      class={["shrink-0 rounded-xs px-1.5 py-0.5 text-xs font-semibold uppercase", tintOf(option.type!)]}
                    >
                      {modelName(option.type!)}
                    </span>
                  </Show>
                  <span class="min-w-0 truncate">{option.label}</span>
                </li>
              </>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}
