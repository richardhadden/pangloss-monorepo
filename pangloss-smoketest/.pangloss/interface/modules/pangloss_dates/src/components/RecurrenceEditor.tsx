import { inputClass, NumberInput, useItemForm, useTranslations } from "@pangloss/interface-core";
import { createMemo, For, onSettled, Show, untrack } from "solid-js";
import { monthNames, weekdayNames } from "../format";
import { ExactParts } from "./ExactParts";

type Data = Record<string, unknown>;
type Path = (string | number)[];
type Frequency = "yearly" | "monthly" | "weekly";
/** How a yearly or monthly rule names its day */
type Way = "day" | "weekday" | "easter";

const FREQUENCIES: Frequency[] = ["yearly", "monthly", "weekly"];
/** The weekdays as a week is read, Monday first (the rule numbers Sunday 0) */
const WEEK = [1, 2, 3, 4, 5, 6, 0];
const NTHS = [1, 2, 3, 4, 5, -1];

const isData = (value: unknown): value is Data => typeof value === "object" && value !== null && !Array.isArray(value);
const num = (value: unknown) => (typeof value === "number" ? value : undefined);

/** The words for "the first", ... "the last" (of the month) */
export function nthWords(t: (key: string, english: string) => string): Record<number, string> {
  return {
    1: t("date_nth_first", "first"),
    2: t("date_nth_second", "second"),
    3: t("date_nth_third", "third"),
    4: t("date_nth_fourth", "fourth"),
    5: t("date_nth_fifth", "fifth"),
    [-1]: t("date_nth_last", "last"),
  };
}

/** Pills to choose one of a few: the chosen one filled */
function Pills<T extends string>(props: {
  label: string;
  options: { value: T; text: string }[];
  value: T | undefined;
  onChange: (value: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={props.label} class="flex flex-wrap gap-1.5">
      <For each={props.options}>
        {(option) => (
          <button
            type="button"
            role="radio"
            aria-checked={props.value === option.value ? "true" : "false"}
            onClick={() => props.onChange(option.value)}
            class={[
              "cursor-pointer rounded-full border-[0.5px] border-slate-400/70 px-3 py-1 text-sm select-none",
              {
                "bg-slate-700": props.value === option.value,
                "text-white": props.value === option.value,
                "bg-white/80": props.value !== option.value,
                "hover:bg-slate-200": props.value !== option.value,
              },
            ]}
          >
            {option.text}
          </button>
        )}
      </For>
    </div>
  );
}

function Row(props: { name: string; children: unknown }) {
  return (
    <>
      <span class="pt-1.5 text-xs font-semibold text-slate-500 uppercase">{props.name}</span>
      <div class="flex min-w-0 flex-col gap-2">{props.children as never}</div>
    </>
  );
}

/**
 * A repeated event (a `Recurrence`) as a person says it, in the form at `path`: what it repeats by (every year, month
 * or week), on what (a day of a month; the third Sunday of March; a day from Easter; the weekdays), how often (every
 * second year), and from when until when. The rule's fields (`frequency`, `month`, `monthDay`, `nth`, `weekdays`,
 * `easterOffset`, `interval`, `leapShift`) are written from these; the lists the rule needs (`weekdays`,
 * `excludedDays`) are always there, so an empty rule is complete. Days to leave out (`excludedDays`, day numbers)
 * and a rule on a feast (`feast`, the id of a characterisation) are not offered here.
 */
export function RecurrenceParts(props: { path: Path; label: string }) {
  const form = useItemForm();
  const { t, language } = useTranslations();
  const value = (): Data => {
    const at = form.get(props.path);
    return isData(at) ? at : {};
  };
  const at = (key: string) => [...props.path, key];
  const set = (key: string, next: unknown) => form.set(at(key), next);
  const clear = (...keys: string[]) => {
    for (const key of keys) if (value()[key] !== undefined) form.remove(at(key));
  };
  // (the lists the rule needs are there from the start, so that nothing is "required" before anything is said)
  onSettled(() => {
    untrack(() => {
      if (!Array.isArray(value().weekdays)) set("weekdays", []);
      if (!Array.isArray(value().excludedDays)) set("excludedDays", []);
    });
  });
  const frequency = () => value().frequency as Frequency | undefined;
  const weekdays = () => (Array.isArray(value().weekdays) ? (value().weekdays as number[]) : []);
  const way = (): Way =>
    num(value().easterOffset) !== undefined ? "easter" : num(value().nth) !== undefined ? "weekday" : "day";
  const months = createMemo(() => monthNames(language()));
  const days = createMemo(() => weekdayNames(language()));
  const nths = createMemo(() => nthWords(t));
  const part = (key: string) => {
    const found = num(value()[key]);
    return found === undefined ? "" : String(found);
  };
  const writeNumber = (key: string, typed: string) => {
    if (typed === "") clear(key);
    else set(key, Number(typed));
  };
  const chooseFrequency = (next: Frequency) => {
    set("frequency", next);
    if (next === "weekly") clear("month", "monthDay", "nth", "easterOffset", "leapShift");
    if (next === "monthly") clear("month", "easterOffset", "leapShift");
    if (next !== "weekly" && way() === "day") set("weekdays", []);
  };
  const chooseWay = (next: Way) => {
    if (next === way()) return;
    if (next === "day") clear("nth", "easterOffset");
    if (next === "weekday") {
      clear("monthDay", "easterOffset", "leapShift");
      set("nth", 1);
    }
    if (next === "easter") {
      clear("month", "monthDay", "nth", "leapShift");
      set("easterOffset", 0);
    }
    if (next !== "weekday") set("weekdays", []);
  };
  const toggleWeekday = (day: number) => {
    const now = weekdays();
    set(
      "weekdays",
      now.includes(day) ? now.filter((d) => d !== day) : [...now, day].sort((a, b) => a - b),
    );
  };
  const theWeekday = () => (weekdays().length > 0 ? String(weekdays()[0]) : "");
  const leapDay = () => frequency() === "yearly" && num(value().month) === 2 && (num(value().monthDay) ?? 0) >= 24;
  const unit = () =>
    frequency() === "weekly"
      ? t("date_unit_weeks", "weeks")
      : frequency() === "monthly"
        ? t("date_unit_months", "months")
        : t("date_unit_years", "years");
  const monthSelect = (
    <select
      class={[inputClass, "w-40"]}
      aria-label={`${props.label} ${t("date_month", "Month")}`}
      value={part("month")}
      onChange={(event) => writeNumber("month", event.currentTarget.value)}
    >
      <option value="" textContent={t("date_no_month", "(no month)")} />
      <For each={months()}>
        {(name, index) => (
          <option value={String(index() + 1)} selected={part("month") === String(index() + 1)}>
            {name}
          </option>
        )}
      </For>
    </select>
  );
  const weekdaySelect = (
    <select
      class={[inputClass, "w-40"]}
      aria-label={`${props.label} ${t("date_weekday", "Weekday")}`}
      value={theWeekday()}
      onChange={(event) => set("weekdays", event.currentTarget.value === "" ? [] : [Number(event.currentTarget.value)])}
    >
      <option value="" textContent={t("date_no_weekday", "(weekday)")} />
      <For each={WEEK}>
        {(day) => (
          <option value={String(day)} selected={theWeekday() === String(day)}>
            {days()[day]}
          </option>
        )}
      </For>
    </select>
  );
  const nthSelect = (
    <select
      class={[inputClass, "w-32"]}
      aria-label={`${props.label} ${t("date_nth", "Which")}`}
      value={part("nth")}
      onChange={(event) => writeNumber("nth", event.currentTarget.value)}
    >
      <For each={NTHS}>
        {(n) => (
          <option value={String(n)} selected={part("nth") === String(n)}>
            {nths()[n]}
          </option>
        )}
      </For>
    </select>
  );
  const dayBox = (
    <div class="w-24 shrink-0">
      <NumberInput
        label={`${props.label} ${t("date_day", "Day")}`}
        placeholder={t("date_day", "Day")}
        min={1}
        max={31}
        allowed={/[0-9]/}
        value={part("monthDay")}
        onInput={(typed) => writeNumber("monthDay", typed)}
      />
    </div>
  );
  return (
    <div class="grid grid-cols-[8rem_minmax(0,1fr)] items-start gap-x-6 gap-y-4" data-testid="recurrence-editor">
      <Row name={t("date_repeats", "Repeats")}>
        <Pills
          label={`${props.label} ${t("date_repeats", "Repeats")}`}
          options={[
            { value: "yearly", text: t("date_every_year", "Every year") },
            { value: "monthly", text: t("date_every_month", "Every month") },
            { value: "weekly", text: t("date_every_week", "Every week") },
          ]}
          value={frequency()}
          onChange={chooseFrequency}
        />
      </Row>
      <Show when={frequency() === "yearly"}>
        <Row name={t("date_on", "On")}>
          <Pills
            label={`${props.label} ${t("date_on", "On")}`}
            options={[
              { value: "day", text: t("date_way_day", "A day of a month") },
              { value: "weekday", text: t("date_way_weekday", "A weekday of a month") },
              { value: "easter", text: t("date_way_easter", "A day from Easter") },
            ]}
            value={way()}
            onChange={chooseWay}
          />
          <Show when={way() === "day"}>
            <div class="flex flex-wrap items-center gap-2">
              {dayBox}
              {monthSelect}
            </div>
            <Show when={leapDay()}>
              <label class="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={value().leapShift === true}
                  onChange={(event) => (event.currentTarget.checked ? set("leapShift", true) : clear("leapShift"))}
                />
                {t("date_leap_shift", "A day later in a leap year (the old Roman leap day repeated 24 February)")}
              </label>
            </Show>
          </Show>
          <Show when={way() === "weekday"}>
            <div class="flex flex-wrap items-center gap-2">
              {nthSelect}
              {weekdaySelect}
              <span class="text-sm text-slate-500">{t("date_of", "of")}</span>
              {monthSelect}
            </div>
          </Show>
          <Show when={way() === "easter"}>
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-sm">{t("date_easter", "Easter")}</span>
              <div class="w-28 shrink-0">
                <NumberInput
                  label={`${props.label} ${t("date_easter_offset", "Days from Easter")}`}
                  min={-80}
                  max={250}
                  value={part("easterOffset")}
                  onInput={(typed) => writeNumber("easterOffset", typed)}
                />
              </div>
              <span class="text-sm text-slate-500">{t("date_days", "days")}</span>
            </div>
            <p class="text-xs text-slate-500">
              {t("date_easter_help", "0 is Easter Day, 49 Pentecost, −47 Shrove Tuesday, −46 Ash Wednesday")}
            </p>
          </Show>
        </Row>
      </Show>
      <Show when={frequency() === "monthly"}>
        <Row name={t("date_on", "On")}>
          <Pills
            label={`${props.label} ${t("date_on", "On")}`}
            options={[
              { value: "day", text: t("date_way_day_of_month", "A day of the month") },
              { value: "weekday", text: t("date_way_weekday_of_month", "A weekday of the month") },
            ]}
            value={way()}
            onChange={chooseWay}
          />
          <Show when={way() === "day"}>
            <div class="flex items-center gap-2">
              {dayBox}
              <span class="text-sm text-slate-500">{t("date_of_the_month", "of the month")}</span>
            </div>
          </Show>
          <Show when={way() === "weekday"}>
            <div class="flex flex-wrap items-center gap-2">
              {nthSelect}
              {weekdaySelect}
              <span class="text-sm text-slate-500">{t("date_of_the_month", "of the month")}</span>
            </div>
          </Show>
        </Row>
      </Show>
      <Show when={frequency() === "weekly"}>
        <Row name={t("date_on", "On")}>
          <div class="flex flex-wrap gap-x-4 gap-y-1" role="group" aria-label={`${props.label} ${t("date_weekdays", "Weekdays")}`}>
            <For each={WEEK}>
              {(day) => (
                <label class="flex items-center gap-1.5 text-sm">
                  <input type="checkbox" checked={weekdays().includes(day)} onChange={() => toggleWeekday(day)} />
                  {days()[day]}
                </label>
              )}
            </For>
          </div>
        </Row>
      </Show>
      <Show when={frequency()}>
        <Row name={t("date_how_often", "How often")}>
          <div class="flex items-center gap-2">
            <span class="text-sm">{t("date_every", "every {what}", { what: "" }).trim()}</span>
            <div class="w-24 shrink-0">
              <NumberInput
                label={`${props.label} ${t("date_interval", "Every")}`}
                placeholder="1"
                min={1}
                allowed={/[0-9]/}
                value={part("interval")}
                onInput={(typed) => writeNumber("interval", typed)}
              />
            </div>
            <span class="text-sm">{unit()}</span>
          </div>
        </Row>
      </Show>
      <Row name={t("date_from", "From")}>
        <ExactParts path={[...props.path, "start"]} label={`${props.label} ${t("date_from", "From")}`} />
      </Row>
      <Row name={t("date_until", "Until")}>
        <ExactParts path={[...props.path, "end"]} label={`${props.label} ${t("date_until", "Until")}`} />
      </Row>
    </div>
  );
}
