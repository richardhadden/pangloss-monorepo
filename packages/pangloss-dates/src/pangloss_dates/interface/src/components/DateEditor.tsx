import {
  inputClass,
  ModelFields,
  useItemForm,
  useTranslations,
} from "@pangloss/interface-core";
import type { EditCardProps } from "@pangloss/interface-core";
import { For, Match, Show, Switch } from "solid-js";
import { formatDate, MONTHS } from "../format";

type Data = Record<string, unknown>;
type Path = (string | number)[];

// (what the server works out from the rest, whatever is sent: never typed in)
const WORKED_OUT = [
  "precision",
  "earliestFuzzy",
  "earliestStrict",
  "latestStrict",
  "latestFuzzy",
  "sortDay",
  "endSortDay",
  "patternKeys",
];
// (what any date has beside what it is: under it, in rows)
const COMMON = ["calendar", "sortBy", "sourceText"];

const isData = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * The editor of a date (the card `Date` names for `edit_card`, which the other dates have from it):
 * only what a person says of a date, never the bounds and sort days the server works out. An exact
 * date is its year, month and day on one line; a range, its earliest and latest; an EDTF date, the
 * text. A period and a recurrence are their fields, with their start and end each a date again (and
 * so this editor again). Then the calendar, what to sort by and what the source said, and the date
 * as it reads.
 */
export default function DateEditor(props: EditCardProps) {
  const form = useItemForm();
  const { t } = useTranslations();
  const reads = () => {
    const text = formatDate(props.value);
    // (not until it is all there: a range without its latest does not read)
    return text && !text.includes("undefined") ? text : undefined;
  };
  return (
    <div class="flex min-w-0 flex-col gap-5">
      <Switch
        fallback={
          <ModelFields
            model={props.model}
            path={() => props.path}
            env={{}}
            skip={[...WORKED_OUT, ...COMMON]}
          />
        }
      >
        <Match when={props.type === "ExactDate"}>
          <ExactParts path={props.path} label={props.label} />
        </Match>
        <Match when={props.type === "DateRange"}>
          <div class="grid grid-cols-[10rem_minmax(0,1fr)] items-center gap-x-6 gap-y-3">
            <span class="text-xs font-semibold text-slate-500 uppercase">
              {t("date_earliest", "Earliest")}
            </span>
            <ExactParts
              path={[...props.path, "earliest"]}
              label={`${props.label} ${t("date_earliest", "Earliest")}`}
            />
            <span class="text-xs font-semibold text-slate-500 uppercase">
              {t("date_latest", "Latest")}
            </span>
            <ExactParts
              path={[...props.path, "latest"]}
              label={`${props.label} ${t("date_latest", "Latest")}`}
            />
          </div>
        </Match>
        <Match when={props.type === "EDTFDate"}>
          <div class="flex flex-col gap-1">
            <input
              type="text"
              class={[inputClass, "max-w-sm font-mono"]}
              aria-label={`${props.label} EDTF`}
              placeholder="1500-03~"
              value={
                typeof props.value.edtf === "string" ? props.value.edtf : ""
              }
              onInput={(event) =>
                form.set([...props.path, "edtf"], event.currentTarget.value)
              }
            />
            <p class="text-xs text-slate-500">
              {t(
                "date_edtf_help",
                "Extended Date/Time Format: 1500-03~ is about March 1500, 15XX some year of the 1500s, 1500/1510 from 1500 to 1510",
              )}
            </p>
          </div>
        </Match>
      </Switch>
      <ModelFields
        model={props.model}
        path={() => props.path}
        env={{}}
        skip={props.model.fields
          .map((field) => field.key)
          .filter((key) => !COMMON.includes(key))}
      />
      <Show when={reads()}>
        <p class="text-sm text-slate-600" data-testid="date-reads">
          <span class="mr-2 text-xs font-semibold text-slate-500 uppercase select-none">
            {t("date_reads", "Reads")}
          </span>
          {reads()}
        </p>
      </Show>
    </div>
  );
}

/**
 * An exact date at `path` of the form, on one line: the year, the month (by name) and the day, each
 * left out by leaving it empty. It is always an `ExactDate`, also where it is the end of a range that
 * has none yet.
 */
function ExactParts(props: { path: Path; label: string }) {
  const form = useItemForm();
  const { t } = useTranslations();
  const value = (): Data => {
    const at = form.get(props.path);
    return isData(at) ? at : {};
  };
  const part = (key: string) => {
    const at = value()[key];
    return typeof at === "number" ? String(at) : "";
  };
  // (each part by itself, never a copy of the whole date: a copy read before the last change is
  // applied would undo it)
  const write = (key: string, typed: string) => {
    if (value().type !== "ExactDate")
      form.set([...props.path, "type"], "ExactDate");
    if (typed === "") form.remove([...props.path, key]);
    else form.set([...props.path, key], Number(typed));
  };
  return (
    // (each part in a box of its width: the input fills it)
    <div class="flex flex-wrap items-center gap-2">
      <div class="w-28 shrink-0">
        <input
          type="number"
          step="1"
          class={inputClass}
          aria-label={`${props.label} ${t("date_year", "Year")}`}
          placeholder={t("date_year", "Year")}
          value={part("year")}
          onInput={(event) => write("year", event.currentTarget.value)}
        />
      </div>
      <div class="w-40 shrink-0">
        <select
          class={inputClass}
          aria-label={`${props.label} ${t("date_month", "Month")}`}
          value={part("month")}
          onChange={(event) => write("month", event.currentTarget.value)}
        >
          <option value="">{t("date_no_month", "(no month)")}</option>
          <For each={MONTHS}>
            {(name, index) => (
              <option
                value={String(index() + 1)}
                selected={part("month") === String(index() + 1)}
              >
                {name}
              </option>
            )}
          </For>
        </select>
      </div>
      <div class="w-20 shrink-0">
        <input
          type="number"
          step="1"
          min="1"
          max="31"
          class={inputClass}
          aria-label={`${props.label} ${t("date_day", "Day")}`}
          placeholder={t("date_day", "Day")}
          value={part("day")}
          onInput={(event) => write("day", event.currentTarget.value)}
        />
      </div>
    </div>
  );
}
