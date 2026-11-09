import { ReferenceChip, smallButtonClass, useApi, useTranslations } from "@pangloss/interface-core";
import { createSignal, For, Show } from "solid-js";
import { getCovering } from "../api";
import type { CalendarName, DayOut, Spanning } from "../api";
import { itemHref, nameOf, sayDate } from "../days";

/**
 * The long periods that cover all of what the page shows (a residence from 1456 with no known end, on a day of 1500):
 * there can be thousands, and none says anything of the day or the month in particular, so the page has only how many
 * there are, and they are read when asked for, a page at a time. (Listed with the dates of the day, or drawn as bars
 * across the month, they made a page of megabytes.)
 */
export function Covering(props: CoveringProps) {
  return (
    <Show when={props.count > 0}>
      <CoveringList {...props} />
    </Show>
  );
}

interface CoveringProps {
  /** How many there are (from the day's or the month's report) */
  count: number;
  /** The days the page shows */
  first: DayOut;
  last: DayOut;
  calendar: CalendarName;
  /** What they are, of this page: "Long periods that include this day" */
  heading: string;
}

function CoveringList(props: CoveringProps) {
  const api = useApi();
  const { t, language, fieldName } = useTranslations();
  const [shown, setShown] = createSignal<Spanning[]>([]);
  const [nextPage, setNextPage] = createSignal(1);
  const [loading, setLoading] = createSignal(false);
  const left = () => props.count - shown().length;
  const load = async () => {
    setLoading(true);
    try {
      const page = await getCovering(api, props.first.jdn, props.last.jdn, nextPage());
      setShown((before) => [...before, ...page.results]);
      setNextPage((page) => page + 1);
    } finally {
      setLoading(false);
    }
  };
  const range = (item: Spanning) =>
    `${sayDate(nameOf(item.first, props.calendar), language(), t)} – ${sayDate(nameOf(item.last, props.calendar), language(), t)}`;
  return (
    <section class="mt-6" aria-labelledby="calendar-covering" data-testid="calendar-covering">
      <h2 id="calendar-covering" class="mb-2 text-xs font-semibold text-slate-500 uppercase">
        {props.heading}
        <span class="ml-1 font-normal normal-case">({props.count})</span>
      </h2>
      <ul class="grid grid-cols-[max-content_fit-content(26rem)_minmax(0,1fr)] gap-x-4 gap-y-2">
        <For each={shown()}>
          {(item) => (
            <li class="col-span-3 grid min-w-0 grid-cols-subgrid items-center">
              <span class="text-xs font-semibold text-slate-500 uppercase">{fieldName(item.ref.type, item.ref.field)}</span>
              <span class="flex min-w-0">
                <ReferenceChip type={item.ref.type} label={item.ref.label} href={itemHref(item.ref.type, item.ref.id)} />
              </span>
              <span class="truncate text-xs text-slate-500 italic">{range(item)}</span>
            </li>
          )}
        </For>
      </ul>
      <Show when={left() > 0}>
        <button
          type="button"
          class={[smallButtonClass, "text-slate-600 disabled:text-slate-400", shown().length > 0 && "mt-3"]}
          disabled={loading()}
          onClick={() => void load()}
        >
          {shown().length === 0
            ? t("calendar_covering_show", "Show them")
            : t("calendar_covering_more", "and {count} more", { count: left() })}
        </button>
      </Show>
    </section>
  );
}
