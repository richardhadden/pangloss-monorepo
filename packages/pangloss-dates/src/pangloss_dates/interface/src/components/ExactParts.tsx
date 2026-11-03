import { integerCharacters, inputClass, NumberInput, useItemForm, useTranslations } from "@pangloss/interface-core";
import { For } from "solid-js";
import { monthNames } from "../format";

type Data = Record<string, unknown>;
type Path = (string | number)[];

const isData = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * An exact date at `path` of the form, on one line: the year, the month (by name) and the day, each
 * left out by leaving it empty. It is always an `ExactDate`, also where it is the end of a range that
 * has none yet.
 */
export function ExactParts(props: { path: Path; label: string }) {
  const form = useItemForm();
  const { t, language } = useTranslations();
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
      <div class="w-32 shrink-0">
        <NumberInput
          label={`${props.label} ${t("date_year", "Year")}`}
          placeholder={t("date_year", "Year")}
          allowed={integerCharacters}
          value={part("year")}
          onInput={(typed) => write("year", typed)}
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
          <For each={monthNames(language())}>
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
      <div class="w-24 shrink-0">
        <NumberInput
          label={`${props.label} ${t("date_day", "Day")}`}
          placeholder={t("date_day", "Day")}
          min={1}
          max={31}
          // (a day is never below nothing: no minus)
          allowed={/[0-9]/}
          value={part("day")}
          onInput={(typed) => write("day", typed)}
        />
      </div>
    </div>
  );
}
