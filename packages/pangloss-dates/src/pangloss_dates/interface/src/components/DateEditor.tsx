import { allowOnly, inputClass, ModelFields, useItemForm, useTranslations } from "@pangloss/interface-core";
import type { EditCardProps } from "@pangloss/interface-core";
import { Match, Show, Switch } from "solid-js";
import { formatDate } from "../format";
import { ExactParts } from "./ExactParts";
import { RecurrenceParts } from "./RecurrenceEditor";

// (what EDTF is written with, up to level 2: digits, the separators, the marks of doubt (~ ? %),
// unspecified digits (X), times, years with Y, exponent and significant digits (E S), and sets ([ ] { } , ..)
const EDTF_CHARACTERS = /[0-9\-/~?%XxTZ:+YES[\]{},.]/;
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
// (what a date sorts by when it does not say, unless its field has a `SortDefault`)
const SORT_DEFAULT = "midpoint";

/**
 * The editor of a date (the card `Date` names for `edit_card`, which the other dates have from it):
 * only what a person says of a date, never the bounds and sort days the server works out. An exact
 * date is its year, month and day on one line; a range, its earliest and latest; an EDTF date, the
 * text. A recurrence is said as a person would (`RecurrenceParts`: every year on 21 March, from... until...). A
 * period is its fields, with its start and end each a date again (and so this editor again). Then the
 * calendar, what to sort by and what the source said, and the date as it reads. What it sorts by
 * when it does not say (the midpoint, or the field's `SortDefault`) is shown as chosen. The start and
 * end of a period have no Sort by: the period's says how it sorts.
 */
export default function DateEditor(props: EditCardProps) {
  const form = useItemForm();
  const { t, language, memberName } = useTranslations();
  // (an exact date with its year, month and day)
  const wholeDay = () =>
    props.type === "ExactDate" && ["year", "month", "day"].every((key) => typeof props.value[key] === "number");
  // (the start or the end of a period, which sorts by its own Sort by, not theirs)
  const endOfPeriod = () => {
    const at = props.path.at(-1);
    if (at !== "start" && at !== "end") return false;
    const parent = form.get(props.path.slice(0, -1)) as Record<string, unknown> | undefined;
    return parent?.type === "Period";
  };
  const sortDefault = () =>
    props.field?.markers?.find((marker) => marker.name === "SortDefault")?.sortBy ?? SORT_DEFAULT;
  const reads = () => {
    const text = formatDate(props.value, { language: language(), t, memberName });
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
        <Match when={props.type === "Recurrence"}>
          <RecurrenceParts path={props.path} label={props.label} />
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
              onBeforeInput={allowOnly(EDTF_CHARACTERS)}
              onInput={(event) => {
                // (an unspecified digit is a capital X in EDTF: a small one is made one, where it is)
                const box = event.currentTarget;
                if (box.value.includes("x")) {
                  const at = box.selectionStart;
                  box.value = box.value.replaceAll("x", "X");
                  box.setSelectionRange(at, at);
                }
                form.set([...props.path, "edtf"], box.value);
              }}
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
        skip={[
          ...props.model.fields.map((field) => field.key).filter((key) => !COMMON.includes(key)),
          // (a whole day sorts the same whichever bound it sorts by: nothing to choose)
          ...(wholeDay() || endOfPeriod() ? ["sortBy"] : []),
        ]}
        defaults={{ sortBy: sortDefault() }}
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
