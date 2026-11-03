import { ConsoleButton, useComponent, useNavExpanded, useTranslations } from "@pangloss/interface-core";
import { For, Loading } from "solid-js";
import type { ParentProps } from "solid-js";
import { CALENDARS } from "../api";
import type { CalendarName } from "../api";
import { sayCalendar, yearsHref } from "../days";

/** The `main` of a calendar page, inset as the other pages are */
export function CalendarPage(props: ParentProps) {
  const { navPinned } = useNavExpanded();
  return (
    <main class={["w-full py-8", { "px-8": navPinned(), "px-20": !navPinned() }]}>{props.children}</main>
  );
}

/**
 * The console of a calendar page: "Calendar" and the page's `label` on the left; on the right the way to the years, and
 * the two calendars, the one the page is read in pressed. `hrefOf` gives the same page in a calendar (it may read what
 * the page is still loading: the buttons wait for it, the rest of the console does not).
 */
export function CalendarConsole(props: {
  label?: string;
  calendar: CalendarName;
  hrefOf: (calendar: CalendarName) => string | undefined;
}) {
  const Console = useComponent("Console");
  const { t } = useTranslations();
  const buttons = (hrefOf: (calendar: CalendarName) => string | undefined) => (
    <For each={CALENDARS}>
      {(each) => (
        <ConsoleButton
          label={sayCalendar(each, t)}
          href={hrefOf(each)}
          pressed={props.calendar === each}
          disabled={hrefOf(each) === undefined}
          text
        />
      )}
    </For>
  );
  return (
    <Console type={t("calendar", "Calendar")} label={props.label}>
      <ConsoleButton label={t("calendar_years", "Years")} href={yearsHref(props.calendar)} text>
        <svg
          viewBox="0 0 24 24"
          class="size-4 select-none fill-none stroke-current stroke-2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <rect x="3" y="5" width="18" height="16" rx="1" />
          <path d="M3 10h18M8 3v4M16 3v4" />
        </svg>
      </ConsoleButton>
      <Loading fallback={buttons(() => undefined)}>{buttons(props.hrefOf)}</Loading>
    </Console>
  );
}

/** The buttons that step back and forward (a month, a day): links, or disabled while where they go is not known */
export function Arrows(props: { previous?: string; next?: string; previousLabel: string; nextLabel: string }) {
  const classes = (href: string | undefined) => [
    "flex size-8 shrink-0 items-center justify-center rounded-sm border-[0.5px] border-slate-400/70 bg-white select-none",
    { "cursor-pointer": href !== undefined, "hover:bg-slate-100": href !== undefined, "opacity-40": href === undefined },
  ];
  return (
    <div class="flex items-center gap-1">
      <a href={props.previous} aria-label={props.previousLabel} title={props.previousLabel} class={classes(props.previous)}>
        <svg viewBox="0 0 24 24" class="size-4 fill-none stroke-current stroke-2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M15 5l-7 7 7 7" />
        </svg>
      </a>
      <a href={props.next} aria-label={props.nextLabel} title={props.nextLabel} class={classes(props.next)}>
        <svg viewBox="0 0 24 24" class="size-4 fill-none stroke-current stroke-2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M9 5l7 7-7 7" />
        </svg>
      </a>
    </div>
  );
}

/** What a page says when its address is not a day or a month of the calendar */
export function BadAddress() {
  const { t } = useTranslations();
  return (
    <CalendarPage>
      <p role="alert" class="text-slate-700">
        {t("calendar_bad_address", "That is not a day of the calendar: the address is /calendar/julian/1500/3/2 (or gregorian).")}
      </p>
    </CalendarPage>
  );
}
