import { createEffect, For, Show, untrack } from "solid-js";
import { ApiError } from "../../api";
import { useItemForm, useModels, useToasts, useTranslations } from "../../context";
import type { ItemFormState } from "../../context";
import { useErrorText } from "../../primitives";
import { ItemSchemas, serverProblems, setValidationMessages, validateItem } from "../../schema";
import type { FieldProblem, Path, SayProblem } from "../../schema";

/**
 * What a problem says, by its code, in the language of the page (a UI string, `invalid_<code>`):
 * what valibot is given as its messages for the language (`setValidationMessages`)
 */
export function useSayProblem(): SayProblem {
  const { t } = useTranslations();
  return (code, params) => {
    switch (code) {
      case "required":
        return t("invalid_required", "Required");
      case "too_short":
        return t("invalid_too_short", "At least {n} characters", params);
      case "too_long":
        return t("invalid_too_long", "At most {n} characters", params);
      case "too_few":
        return t("invalid_too_few", "At least {n} needed", params);
      case "too_many":
        return t("invalid_too_many", "At most {n} allowed", params);
      case "too_small":
        return t("invalid_too_small", "Must be {n} or more", params);
      case "must_exceed":
        return t("invalid_must_exceed", "Must be more than {n}", params);
      case "too_large":
        return t("invalid_too_large", "Must be {n} or less", params);
      case "must_be_under":
        return t("invalid_must_be_under", "Must be less than {n}", params);
      case "not_whole":
        return t("invalid_not_whole", "Must be a whole number");
      case "not_multiple":
        return t("invalid_not_multiple", "Must be a multiple of {n}", params);
      case "not_number":
        return t("invalid_not_number", "Must be a number");
      case "not_date":
        return t("invalid_not_date", "Must be a date");
      case "not_datetime":
        return t("invalid_not_datetime", "Must be a date and time");
      case "not_uuid":
        return t("invalid_not_uuid", "Must be a UUID");
      case "not_choice":
        return t("invalid_not_choice", "Not one of the choices");
      case "type_not_allowed":
        return t("invalid_type_not_allowed", "This type is not allowed here");
      case "server":
        // (the API's own words: it is English)
        return String(params.message ?? "");
      case "wrong_type":
      case "invalid":
        return t("invalid_value", "Not a valid value");
    }
  };
}

/**
 * What a problem says to a person: its message, after the keys between the row it is shown at and
 * where it is (`under`: a date's year, the second of a list)
 */
export function useProblemText() {
  const { fieldName } = useTranslations();
  return (problem: FieldProblem, under: Path = []): string => {
    const where = problem.path
      .slice(under.length)
      .map((key) => (typeof key === "number" ? `#${key + 1}` : fieldName("", key)));
    return where.length > 0 ? `${where.join(" › ")}: ${problem.message}` : problem.message;
  };
}

/**
 * Makes the row of the field at `path` one that problems are shown at, for as long as it is on the
 * page (and at its path as that changes, an item of a list moving up), and gives what is wrong there.
 */
export function useRowProblems(path: () => Path | undefined): () => FieldProblem[] {
  const form = useItemForm();
  createEffect(
    () => {
      const at = path();
      return at === undefined ? undefined : JSON.stringify(at);
    },
    (key) => (key === undefined ? undefined : form.registerRow(JSON.parse(key) as Path)),
  );
  return () => {
    const at = path();
    return at === undefined ? [] : form.problemsAt(at);
  };
}

/** What is wrong at a row, in red under its name */
export function FieldProblems(props: { problems: FieldProblem[]; path: Path }) {
  const text = useProblemText();
  return (
    <Show when={props.problems.length > 0}>
      <ul class="mt-0.5 flex flex-col text-xs font-normal text-red-700 normal-case">
        <For each={props.problems}>{(problem) => <li>{text(problem, props.path)}</li>}</For>
      </ul>
    </Show>
  );
}

/**
 * The checks of a form around its save. `check()` before sending: what is wrong in the form (by the
 * models' schemas), shown at its fields, with a red toast; false if there is anything, and then
 * nothing is to be sent. `refused(error)` when the API says no: a 422 shown at the fields in the
 * same way, anything else in the toast. `root` is what the form is in: the first field with a
 * problem is scrolled into view. The check is in the language of the page (valibot is given its
 * texts, and the language); if the language changes while what it found is shown, it is said again in the new one.
 */
export function useSaveChecks(state: ItemFormState, root: () => HTMLElement | undefined) {
  const definitions = useModels();
  const toasts = useToasts();
  const { t, language } = useTranslations();
  const text = useProblemText();
  const say = useSayProblem();
  const errorText = useErrorText();
  const schemas = new ItemSchemas(definitions);
  // (what the check found is shown, not what the API said: that can be checked again in another language)
  let checked = false;

  const validate = () => {
    const lang = language();
    setValidationMessages(lang, say);
    return validateItem(definitions, state.plain(), { lang, schemas });
  };

  createEffect(
    () => language(),
    () =>
      untrack(() => {
        if (!checked || state.problems().length === 0) return;
        // (only what is still shown: a field changed since is not marked again)
        const shown = new Set(state.problems().map(({ problem }) => JSON.stringify(problem.path)));
        state.setProblems(validate().filter((problem) => shown.has(JSON.stringify(problem.path))));
      }),
  );

  const show = (problems: FieldProblem[]) => {
    // (what has no field to be shown at is said in the toast)
    const unplaced = state
      .setProblems(problems)
      .filter(({ row }) => row === undefined)
      .map(({ problem }) => text(problem));
    const placed = problems.length - unplaced.length;
    const parts = [
      ...(placed > 0
        ? [
            placed === 1
              ? t("not_saved_problem", "Not saved: a field has a problem, marked in red")
              : t("not_saved_problems", "Not saved: {count} problems, marked in red", { count: placed }),
          ]
        : [t("not_saved", "Not saved")]),
      ...unplaced,
    ];
    toasts?.show(parts.join(" · "), "error");
    // (once the rows are red)
    setTimeout(() => {
      const first = root()?.querySelector("[data-problem]");
      first?.scrollIntoView({ block: "center", behavior: "smooth" });
    });
  };

  return {
    check(): boolean {
      const problems = validate();
      checked = true;
      if (problems.length === 0) {
        state.setProblems([]);
        return true;
      }
      show(problems);
      return false;
    },
    refused(error: unknown): void {
      if (error instanceof ApiError && error.status === 422) {
        checked = false;
        show(serverProblems(definitions, error.detail));
        return;
      }
      toasts?.show(errorText(error), "error");
    },
  };
}
