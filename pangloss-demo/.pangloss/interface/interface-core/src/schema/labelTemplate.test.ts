import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";
import type { ModelDefinitions } from "../types";
import { createLabeller, deriveLabels, parseTemplate, render } from "./labelTemplate";
import type { LabelContext } from "./labelTemplate";

// The cases the server's `pangloss_models.label_templates` gives these labels for (written by
// `pangloss-models/tests/test_label_templates.py`): the interface must give the same
const cases = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../../../../../pangloss-models/tests/label_cases.json", import.meta.url)), "utf8"),
) as {
  models: Record<string, { kind: string; requireLabel: boolean; labelTemplate: unknown; fields: unknown[] }>;
  cases: { name: string; data: unknown; expected: unknown }[];
};

const definitions = {
  models: Object.fromEntries(
    Object.entries(cases.models).map(([name, model]) => [
      name,
      { ...model, name, labelTemplate: model.labelTemplate ?? undefined },
    ]),
  ),
  enums: {},
} as unknown as ModelDefinitions;
const context: LabelContext = { definitions, formatter: () => undefined };

// (the server also says `labelAuto: false` of a label written by hand; the form leaves that to the server)
function withoutManualFlags(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(withoutManualFlags);
  if (typeof value !== "object" || value === null) return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key, each]) => !(key === "labelAuto" && each === false))
      .map(([key, each]) => [key, withoutManualFlags(each)]),
  );
}

for (const each of cases.cases) {
  test(`the same label as the server: ${each.name}`, () => {
    const made = structuredClone(each.data);
    deriveLabels(made, context);
    expect(withoutManualFlags(made)).toEqual(withoutManualFlags(each.expected));
  });
}

test("a literal that names a class is a value: nothing in it is given a label", () => {
  // (a class whose label is worked out, named inside a stored search pattern: the pattern is left as it is)
  const derived = Object.entries(definitions.models).find(([, model]) => model.labelTemplate && "alternatives" in (model.labelTemplate as object))![0];
  const holding = {
    ...definitions,
    models: {
      ...definitions.models,
      Holder: { name: "Holder", kind: "ReifiedRelation", requireLabel: false, fields: [{ kind: "literal", name: "criteria", key: "criteria" }] },
    },
  } as unknown as ModelDefinitions;
  const criteria = { type: "Person", where: { $incoming: [{ type: derived, field: "member", where: {} }] } };
  const item = { type: "Holder", criteria: structuredClone(criteria) };
  deriveLabels(item, { definitions: holding, formatter: () => undefined });
  expect(item.criteria).toEqual(criteria);
});

test("a template that cannot be read says where", () => {
  expect(() => parseTemplate("Birth of {person")).toThrow(/a } expected/);
  expect(() => parseTemplate("{people|jion}")).toThrow(/no filter 'jion'/);
});

test("the first alternative that gives a label is taken", () => {
  expect(render(["{surname}", "{forename}", "nobody"], { type: "Person", forename: "A" }, context)).toBe("A");
  expect(render(["{surname}", "{forename}", "nobody"], { type: "Person" }, context)).toBe("nobody");
});

test("a formatter of a module gives the text of what names it", () => {
  const dated = {
    ...definitions,
    models: {
      ...definitions.models,
      Day: { name: "Day", kind: "Embedded", requireLabel: false, labelTemplate: { formatter: "app:day" }, fields: [] },
      Event: {
        name: "Event",
        kind: "Document",
        requireLabel: true,
        labelTemplate: { alternatives: ["Event[ on {when}]"] },
        fields: [{ name: "when", key: "when", kind: "embedded" }],
      },
    },
  } as unknown as ModelDefinitions;
  const event: Record<string, unknown> = { type: "Event", when: { type: "Day", n: 3 } };
  deriveLabels(event, { definitions: dated, formatter: (name) => (name === "app:day" ? (v) => `day ${v.n}` : undefined) });
  expect(event.label).toBe("Event on day 3");
});

test("the form hook works the labels out after a change, and not for models without templates", () => {
  const labeller = createLabeller(context);
  const root: Record<string, unknown> = { type: "Person", forename: "Anne", surname: "Hathaway" };
  const pending = labeller.before(root, ["surname"], false);
  labeller.after(root, pending);
  expect(root).toMatchObject({ label: "Hathaway, Anne", labelAuto: true });
  // (written by hand: left alone)
  root.labelAuto = false;
  root.label = "Mrs Shakespeare";
  labeller.after(root, labeller.before(root, ["surname"], false));
  expect(root.label).toBe("Mrs Shakespeare");

  const none = createLabeller({ definitions: { models: {}, enums: {} } as unknown as ModelDefinitions, formatter: () => undefined });
  expect(none.before({}, ["x"], false)).toEqual([]);
});
