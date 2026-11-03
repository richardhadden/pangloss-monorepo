// @vitest-environment happy-dom
import { ModelsProvider } from "@pangloss/interface-core";
import type { FormData, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { day } from "./fixtures";
import { useDatedDocumentTypes, useOnTheDayFill } from "./Chrome";

const model = (name: string, kind: string, fields: object[] = [], more: object = {}) =>
  ({ name, kind, abstract: false, createDirectly: true, concreteTypes: [name], typeParameters: [], fields, interfaceMeta: null, ...more }) as unknown as ModelDefinition;
const date = (key: string, types: string[]) => ({ name: key, key, kind: "embedded", model: "Date", types });
const holds = (key: string, type: string) => ({
  name: key, key, kind: "relation", many: true, options: [{ kind: "document", type, edgeModel: null }],
});

const DEFINITIONS = {
  models: {
    Factoid: model("Factoid", "Document", [holds("statements", "Statement")]),
    Statement: model("Statement", "Document", [date("date", ["ExactDate", "Period"]), date("julian", ["JulianExactDate"])], {
      createDirectly: false,
    }),
    Report: model("Report", "Document", [date("written", ["Recurrence"])]),
    Person: model("Person", "Entity", [date("born", ["ExactDate"])]),
  },
  enums: {},
} as unknown as ModelDefinitions;

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function hooks() {
  let found: { types: () => string[]; fill: ReturnType<typeof useOnTheDayFill> } | undefined;
  const Probe = () => {
    found = { types: useDatedDocumentTypes(), fill: useOnTheDayFill() };
    return null;
  };
  dispose = render(
    () => (
      <ModelsProvider definitions={DEFINITIONS}>
        <Probe />
      </ModelsProvider>
    ),
    document.body,
  );
  return found!;
}

test("the documents offered on a day are those that can be made and have a date somewhere in them that can be one day", () => {
  // (not a statement, only ever part of a factoid; not a report, whose date is a rule; not an entity)
  expect(hooks().types()).toEqual(["Factoid"]);
});

test("each date of what is added is the day, in the page's calendar or the one its type is fixed to", () => {
  const fill = hooks().fill(day(2), "gregorian");
  const item: FormData = fill({ type: "Factoid", statements: [{ type: "Statement" }] });
  expect(item.statements).toEqual([
    {
      type: "Statement",
      date: { type: "ExactDate", calendar: "gregorian", year: 1500, month: 3, day: 12 },
      julian: { type: "JulianExactDate", calendar: "julian", year: 1500, month: 3, day: 2 },
    },
  ]);
});
