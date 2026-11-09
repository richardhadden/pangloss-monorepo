/**
 * The models as valibot schemas, to check an item in the browser before it is sent: made from the
 * exported definitions (`ModelDefinitions`), as the form holds an item (see docs/form-validation.md).
 * What is wrong is a list of `FieldProblem`s, each at the path of the form it is about, with valibot's
 * message in the language asked for (`setValidationMessages` gives valibot the texts of a language).
 */
import * as v from "valibot";
import type { FieldDefinition, FieldType, ModelDefinition, ModelDefinitions, RelationOption, Validator } from "../types";
import type { FormData, Path } from "./formValue";
import { getModel } from "./lookup";
import type { FieldProblem, ProblemCode } from "./problems";
import { sharesOf } from "./sharing";
import type { Shares } from "./sharing";
import { envOf, optionFor, resolveOptions } from "./typeChoices";
import type { Env } from "./typeChoices";

type Schema = v.GenericSchema;

// (the types of what is wrong are in `problems.ts`, which the bindings use too)
export type { FieldProblem, ProblemCode } from "./problems";

/** The text of a problem in a language: what the interface's translations say for its code */
export type SayProblem = (code: ProblemCode, params: Record<string, string | number>) => string;

/**
 * Gives valibot the messages of `lang` (its i18n: `setGlobalMessage`), so that a check with
 * `{ lang }` says what is wrong in that language. Every issue is said by its code, so one message
 * function serves them all. Set again, it replaces what was set for the language.
 */
export function setValidationMessages(lang: string, say: SayProblem): void {
  v.setGlobalMessage((issue) => {
    const { code, params } = problemOf(issue);
    return say(code, params);
  }, lang);
}

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * Whether a value is nothing, as `cleanForSave` sees it (it is not sent): nothing, null, an empty
 * text, an empty object, an entity not chosen (its type and no id).
 */
export function isBlank(definitions: ModelDefinitions, value: unknown): boolean {
  if (value === undefined || value === null || value === "") return true;
  if (!isObject(value)) return false;
  if (Object.keys(value).length === 0) return true;
  const model = typeof value.type === "string" ? getModel(definitions, value.type) : undefined;
  return model?.kind === "Entity" && (value.id === undefined || value.id === "");
}

const numberOf = (validator: Validator, key: string) =>
  typeof validator[key] === "number" ? (validator[key] as number) : undefined;

/** The checks of a field's validators (`annotated_types`, by name) that apply to a value of the kind `on` */
function checks(validators: Validator[], on: "text" | "number" | "list"): v.PipeItem<any, any, v.BaseIssue<unknown>>[] {
  const out: v.PipeItem<any, any, v.BaseIssue<unknown>>[] = [];
  for (const validator of validators) {
    const n = (key: string) => numberOf(validator, key);
    switch (validator.name) {
      case "MinLen":
        if (on !== "number" && n("min_length") !== undefined) out.push(v.minLength(n("min_length")!));
        break;
      case "MaxLen":
        if (on !== "number" && n("max_length") !== undefined) out.push(v.maxLength(n("max_length")!));
        break;
      case "Ge":
        if (on === "number" && n("ge") !== undefined) out.push(v.minValue(n("ge")!));
        break;
      case "Le":
        if (on === "number" && n("le") !== undefined) out.push(v.maxValue(n("le")!));
        break;
      case "Gt":
        if (on === "number" && n("gt") !== undefined) out.push(v.gtValue(n("gt")!));
        break;
      case "Lt":
        if (on === "number" && n("lt") !== undefined) out.push(v.ltValue(n("lt")!));
        break;
      case "MultipleOf":
        if (on === "number" && n("multiple_of") !== undefined) out.push(v.multipleOf(n("multiple_of")!));
        break;
      case "Unique":
        // (a set: no two items the same)
        if (on === "list") out.push(uniqueCheck);
        break;
      default:
        // (Pydantic's own: `pattern=` of a `Field`, `StringConstraints`)
        if (on === "text" && typeof validator.pattern === "string") {
          try {
            out.push(v.regex(new RegExp(validator.pattern, "u")));
          } catch {
            // (a Python pattern JavaScript cannot read: the API checks it)
          }
        }
    }
  }
  return out;
}

const piped = (schema: Schema, items: v.PipeItem<any, any, v.BaseIssue<unknown>>[]): Schema =>
  items.length === 0 ? schema : (v.pipe(schema, ...items) as Schema);

const DECIMAL = /^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$/;
const DATETIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
const TIME = /^\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/;
// (ISO 8601: P1DT2H30M, PT5S, P2W; or a number of seconds, which the API also takes)
const DURATION = /^(P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+(\.\d+)?S)?)?|[+-]?\d+(\.\d+)?)$/;

/** A text of the format (`uuid`, `url`, `email`): what the format says, else any text */
function textSchema(type: FieldType): Schema {
  const format = "format" in type ? type.format : undefined;
  switch (format) {
    case "uuid":
      return v.pipe(v.string(), v.uuid());
    case "url":
      return v.pipe(v.string(), v.url());
    case "email":
      return v.pipe(v.string(), v.email());
    default:
      return v.string();
  }
}

/**
 * The value of a field, kept apart from whether it is there (`present`). Empty items of a list are
 * left out when it is sent, so they are not checked, and not counted for its length.
 */
function valueSchema(definitions: ModelDefinitions, type: FieldType, validators: Validator[] = []): Schema {
  switch (type.type) {
    case "str":
      return piped(textSchema(type), checks(validators, "text"));
    case "int":
      return piped(v.pipe(v.number(), v.integer()), checks(validators, "number"));
    case "float":
      return piped(v.number(), checks(validators, "number"));
    case "decimal":
      // (the form keeps a decimal as it was typed: a text)
      return piped(
        v.pipe(
          v.union([v.number(), v.pipe(v.string(), v.regex(DECIMAL))]),
          v.transform((value) => Number(value)),
        ),
        checks(validators, "number"),
      );
    case "bool":
      return v.boolean();
    case "date":
      return v.pipe(v.string(), v.isoDate());
    case "datetime":
      return v.pipe(v.string(), v.regex(DATETIME));
    case "time":
      return v.pipe(v.string(), v.regex(TIME));
    case "duration":
      return v.pipe(v.string(), v.regex(DURATION));
    case "enum": {
      const members = definitions.enums[type.enum]?.members ?? [];
      return members.length === 0 ? v.unknown() : choice(members.map((member) => member.value));
    }
    case "literal":
      return choice(type.values);
    case "typedDict":
      return v.looseObject(
        Object.fromEntries(
          Object.entries(type.fields).map(([key, inner]) => [key, present(definitions, valueSchema(definitions, inner), true)]),
        ),
      );
    case "list":
      return listOf(definitions, valueSchema(definitions, type.item), validators);
    default:
      return v.unknown();
  }
}

// (a choice made with a pill is its text: an enum of numbers is still right as text)
const choice = (values: (string | number | boolean | null)[]): Schema =>
  v.picklist([...new Set(values.flatMap((value) => [value, String(value)]))] as string[]);

/** A list whose empty items are not checked, and whose length (`MinLen`, `MaxLen`) is of the rest */
function listOf(definitions: ModelDefinitions, item: Schema, validators: Validator[], shares?: Shares): Schema {
  return piped(
    v.pipe(
      v.array(present(definitions, item, false)),
      v.transform((items: unknown[]) => items.filter((inner) => !isBlank(definitions, inner))),
    ),
    [...checks(validators, "list"), ...(shares ? [sharesCheck(shares)] : [])],
  );
}

// (what each shares check is of: for its problem's text)
const SHARES = new WeakMap<object, Shares>();

const uniqueCheck = v.check(
  (items: unknown[]) => new Set(items.map((item) => JSON.stringify(item))).size === items.length,
);

const shareSum = (items: unknown[], key: string) =>
  items.reduce<number>((sum, inner) => {
    const edge = isObject(inner) && isObject(inner.edgeProperties) ? Number(inner.edgeProperties[key]) : NaN;
    return sum + (Number.isFinite(edge) ? edge : 0);
  }, 0);

/** The shares of the items add up to their total (`SumsTo`), as the server checks (an empty list has none) */
function sharesCheck(shares: Shares): v.PipeItem<any, any, v.BaseIssue<unknown>> {
  const requirement = (items: unknown[]) => items.length === 0 || shareSum(items, shares.key) === shares.total;
  SHARES.set(requirement, shares);
  return v.check(requirement);
}

// (the only custom check: a value that is not there)
const REQUIRED = v.custom(() => false);

/** `schema` for a value that is there; nothing if it is empty and may be, "required" if it may not */
function present(definitions: ModelDefinitions, schema: Schema, required: boolean): Schema {
  return v.lazy((input) => (isBlank(definitions, input) ? (required ? REQUIRED : v.unknown()) : schema));
}

/** The schemas of the models, made when first needed and kept, per model and binding of its type variables */
export class ItemSchemas {
  private made = new Map<string, Schema>();

  constructor(private definitions: ModelDefinitions) {}

  /** An item of `type` (a Document or an Entity edited on its own page, or in its own form) */
  item(type: string): Schema {
    return this.model(type, {});
  }

  /** The fields of the model `name`, with its type variables bound as in `env` */
  model(name: string, env: Env): Schema {
    const key = `${name} ${JSON.stringify(env)}`;
    let schema = this.made.get(key);
    if (!schema) {
      // (lazily: a model can hold itself, a statement in a statement)
      schema = v.lazy(() => this.build(name, env));
      this.made.set(key, schema);
    }
    return schema;
  }

  private build(name: string, env: Env): Schema {
    const model = getModel(this.definitions, name);
    if (!model) return v.unknown();
    const entries: Record<string, Schema> = {};
    if (labelled(model)) entries.label = this.entry(v.string(), true);
    // (a field the server works out, `DBField`, such as the bounds of a date, is never written by a client: not checked)
    for (const field of model.fields) if (!field.dbField) entries[field.key] = this.field(field, env);
    return v.looseObject(entries);
  }

  /** A field: absent is "required" if it may not be (a missing key is told by the object, an empty value here) */
  private entry(schema: Schema, required: boolean): Schema {
    const inner = present(this.definitions, schema, required);
    return required ? inner : v.optional(inner);
  }

  private field(field: FieldDefinition, env: Env): Schema {
    const required = field.required && !field.nullable;
    switch (field.kind) {
      case "literal":
        return this.entry(valueSchema(this.definitions, field.type, field.validators), required);
      case "list":
        return this.entry(
          listOf(this.definitions, valueSchema(this.definitions, field.item, field.itemValidators), field.validators),
          required,
        );
      case "annotatedValue":
        return this.entry(
          field.many
            ? listOf(this.definitions, this.annotated(field.model, field.valueType), [])
            : this.annotated(field.model, field.valueType),
          required,
        );
      case "embedded":
        return this.entry(this.oneOf(field.types.map((type) => [type, () => this.model(type, {})])), required);
      case "relation": {
        const item = this.relationItem(resolveOptions(field.options, env), env);
        return this.entry(
          field.many ? listOf(this.definitions, item, field.validators, sharesOf(this.definitions, field)) : item,
          required,
        );
      }
      default:
        // (a type variable of a literal, something the export does not know: the API checks it)
        return v.optional(v.unknown());
    }
  }

  /** An annotated value: its model's fields, with `value` of the field's own type */
  private annotated(name: string, valueType: FieldType | null): Schema {
    const model = getModel(this.definitions, name);
    const entries: Record<string, Schema> = {};
    for (const field of model?.fields ?? []) {
      if (field.key !== "value") entries[field.key] = this.field(field, {});
    }
    entries.value = present(this.definitions, valueType ? valueSchema(this.definitions, valueType) : v.unknown(), true);
    return v.looseObject(entries);
  }

  /**
   * An object that is one of some types, by its `type`: the schema of that one, or "not allowed
   * here" (unless `open`: there are options the export cannot say, so the API decides)
   */
  private oneOf(types: [string, () => Schema][], open = false): Schema {
    const byType = new Map(types);
    return v.lazy((input) => {
      const type = isObject(input) && typeof input.type === "string" ? input.type : undefined;
      const schema = type === undefined ? undefined : byType.get(type);
      if (schema) return schema();
      // (`never`: nothing is allowed there, as the type it is)
      return open ? v.unknown() : v.never();
    });
  }

  /** One thing in a relation, by what the option for its type is */
  private relationItem(options: RelationOption[], env: Env): Schema {
    const types = options.flatMap((option) =>
      "type" in option && option.kind !== "unknown" ? [option.type] : [],
    );
    return this.oneOf(
      types.map((type): [string, () => Schema] => [
        type,
        () => {
          const option = optionFor(options, type)!;
          const edgeModel = "edgeModel" in option ? option.edgeModel : null;
          const edge: Record<string, Schema> = edgeModel ? { edgeProperties: this.edge(edgeModel) } : {};
          if (option.kind === "entity") {
            // (a reference: the entity is chosen, and what the relation says of it)
            return v.looseObject({ id: v.union([v.string(), v.number()]), ...edge }) as Schema;
          }
          const own = this.model(type, envOf(option, env));
          return edgeModel ? (v.intersect([own, v.looseObject(edge)]) as Schema) : own;
        },
      ]),
      // (a type variable that is not bound, an option of a kind the export does not know)
      types.length < options.length,
    );
  }

  // (the properties of a relation: an object, even before any is filled in, so that a required one is told)
  private edge(name: string): Schema {
    return v.optional(this.model(name, {}), {});
  }
}

/** The kinds whose `Create` has a label, if the model says it is required */
const labelled = (model: ModelDefinition) =>
  model.requireLabel && ["Document", "Entity", "ReifiedRelationDocument"].includes(model.kind);

/**
 * What is wrong in `item` (as the form holds it) as an item of its type; nothing if it can be sent.
 * The messages are in `lang`, if `setValidationMessages` has given valibot its texts (else valibot's English).
 */
export function validateItem(
  definitions: ModelDefinitions,
  item: FormData,
  options: { lang?: string; schemas?: ItemSchemas } = {},
): FieldProblem[] {
  const type = typeof item.type === "string" ? item.type : undefined;
  if (!type || !getModel(definitions, type)) return [];
  const schemas = options.schemas ?? new ItemSchemas(definitions);
  const result = v.safeParse(schemas.item(type), item, { abortPipeEarly: true, lang: options.lang });
  return result.success ? [] : result.issues.map((issue) => ({ ...problemOf(issue), message: issue.message }));
}

const pathOf = (issue: v.BaseIssue<unknown>): Path =>
  (issue.path ?? []).map((item) => item.key as string | number);

const count = (requirement: unknown) => (typeof requirement === "number" ? requirement : Number(requirement));

/** A valibot issue as a problem of the form (its message aside) */
export function problemOf(issue: v.BaseIssue<unknown>): Omit<FieldProblem, "message"> {
  const path = pathOf(issue);
  const n = { n: count(issue.requirement) };
  const list = Array.isArray(issue.input);
  switch (issue.type) {
    case "custom":
      return { path, code: "required", params: {} };
    case "check": {
      const shares = SHARES.get(issue.requirement as object);
      if (shares && Array.isArray(issue.input)) {
        return { path, code: "shares_total", params: { n: shares.total, sum: shareSum(issue.input, shares.key) } };
      }
      if (issue.requirement === uniqueCheck.requirement) return { path, code: "not_unique", params: {} };
      return { path, code: "invalid", params: {} };
    }
    case "never":
      return { path, code: "type_not_allowed", params: {} };
    case "regex":
      // (a decimal, a date and time, are checked by a pattern: by what the value is; a pattern of the model's, "invalid")
      return {
        path,
        code:
          issue.requirement === DECIMAL
            ? "not_number"
            : issue.requirement === DATETIME
              ? "not_datetime"
              : issue.requirement === TIME
                ? "not_time"
                : issue.requirement === DURATION
                  ? "not_duration"
                  : "invalid",
        params: {},
      };
    case "min_length":
      return { path, code: list ? "too_few" : "too_short", params: n };
    case "max_length":
      return { path, code: list ? "too_many" : "too_long", params: n };
    case "min_value":
      return { path, code: "too_small", params: n };
    case "gt_value":
      return { path, code: "must_exceed", params: n };
    case "max_value":
      return { path, code: "too_large", params: n };
    case "lt_value":
      return { path, code: "must_be_under", params: n };
    case "integer":
      return { path, code: "not_whole", params: {} };
    case "multiple_of":
      return { path, code: "not_multiple", params: n };
    case "iso_date":
      return { path, code: "not_date", params: {} };
    case "uuid":
      return { path, code: "not_uuid", params: {} };
    case "url":
      return { path, code: "not_url", params: {} };
    case "email":
      return { path, code: "not_email", params: {} };
    case "picklist":
      return { path, code: "not_choice", params: {} };
    case "union":
      return { path, code: "not_number", params: {} };
  }
  // (a key the object does not have is a field left out)
  if (issue.kind === "schema" && issue.received === "undefined") return { path, code: "required", params: {} };
  return { path, code: "wrong_type", params: { expected: issue.expected ?? "" } };
}

/**
 * The problems of a 422 of the API, at the paths of the form: its `loc` without `body`, nor the
 * names of models and the tags Pydantic puts in it for a union (`function-after[...]`).
 * What is not such a list is one problem with no path.
 */
export function serverProblems(definitions: ModelDefinitions, detail: string): FieldProblem[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(detail);
  } catch {
    parsed = undefined;
  }
  if (!Array.isArray(parsed)) return [{ path: [], code: "server", params: { message: detail }, message: detail }];
  return parsed.map((problem: { loc?: unknown[]; msg?: unknown }) => ({
    path: (problem.loc ?? []).filter(
      (part): part is string | number =>
        typeof part === "number" ||
        (typeof part === "string" && part !== "body" && !definitions.models[part] && /^[A-Za-z_][\w]*$/.test(part)),
    ),
    code: "server" as const,
    params: { message: typeof problem.msg === "string" ? problem.msg : JSON.stringify(problem) },
    message: typeof problem.msg === "string" ? problem.msg : JSON.stringify(problem),
  }));
}
