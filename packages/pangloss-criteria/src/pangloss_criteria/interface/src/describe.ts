/**
 * The summary of criteria, made by one function used wherever criteria are shown (`describeCriteria`): from the
 * stored pattern and the translated names of the types and fields, a sentence as a list of parts (text, the name
 * of a type, an entity, brackets round what is nested), which `CriteriaSummary` draws with each entity as a chip:
 *
 *   Person · holder of: HoldsOffice (office: [Secretary], employer: [Maximilian I])
 *
 * (what refers to an entity is named by its reverse name, as the entity's page names it: `holder_of` here)
 *
 * It reads the `where` itself, not through the search form (`whereToForm`), so that it says what the form cannot
 * show too. A key or an operator it does not know is said as it is written, with its value: never left out.
 * (implementation_docs/matches-criteria.md, "The interface")
 */
import { flagWords, getModel } from "@pangloss/interface-core";
import type { ModelDefinitions, Translations } from "@pangloss/interface-core";
import type { Criteria } from "./api";
import type { Labels } from "./labels";

export type Part =
  | { kind: "text"; text: string }
  /** The name of a type (a model), as the page says it */
  | { kind: "type"; type: string; text: string }
  /** An entity, by its id: its label comes from `/api/references` */
  | { kind: "entity"; id: string }
  | { kind: "open" }
  | { kind: "close" };

/** What the summary says names with */
export type Words = Pick<Translations, "t" | "modelName" | "fieldName" | "incomingName">;

type Where = Record<string, unknown>;

const isObject = (value: unknown): value is Where =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const text = (said: string): Part => ({ kind: "text", text: said });

/** The parts of `lists`, with `between` between each two */
function joined(lists: Part[][], between: Part[]): Part[] {
  return lists.flatMap((list, index) => (index === 0 ? list : [...between, ...list]));
}

/** A translated phrase whose `{name}`s are parts: `{field} contains “{value}”` */
function phrase(template: string, given: Record<string, Part[]>): Part[] {
  const parts: Part[] = [];
  let at = 0;
  for (const match of template.matchAll(/\{(\w+)\}/g)) {
    const name = match[1]!;
    if (!Object.hasOwn(given, name)) continue;
    if (match.index > at) parts.push(text(template.slice(at, match.index)));
    parts.push(...given[name]!);
    at = match.index + match[0].length;
  }
  if (at < template.length) parts.push(text(template.slice(at)));
  return parts;
}

/** A value as it is said: a text in quotation marks, a list with commas, anything else as JSON */
function literal(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(literal).join(", ");
  return JSON.stringify(value);
}

/**
 * The parts that say `criteria`: its type, then each of its conditions. Nothing for no criteria. `definitions` give
 * the names of what refers to an entity (`$incoming`) by its reverse name, as an entity's page has them
 */
export function describeCriteria(
  criteria: Criteria | null | undefined,
  words: Words,
  definitions?: ModelDefinitions,
): Part[] {
  if (!criteria || typeof criteria.type !== "string" || criteria.type === "") return [];
  const { t, modelName, fieldName, incomingName } = words;
  const type = (name: string): Part => ({ kind: "type", type: name, text: modelName(name) });
  const or = () => [text(` ${t("criteria_or", "or")} `)];
  const comma = [text(", ")];
  const entities = (ids: unknown): Part[] =>
    joined(
      (Array.isArray(ids) ? ids : [ids]).map((id) => (typeof id === "string" ? [{ kind: "entity", id }] : [text(literal(id))])),
      or(),
    );
  // (something said as it is written: a key the summary does not know, with its value)
  const raw = (key: string, value: unknown): Part[] => [text(`${key}: ${JSON.stringify(value)}`)];

  /** A node of a type, with its conditions in brackets after it, if it has any */
  const node = (name: unknown, where: unknown): Part[] => {
    if (typeof name !== "string") return raw("type", name);
    const inner = isObject(where) ? conditions(name, where) : [];
    return inner.length > 0 ? [type(name), text(" "), { kind: "open" }, ...joined(inner, comma), { kind: "close" }] : [type(name)];
  };

  /** The name of what refers to an entity of `of` by the field `field` of `source`: its reverse name, as translated */
  const incomingNameOf = (of: string, source: string, field: string): string => {
    const relation = definitions?.models[of]?.incoming.find((incoming) =>
      incoming.sources.some((each) => each.model === source && each.field === field),
    );
    if (relation) return incomingName(of, relation.name);
    const forward = getModelSafely(definitions, source)?.fields.find((each) => each.name === field || each.key === field);
    return forward && forward.kind === "relation" ? incomingName(of, forward.reverseName) : fieldName(source, field);
  };

  /** The conditions on one field of a node of `of` */
  const onField = (of: string, key: string, value: unknown): Part[][] => {
    const name = [text(key === "label" ? t("label", "Label") : fieldName(of, key))];
    if (!isObject(value)) return [phrase(t("criteria_is", "{field}: {value}"), { field: name, value: [text(literal(value))] })];
    const { through, ...rest } = value;
    const wrappers =
      Array.isArray(through) && through.length > 0
        ? phrase(t("criteria_through", " through {wrappers}"), {
            wrappers: joined(through.map((each) => (typeof each === "string" ? [type(each)] : [text(literal(each))])), comma),
          })
        : through === undefined
          ? []
          : [text(" "), ...raw("through", through)];
    const said: Part[][] = [];
    if ("type" in rest) {
      const { type: target, where, ...more } = rest;
      said.push([...phrase(t("criteria_is", "{field}: {value}"), { field: name, value: node(target, where) }), ...wrappers]);
      for (const [other, inner] of Object.entries(more)) said.push([...name, text(" "), ...raw(other, inner)]);
      return said;
    }
    const keys = Object.keys(rest);
    if (keys.length === 0) return [[...name, ...wrappers]];
    for (const op of keys) {
      const given = rest[op];
      const value = [text(literal(given))];
      let one: Part[];
      switch (op) {
        case "contains":
          one = phrase(t("criteria_contains_text", "{field} contains “{value}”"), { field: name, value });
          break;
        case "starts_with":
          one = phrase(t("criteria_starts_with", "{field} starts with “{value}”"), { field: name, value });
          break;
        case "eq":
          one = phrase(t("criteria_is", "{field}: {value}"), { field: name, value });
          break;
        case "gt":
        case "gte":
        case "lt":
        case "lte":
          one = [...name, text(` ${{ gt: ">", gte: "≥", lt: "<", lte: "≤" }[op]} `), ...value];
          break;
        case "between": {
          const [from, to] = Array.isArray(given) ? given : [given, undefined];
          one = phrase(t("criteria_between", "{field} between {from} and {to}"), {
            field: name,
            from: [text(literal(from))],
            to: [text(literal(to))],
          });
          break;
        }
        case "in":
          one = phrase(t("criteria_one_of", "{field}: one of {value}"), { field: name, value });
          break;
        case "exists":
          one =
            given === false
              ? phrase(t("criteria_missing", "no {field}"), { field: name })
              : phrase(t("criteria_exists", "{field} given"), { field: name });
          break;
        case "is":
        case "is_any":
          one = phrase(t("criteria_is", "{field}: {value}"), { field: name, value: entities(given) });
          break;
        default:
          one = [...name, text(" "), ...raw(op, given)];
      }
      said.push([...one, ...wrappers]);
    }
    return said;
  };

  /** Each condition of a node of `of`, as parts */
  function conditions(of: string, where: Where): Part[][] {
    const said: Part[][] = [];
    for (const [key, value] of Object.entries(where)) {
      switch (key) {
        case "$all":
          if (Array.isArray(value) && value.every(isObject)) for (const each of value) said.push(...conditions(of, each));
          else said.push(raw(key, value));
          break;
        case "$not": {
          const inner = isObject(value) ? conditions(of, value) : [];
          said.push(
            inner.length > 0
              ? phrase(t("criteria_not", "not {conditions}"), {
                  conditions: [{ kind: "open" }, ...joined(inner, comma), { kind: "close" }],
                })
              : raw(key, value),
          );
          break;
        }
        case "$any_of": {
          if (!Array.isArray(value) || !value.every(isObject)) {
            said.push(raw(key, value));
            break;
          }
          const alternatives = value.map((each) => {
            const inner = conditions(of, each);
            return inner.length > 1 ? [{ kind: "open" } as Part, ...joined(inner, comma), { kind: "close" } as Part] : joined(inner, comma);
          });
          said.push([{ kind: "open" }, ...joined(alternatives, or()), { kind: "close" }]);
          break;
        }
        case "$incoming":
        case "$somewhere": {
          if (!Array.isArray(value) || !value.every(isObject)) {
            said.push(raw(key, value));
            break;
          }
          for (const pattern of value) {
            const { type: source, field, where: inner, ...more } = pattern;
            const what = node(source, inner);
            if (key === "$somewhere") said.push(phrase(t("criteria_contains", "contains {node}"), { node: what }));
            else if (typeof field === "string" && typeof source === "string")
              said.push(phrase(t("criteria_incoming", "{relation}: {node}"), { relation: [text(incomingNameOf(of, source, field))], node: what }));
            else said.push(phrase(t("criteria_referred_to_by", "referred to by {node}"), { node: what }));
            for (const [other, extra] of Object.entries(more)) said.push(raw(other, extra));
          }
          break;
        }
        case "$mentions": {
          const ids = isObject(value) ? (value.is_any ?? value.is) : undefined;
          const only = isObject(value) && Object.keys(value).length === 1 && ("is" in value || "is_any" in value);
          said.push(only ? phrase(t("criteria_mentions", "mentions {entities}"), { entities: entities(ids) }) : raw(key, value));
          break;
        }
        case "$spaces":
          said.push(
            Array.isArray(value) && value.every((each) => typeof each === "string")
              ? phrase(t("criteria_inside", "inside {spaces}"), { spaces: joined(value.map((space) => [type(space)]), comma) })
              : raw(key, value),
          );
          break;
        default:
          if (key.startsWith("$")) {
            // (a yes-or-no filter of an installed app, named as the search form names it)
            said.push(
              typeof value === "boolean"
                ? phrase(t("criteria_flag", "{flag}: {value}"), {
                    flag: [text(t(`search_flag_${key.replace(/^\$/, "")}`, flagWords(key)))],
                    value: [text(value ? t("yes", "Yes") : t("no", "No"))],
                  })
                : raw(key, value),
            );
          } else said.push(...onField(of, key, value));
      }
    }
    return said;
  }

  const said = isObject(criteria.where) ? conditions(criteria.type, criteria.where) : [];
  return said.length > 0 ? [type(criteria.type), text(" · "), ...joined(said, comma)] : [type(criteria.type)];
}

function getModelSafely(definitions: ModelDefinitions | undefined, name: string) {
  return definitions ? getModel(definitions, name) : undefined;
}

/** Every entity the summary names, each once, in order: what `/api/references` is asked about */
export function idsOf(parts: Part[]): string[] {
  return [...new Set(parts.flatMap((part) => (part.kind === "entity" ? [part.id] : [])))];
}

/** What each part says as text, an entity by its label in square brackets (`gone` for one that is not found) */
function partText(part: Part, labels: Labels | undefined, gone: string): string {
  switch (part.kind) {
    case "text":
    case "type":
      return part.text;
    case "entity": {
      const found = labels?.get(part.id);
      return labels === undefined ? "[…]" : found === undefined ? `[${gone}]` : `[${found.label}]`;
    }
    case "open":
      return "(";
    case "close":
      return ")";
  }
}

/** The summary as plain text (for `title=`): the entities by their labels, `gone` for one that was not found */
export function describeText(parts: Part[], labels: Labels | undefined, gone: string): string {
  return parts.map((part) => partText(part, labels, gone)).join("");
}

/**
 * The parts that fit in about `most` characters, the last text cut with "…" if they do not all fit (an entity is
 * the length of its label, and is not cut); `cut` says whether anything was left out
 */
export function cutParts(
  parts: Part[],
  labels: Labels | undefined,
  gone: string,
  most = 120,
): { parts: Part[]; cut: boolean } {
  const kept: Part[] = [];
  let length = 0;
  for (const part of parts) {
    const said = partText(part, labels, gone);
    if (length + said.length <= most) {
      kept.push(part);
      length += said.length;
      continue;
    }
    if (part.kind === "text" || part.kind === "type") {
      const room = Math.max(0, most - length);
      const start = said.slice(0, room).trimEnd();
      if (start) kept.push({ kind: "text", text: start });
    }
    kept.push(text("…"));
    return { parts: kept, cut: true };
  }
  return { parts: kept, cut: false };
}
