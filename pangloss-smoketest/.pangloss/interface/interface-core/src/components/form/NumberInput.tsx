import { useTranslations } from "../../context";

/**
 * A `beforeinput` handler that refuses what has a character not matched by `allowed` (one character
 * at a time), as it is typed, pasted or dropped: it never gets into the box. Deleting is always let
 * through.
 */
export function allowOnly(allowed: RegExp) {
  return (event: InputEvent) => {
    const text = event.data ?? event.dataTransfer?.getData("text/plain") ?? "";
    if (text !== "" && ![...text].every((character) => allowed.test(character))) event.preventDefault();
  };
}

// (whole numbers, with a minus; and numbers with a point)
export const integerCharacters = /[0-9-]/;
export const decimalCharacters = /[0-9.-]/;

/**
 * A box for a number, with its own up and down buttons joined on to its right end (the browser's
 * spinner is hidden: it cannot be styled). The buttons step as the keys do (`stepUp`/`stepDown`, so
 * `step`, `min` and `max` hold), and keep the focus where it is; the Up and Down keys still step in
 * the box. Characters that are not in a number are refused (`allowed`).
 */
export function NumberInput(props: {
  value: string;
  onInput: (typed: string) => void;
  /** The name of the box for a screen reader */
  label: string;
  placeholder?: string;
  step?: number | "any";
  min?: number;
  max?: number;
  allowed?: RegExp;
  /** The width of the whole (the box and its buttons) */
  class?: string;
}) {
  const { t } = useTranslations();
  let box: HTMLInputElement | undefined;
  const stepBy = (up: boolean) => {
    if (!box) return;
    // ("any" cannot be stepped: a step of 1 for that)
    if (box.step === "any") box.step = "1";
    try {
      if (up) box.stepUp();
      else box.stepDown();
    } finally {
      if (props.step === "any") box.step = "any";
    }
    props.onInput(box.value);
  };
  const button =
    "flex flex-1 cursor-pointer items-center justify-center px-1.5 text-slate-500 select-none hover:bg-slate-300/50 hover:text-slate-800 active:bg-slate-400/40";
  return (
    <div
      class={[
        "flex min-w-0 items-stretch overflow-hidden rounded-xs border-[0.5px] border-slate-400/70 bg-white/80 focus-within:border-slate-600",
        props.class ?? "w-full",
      ]}
    >
      <input
        ref={box}
        type="number"
        class="min-w-0 flex-1 [appearance:textfield] bg-transparent px-2 py-1.5 text-sm focus:outline-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        aria-label={props.label}
        placeholder={props.placeholder}
        step={props.step ?? 1}
        min={props.min}
        max={props.max}
        value={props.value}
        onBeforeInput={allowOnly(props.allowed ?? (props.step === "any" ? decimalCharacters : integerCharacters))}
        onInput={(event) => props.onInput(event.currentTarget.value)}
      />
      <div class="flex shrink-0 flex-col border-l-[0.5px] border-slate-400/70">
        <button
          type="button"
          tabindex="-1"
          class={button}
          aria-label={t("step_up", "Increase {name}", { name: props.label })}
          // (the focus stays in the box)
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => stepBy(true)}
        >
          <svg viewBox="0 0 10 6" class="h-1.5 w-2.5 fill-none stroke-current stroke-[1.5]" aria-hidden="true">
            <path d="M1 5l4-4 4 4" />
          </svg>
        </button>
        <button
          type="button"
          tabindex="-1"
          class={[button, "border-t-[0.5px] border-slate-400/70"]}
          aria-label={t("step_down", "Decrease {name}", { name: props.label })}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => stepBy(false)}
        >
          <svg viewBox="0 0 10 6" class="h-1.5 w-2.5 fill-none stroke-current stroke-[1.5]" aria-hidden="true">
            <path d="M1 1l4 4 4-4" />
          </svg>
        </button>
      </div>
    </div>
  );
}
