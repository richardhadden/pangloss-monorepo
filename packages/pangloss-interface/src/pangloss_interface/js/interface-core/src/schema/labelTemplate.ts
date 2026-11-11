/**
 * Labels worked out from what an item holds: `Meta(label_template=...)` (implementation_docs/label-templates.md). The same
 * language, and the same results, as `pangloss_models.label_templates` on the server, which works each automatic label
 * out again on a write and keeps its own: the cases of `pangloss-models/tests/label_cases.json` are run by both.
 *
 *     template    := (text | placeholder | group)*
 *     placeholder := "{" path ("|" filter)* "}"          path: field names, dotted (bequests.recipient)
 *     group       := "[" template "]"                    left out if any placeholder in it is empty
 *     filter      := name ("(" "text" ("," "text")* ")")?
 */
import type { ModelDefinition, ModelDefinitions } from "../types";
import type { FormHook } from "./binding";
import type { FormData } from "./formValue";

type Part =
  | { kind: "text"; text: string }
  | { kind: "placeholder"; path: string[]; filters: Filter[] }
  | { kind: "group"; parts: Part[] };
interface Filter {
  name: string;
  args: string[];
  template?: Part[];
}

/** A label made by a function of an interface module (`labelFormatters`), given the JSON of the object */
export type LabelFormatter = (value: Record<string, unknown>) => string | undefined;

const FILTERS: Record<string, [number, number]> = {
  join: [0, 2],
  first: [0, 0],
  last: [0, 0],
  count: [0, 0],
  default: [1, 1],
  each: [1, 1],
  lower: [0, 0],
  capitalise: [0, 0],
};

const NAME = /[A-Za-z_]\w*/y;

class Parser {
  at = 0;
  constructor(readonly source: string) {}

  fail(problem: string): Error {
    return new Error(`label_template ${JSON.stringify(this.source)}: ${problem} (at ${this.at})`);
  }

  template(until?: "]"): Part[] {
    const parts: Part[] = [];
    let text = "";
    const flush = () => {
      if (text) parts.push({ kind: "text", text });
      text = "";
    };
    while (this.at < this.source.length) {
      const char = this.source[this.at]!;
      if (char === "\\") {
        if (this.at + 1 >= this.source.length) throw this.fail("a \\ at the end");
        text += this.source[this.at + 1];
        this.at += 2;
      } else if (char === "{") {
        flush();
        this.at += 1;
        parts.push(this.placeholder());
      } else if (char === "[") {
        flush();
        this.at += 1;
        parts.push({ kind: "group", parts: this.template("]") });
      } else if (char === "]") {
        if (until !== "]") throw this.fail("a ] with no [ before it");
        flush();
        this.at += 1;
        return parts;
      } else if (char === "}") {
        throw this.fail("a } with no { before it");
      } else {
        text += char;
        this.at += 1;
      }
    }
    if (until) throw this.fail("a [ that is not closed");
    flush();
    return parts;
  }

  space() {
    while (this.source[this.at] === " ") this.at += 1;
  }

  name(what: string): string {
    this.space();
    NAME.lastIndex = this.at;
    const found = NAME.exec(this.source);
    if (!found) throw this.fail(`the name of ${what} expected`);
    this.at = NAME.lastIndex;
    this.space();
    return found[0];
  }

  placeholder(): Part {
    const path = [this.name("a field")];
    while (this.source[this.at] === ".") {
      this.at += 1;
      path.push(this.name("a field"));
    }
    const filters: Filter[] = [];
    while (this.source[this.at] === "|") {
      this.at += 1;
      filters.push(this.filter());
    }
    if (this.source[this.at] !== "}") throw this.fail("a } expected");
    this.at += 1;
    return { kind: "placeholder", path, filters };
  }

  filter(): Filter {
    const name = this.name("a filter");
    if (!Object.hasOwn(FILTERS, name)) throw this.fail(`there is no filter '${name}'`);
    const args: string[] = [];
    if (this.source[this.at] === "(") {
      this.at += 1;
      this.space();
      while (this.source[this.at] !== ")") {
        args.push(this.quoted());
        this.space();
        if (this.source[this.at] === ",") {
          this.at += 1;
          this.space();
        } else if (this.source[this.at] !== ")") throw this.fail("a , or a ) expected");
      }
      this.at += 1;
      this.space();
    }
    const [least, most] = FILTERS[name]!;
    if (args.length < least || args.length > most) throw this.fail(`'${name}' takes ${least}-${most} texts`);
    return name === "each" ? { name, args, template: new Parser(args[0]!).template() } : { name, args };
  }

  quoted(): string {
    if (this.source[this.at] !== '"') throw this.fail('a text in "" expected');
    this.at += 1;
    let text = "";
    while (this.at < this.source.length) {
      const char = this.source[this.at]!;
      if (char === "\\" && this.at + 1 < this.source.length) {
        const following = this.source[this.at + 1]!;
        text += following === '"' || following === "\\" ? following : char + following;
        this.at += 2;
      } else if (char === '"') {
        this.at += 1;
        return text;
      } else {
        text += char;
        this.at += 1;
      }
    }
    throw this.fail('a text in "" that is not closed');
  }
}

const parsedCache = new Map<string, Part[]>();

/** The parts of a template (read once for each text) */
export function parseTemplate(source: string): Part[] {
  let parsed = parsedCache.get(source);
  if (!parsed) {
    parsed = new Parser(source).template();
    parsedCache.set(source, parsed);
  }
  return parsed;
}

// Kinds without a label of their own whose text is what they hold
const WRAPPERS = ["ReifiedRelation", "Conjunction", "SemanticSpace"];
// The keys of a node that are not what it holds
const NOT_CONTENTS = new Set(["meta", "edgeProperties", "type", "id", "label", "labelAuto"]);
// The keys a walk through an item does not go into: what is said of it, not what it holds
const NOT_WALKED = new Set(["meta", "edgeProperties", "contextLabels", "semanticSpaces"]);

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** What the interpreter is given: the models, and the formatters of the modules by `app:name` */
export interface LabelContext {
  definitions: ModelDefinitions;
  formatter: (name: string) => LabelFormatter | undefined;
}

function modelOf(context: LabelContext, value: unknown): ModelDefinition | undefined {
  if (!isObject(value) || typeof value.type !== "string") return undefined;
  return Object.hasOwn(context.definitions.models, value.type) ? context.definitions.models[value.type] : undefined;
}

/** Its label is kept, and worked out by a template */
export function derivesLabel(model: ModelDefinition | undefined): boolean {
  return !!model && model.requireLabel && !!model.labelTemplate && "alternatives" in model.labelTemplate;
}

function contentKeys(model: ModelDefinition): string[] {
  return model.kind === "ReifiedRelation"
    ? ["target"]
    : model.fields.filter((field) => field.kind === "relation").map((field) => field.key);
}

function flat(value: unknown): unknown[] {
  if (value === undefined || value === null) return [];
  if (Array.isArray(value)) return value.flatMap(flat);
  return [value];
}

/** What a path reaches: through a list, each item; through a wrapper that has no such field, what it holds */
export function resolve(value: unknown, path: string[], context: LabelContext): unknown[] {
  let current = flat(value);
  for (const name of path) current = current.flatMap((item) => step(item, name, context));
  return current;
}

const open = (values: unknown[], context: LabelContext) => values.flatMap((item) => opened(item, context));

/**
 * A wrapper with no template of its own, as what it holds (so that `count` and `join` take its members: `each`,
 * `first` and `last` take the wrappers themselves)
 */
function opened(item: unknown, context: LabelContext): unknown[] {
  const model = modelOf(context, item);
  if (!model || !WRAPPERS.includes(model.kind) || model.labelTemplate) return [item];
  return contentKeys(model).flatMap((key) => flat((item as FormData)[key]).flatMap((held) => opened(held, context)));
}

function step(item: unknown, name: string, context: LabelContext): unknown[] {
  const model = modelOf(context, item);
  if (!model) return isObject(item) ? flat(item[name]) : [];
  const field = model.fields.find((each) => each.name === name);
  if (field) return flat((item as FormData)[field.key]);
  if (WRAPPERS.includes(model.kind)) {
    return contentKeys(model).flatMap((key) =>
      flat((item as FormData)[key]).flatMap((held) => step(held, name, context)),
    );
  }
  return [];
}

/** A value as text in a label (undefined: nothing) */
export function textOf(value: unknown, context: LabelContext): string | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value === "boolean" || typeof value === "number") return String(value);
  if (typeof value === "string") return value || undefined;
  if (Array.isArray(value)) {
    const texts = value.map((each) => textOf(each, context)).filter((text): text is string => !!text);
    return texts.join(", ") || undefined;
  }
  if (!isObject(value)) return undefined;
  if (typeof value.label === "string" && value.label) return value.label;
  const model = modelOf(context, value);
  if (!model) return "value" in value ? textOf(value.value, context) : undefined;
  const template = model.labelTemplate;
  if (template && "formatter" in template) {
    return context.formatter(template.formatter)?.(value) || undefined;
  }
  if (template) return render(template.alternatives, value, context);
  if (WRAPPERS.includes(model.kind)) {
    return textOf(
      contentKeys(model).flatMap((key) => flat(value[key])),
      context,
    );
  }
  return undefined;
}

/** The label the first alternative that gives one gives (undefined: none does) */
export function render(alternatives: string[], value: unknown, context: LabelContext): string | undefined {
  return renderParsed(alternatives.map(parseTemplate), value, context);
}

function renderParsed(alternatives: Part[][], value: unknown, context: LabelContext): string | undefined {
  for (const parts of alternatives) {
    const made = renderParts(parts, value, context);
    const clean = made?.replace(/\s+/g, " ").trim();
    if (clean) return clean;
  }
  return undefined;
}

function renderParts(parts: Part[], value: unknown, context: LabelContext): string | undefined {
  let out = "";
  for (const part of parts) {
    if (part.kind === "text") out += part.text;
    else if (part.kind === "group") out += renderParts(part.parts, value, context) ?? "";
    else {
      const text = placeholder(part.path, part.filters, value, context);
      if (text === undefined) return undefined;
      out += text;
    }
  }
  return out;
}

function placeholder(path: string[], filters: Filter[], value: unknown, context: LabelContext): string | undefined {
  let values = resolve(value, path, context);
  for (const filter of filters) {
    switch (filter.name) {
      case "each":
        values = values
          .map((item) => renderParsed([filter.template!], item, context))
          .filter((made): made is string => !!made);
        break;
      case "first":
        values = values.slice(0, 1);
        break;
      case "last":
        values = values.slice(-1);
        break;
      case "count":
        values = open(values, context);
        values = values.length ? [String(values.length)] : [];
        break;
      case "join": {
        const texts = open(values, context).map((each) => textOf(each, context)).filter((text): text is string => !!text);
        const separator = filter.args[0] ?? ", ";
        const last = filter.args[1] ?? separator;
        const joined = texts.length > 1 ? texts.slice(0, -1).join(separator) + last + texts.at(-1) : texts.join("");
        values = joined ? [joined] : [];
        break;
      }
      case "default":
        if (!textOf(values, context)) values = [filter.args[0]];
        break;
      case "lower":
      case "capitalise": {
        let text = textOf(values, context);
        if (text) text = filter.name === "lower" ? text.toLowerCase() : text[0]!.toUpperCase() + text.slice(1);
        values = text ? [text] : [];
        break;
      }
    }
  }
  return textOf(open(values, context), context);
}

/** A reference to an item of its own (`{type, id, label}`), not one written here */
export function isReference(value: FormData): boolean {
  return Object.keys(value).every((key) => NOT_CONTENTS.has(key));
}

/** Its label is to be worked out: it says so, or says nothing and has none */
export function isAutomatic(value: FormData): boolean {
  return value.labelAuto === true || ((value.labelAuto === undefined || value.labelAuto === null) && !value.label);
}

/**
 * Works out the labels of `root` and of what it holds, innermost first, in place: `label`, and `labelAuto` true, where
 * they are automatic. A node whose label was written by hand is left as it is (`labelAuto` false is the server's to set,
 * or the pencil's). Only keys that change are written: the form's store sees no change where there is none
 */
export function deriveLabels(root: unknown, context: LabelContext): void {
  const visit = (value: unknown, top: boolean) => {
    if (Array.isArray(value)) {
      value.forEach((item) => visit(item, false));
      return;
    }
    if (!isObject(value)) return;
    if (!top && isReference(value)) return;
    for (const [key, item] of Object.entries(value)) {
      if (!NOT_WALKED.has(key)) visit(item, false);
    }
    const model = modelOf(context, value);
    if (!derivesLabel(model) || !isAutomatic(value)) return;
    const label = render((model!.labelTemplate as { alternatives: string[] }).alternatives, value, context) ?? "";
    if (value.label !== label) value.label = label;
    if (value.labelAuto !== true) value.labelAuto = true;
  };
  visit(root, true);
}

/**
 * The form hook that keeps automatic labels up to date: after each change, every label of the item that its template
 * works out is worked out again (only after a change by the user: an item opened shows the labels it was saved with)
 */
export function createLabeller(context: LabelContext): FormHook<true> {
  const any = Object.values(context.definitions.models).some(derivesLabel);
  return {
    before: () => (any ? [true] : []),
    after(root, pending) {
      if (pending.length > 0) deriveLabels(root, context);
    },
  };
}
