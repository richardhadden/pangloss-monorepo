/**
 * What is wrong in an item, or to be said about it, at a path of the form: the types alone, so that what finds them
 * (the checks of `validation.ts`, the notices of the bindings) need not import each other.
 */
import type { Path } from "./formValue";

/** What is wrong (each a UI string, `invalid_<code>`) */
export type ProblemCode =
  | "required"
  | "too_short"
  | "too_long"
  | "too_few"
  | "too_many"
  | "too_small"
  | "must_exceed"
  | "too_large"
  | "must_be_under"
  | "not_whole"
  | "not_multiple"
  | "not_number"
  | "not_date"
  | "not_datetime"
  | "not_uuid"
  | "not_url"
  | "not_email"
  | "not_time"
  | "not_duration"
  | "not_unique"
  | "not_choice"
  | "shares_total"
  | "wrong_type"
  | "type_not_allowed"
  | "bound_not_held"
  | "invalid"
  | "server";

/**
 * Something wrong in an item, at `path` of the form; `params` are what its text needs (`{n}`, the
 * API's `{message}`), and `message` is the text, in the language of the check (the API's own words for a 422)
 */
export interface FieldProblem {
  path: Path;
  code: ProblemCode;
  params: Record<string, string | number>;
  message: string;
}
