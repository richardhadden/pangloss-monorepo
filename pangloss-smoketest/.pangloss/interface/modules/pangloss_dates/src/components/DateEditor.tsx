import { allowOnly, fieldRuleClass, inputClass, ModelFields, useItemForm, useTranslations } from "@pangloss/interface-core";
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
 * date is its year, month and day on one line; a range, its not-before and not-after (either may be
 * not known: `RangeEnd`); an EDTF date, the
 * text. A recurrence is said as a person would (`RecurrenceParts`: every year on 21 March, from... until...). A
 * period is its fields, with its start and end each a date again (and so this editor again). Under it,
 * the date as it reads; then the calendar, what the source said and what to sort by. What it sorts by
 * when it does not say (the midpoint, or the field's `SortDefault`) is shown as chosen. The start and
 * end of a period have no Sort by: the period's says how it sorts.
 */
/**
 * An end of a range (`notBefore`, `notAfter`, as the TEI names them): its name, then the date, and a
 * "Not known" button. Pressed, the end is an `UnknownDate` (nothing is known of it) and the date's
 * parts are gone; pressed again, it is a date to fill in. Both ends cannot be unknown: the button of
 * one is not offered while the other is pressed.
 */
function RangeEnd(props: {
  path: (string | number)[];
  end: string;
  other: string;
  name: string;
  label: string;
}) {
  const form = useItemForm();
  const { t } = useTranslations();
  const typeAt = (end: string) =>
    (form.get([...props.path, end]) as Record<string, unknown> | undefined)?.type;
  const unknown = () => typeAt(props.end) === "UnknownDate";
  return (
    <>
      <span class="text-xs font-semibold text-slate-500 uppercase">{props.name}</span>
      <div class="flex flex-wrap items-center gap-3">
        <Show when={!unknown()}>
          <ExactParts path={[...props.path, props.end]} label={`${props.label} ${props.name}`} />
        </Show>
        <button
          type="button"
          class={[
            "rounded-sm border px-2 py-1 text-xs",
            unknown()
              ? "border-slate-600 bg-slate-600 text-white"
              : "border-slate-300 text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent",
          ]}
          aria-pressed={unknown() ? "true" : "false"}
          aria-label={`${props.label} ${props.name} ${t("date_not_known", "Not known")}`}
          title={t("date_not_known_help", "Nothing is known of this end (press again to give a date)")}
          disabled={!unknown() && typeAt(props.other) === "UnknownDate"}
          onClick={() =>
            form.set([...props.path, props.end], { type: unknown() ? "ExactDate" : "UnknownDate" })
          }
        >
          {t("date_not_known", "Not known")}
        </button>
      </div>
    </>
  );
}

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
    // (not until it is all there: a range without its not-after does not read)
    return text && !text.includes("undefined") ? text : undefined;
  };
  return (
    <div class="flex min-w-0 flex-col gap-5">
      {/* (the date, then how it reads, under it: the rest are rows, each with a rule above it) */}
      <div class="flex min-w-0 flex-col gap-3">
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
              <RangeEnd
                path={props.path}
                end="notBefore"
                other="notAfter"
                name={t("date_not_before", "Not before")}
                label={props.label}
              />
              <RangeEnd
                path={props.path}
                end="notAfter"
                other="notBefore"
                name={t("date_not_after", "Not after")}
                label={props.label}
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
        <Show when={reads()}>
          <p class="text-sm text-slate-600" data-testid="date-reads">
            <span class="mr-2 text-xs font-semibold text-slate-500 uppercase select-none">
              {t("date_reads", "Reads")}
            </span>
            {reads()}
          </p>
        </Show>
      </div>
      <div class={["border-t pt-5", fieldRuleClass]}>
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
      </div>
    </div>
  );
}
