import { ConsoleButton, useTranslations } from "@pangloss/interface-core";
import type { ConsoleActionProps } from "@pangloss/interface-core";
import { Portal } from "@solidjs/web";
import { createSignal, flush, For, onSettled, Show } from "solid-js";

// (the names of the formats: the same in every language)
const FORMATS = [
  { format: "ttl", name: "Turtle" },
  { format: "jsonld", name: "JSON-LD" },
  { format: "trig", name: "TriG" },
  { format: "nt", name: "N-Triples" },
  { format: "nq", name: "N-Quads" },
];
const MENU_ITEM =
  "px-3 py-1 whitespace-nowrap select-none hover:bg-slate-200 focus:bg-slate-200 focus:outline-none";

/**
 * An item as RDF, as the API gives it, in a new tab (not a page of the interface): a button that opens a small menu of
 * the formats, and the API's own JSON. Down or Up opens it, and they go through it; Escape and Tab close it.
 */
export default function ViewRdf(props: ConsoleActionProps) {
  const { t } = useTranslations();
  const [open, setOpen] = createSignal(false);
  // (in the body, placed from where the button is: the console bar clips what is put in it. It opens towards the room there is)
  const [place, setPlace] = createSignal<Record<string, string>>({});
  let root: HTMLDivElement | undefined;
  let menu: HTMLDivElement | undefined;
  let opener: HTMLElement | undefined;

  const items = () => [...(menu?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
  const show = () => {
    const box = opener?.getBoundingClientRect();
    if (box !== undefined) {
      const right = `${document.documentElement.clientWidth - box.right}px`;
      setPlace(
        box.top > window.innerHeight / 2
          ? { right, bottom: `${window.innerHeight - box.top}px` }
          : { right, top: `${box.bottom}px` },
      );
    }
    setOpen(true);
  };
  const onKeyDown = (event: KeyboardEvent) => {
    // (from the menu it is heard twice: there, and on the button's side, as a portal passes events on)
    if (event.defaultPrevented) return;
    if (event.key === "Escape" && open()) {
      setOpen(false);
      opener?.focus();
    } else if (event.key === "Tab") {
      setOpen(false);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const down = event.key === "ArrowDown";
      if (!open()) {
        show();
        // (the menu drawn, then into it)
        flush();
      }
      const all = items();
      const at = all.indexOf(document.activeElement as HTMLElement);
      const next = at < 0 ? (down ? 0 : all.length - 1) : (at + (down ? 1 : -1) + all.length) % all.length;
      all[next]?.focus();
    }
  };
  onSettled(() => {
    // (a click anywhere else closes it)
    const away = (event: MouseEvent) => {
      const target = event.target as Node;
      if (root && !root.contains(target) && !menu?.contains(target)) setOpen(false);
    };
    document.addEventListener("click", away);
    return () => document.removeEventListener("click", away);
  });
  const href = (format: string) =>
    `/api/rdf/${encodeURIComponent(props.type)}/${encodeURIComponent(props.id)}?format=${format}&view=true`;

  return (
    <Show when={props.page === "item"}>
      <div ref={root} class="relative flex h-full shrink-0" onKeyDown={onKeyDown}>
        <ConsoleButton
          label={t("view_rdf", "View as RDF")}
          pressed={open()}
          elementRef={(element: HTMLElement) => (opener = element)}
          onClick={() => (open() ? setOpen(false) : show())}
        >
          {/* (three nodes joined: a graph) */}
          <svg viewBox="0 0 24 24" class="size-5 select-none fill-none stroke-current stroke-[1.5]" aria-hidden="true">
            <circle cx="6" cy="6" r="2.5" />
            <circle cx="18" cy="9" r="2.5" />
            <circle cx="9" cy="18" r="2.5" />
            <path d="M8.4 6.6l7.2 1.8M6.9 8.4l1.4 7.2M16.3 10.9l-5.6 5.3" />
          </svg>
        </ConsoleButton>
        <Show when={open()}>
          <Portal>
            <div
              ref={menu}
              role="menu"
              onKeyDown={onKeyDown}
              aria-label={t("view_rdf", "View as RDF")}
              style={place()}
              class="fixed z-50 flex min-w-32 flex-col rounded-xs border-[0.5px] border-slate-400/70 bg-white py-1 text-sm font-normal normal-case text-slate-800 shadow-md"
            >
              <For each={FORMATS}>
                {(entry) => (
                  <a
                    role="menuitem"
                    href={href(entry.format)}
                    target="_blank"
                    rel="noopener"
                    class={MENU_ITEM}
                    onClick={() => setOpen(false)}
                  >
                    {entry.name}
                  </a>
                )}
              </For>
              {/* (what the API itself gives: the console leaves this link to the menu, `jsonLinkIn`) */}
              <a
                role="menuitem"
                href={`/api/${encodeURIComponent(props.type)}/${encodeURIComponent(props.id)}`}
                target="_blank"
                rel="noopener"
                class={[MENU_ITEM, "border-t-[0.5px] border-slate-400/70"]}
                onClick={() => setOpen(false)}
              >
                API JSON
              </a>
            </div>
          </Portal>
        </Show>
      </div>
    </Show>
  );
}
