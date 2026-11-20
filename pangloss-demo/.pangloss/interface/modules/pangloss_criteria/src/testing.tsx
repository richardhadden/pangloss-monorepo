// (what the module's component tests share: the models, an API that answers as a test says, and the page round them)
import {
  ApiProvider,
  ComponentsProvider,
  Modal,
  ModelsProvider,
  ReferenceChip,
} from "@pangloss/interface-core";
import type { ApiClient, ComponentMap, ModelDefinitions } from "@pangloss/interface-core";
import { flush } from "solid-js";
import { render } from "@solidjs/web";
import type { JSX } from "@solidjs/web";

const field = (name: string, extra: Record<string, unknown> = {}) => ({
  name,
  key: name,
  kind: "literal",
  type: { type: "str" },
  validators: [],
  description: null,
  dbField: false,
  readOnly: false,
  required: false,
  nullable: true,
  default: null,
  ...extra,
});

const model = (name: string, kind: string, fields: unknown[] = []) => ({
  name,
  kind,
  parent: null,
  abstract: false,
  concreteTypes: [name],
  description: null,
  typeParameters: kind === "ReifiedRelation" ? ["T"] : [],
  interfaceMeta: null,
  fields,
  incoming: [],
});

export const person = { kind: "entity" as const, type: "Person", edgeModel: null };

/** The option of a relation that takes a description of a person */
export const describedPerson = {
  kind: "reifiedRelation" as const,
  type: "MatchesCriteria",
  edgeModel: null,
  params: { T: { typeVar: "T", options: [person] } },
};

// (a person has a year of birth and friends; a description has its computed fields, as the export marks them; a
// sighting has two fields that take a description of a person)
export const definitions = {
  models: {
    Person: model("Person", "Entity"),
    MatchesCriteria: model("MatchesCriteria", "ReifiedRelation", [
      field("wording"),
      field("criteria"),
      field("same_one", { key: "sameOne", type: { type: "UUID" } }),
      field("description", {
        kind: "relation",
        many: false,
        options: [{ kind: "document", type: "PGCitation", edgeModel: null, cites: ["Description"] }],
      }),
      field("target", { kind: "relation", computed: true, readOnly: true, many: true, options: [{ kind: "typeVar", name: "T", edgeModel: null }] }),
      field("candidate_count", { key: "candidateCount", computed: true, readOnly: true, type: { type: "int" } }),
      field("evaluated_when", { key: "evaluatedWhen", computed: true, readOnly: true }),
      field("broken", { computed: true, readOnly: true }),
      field("broken_since", { key: "brokenSince", computed: true, readOnly: true }),
    ]),
    Description: model("Description", "Document", [field("criteria")]),
    PGCitation: model("PGCitation", "Document"),
    Sighting: model("Sighting", "Document", [
      field("seen", { kind: "relation", many: true, options: [person, describedPerson] }),
      field("company", { kind: "relation", many: true, options: [describedPerson] }),
    ]),
  },
  enums: {},
  searchPatterns: {
    Person: {
      kind: "entity",
      fields: { born: { operators: "compare", value: { type: "int" } }, friend: { operators: "relation", targets: ["Person"] } },
      orderBy: [],
    },
  },
} as unknown as ModelDefinitions;

export const MARIE = "00000000-0000-0000-0000-0000000000a1";
/** A shared description */
export const SECRETARY = "00000000-0000-0000-0000-0000000000e1";

/** The citation of the shared description `SECRETARY`, as a read gives it */
export const citesSecretary = (extra: Record<string, unknown> = {}) => ({
  type: "PGCitation",
  id: "00000000-0000-0000-0000-0000000000c1",
  targetId: SECRETARY,
  targetType: "Description",
  targetLabel: "The duke's secretary",
  targetHeadId: SECRETARY,
  targetHeadType: "Description",
  targetHeadLabel: "The duke's secretary",
  targetState: "there",
  changedSinceCited: false,
  ...extra,
});

/** The shared description `SECRETARY` as the list of them gives it */
export const secretary = { id: SECRETARY, label: "The duke's secretary", criteria: { type: "Person", where: { born: { eq: 1500 } } }, mentions: 3 };
export const CHARLES = "00000000-0000-0000-0000-0000000000a2";

/** One call the API was asked */
export interface Asked {
  path: string;
  body: unknown;
}

/**
 * An API whose answers a test gives: `answer(path, body)` is called for each request, and what it gives (or the
 * promise it gives) is the answer. Every request is kept in `asked`
 */
export function fakeApi(answer: (path: string, body: unknown) => unknown) {
  const asked: Asked[] = [];
  const call = async (path: string, body?: unknown) => {
    asked.push({ path, body });
    return answer(path, body);
  };
  const client = {
    baseUrl: "/api",
    get: (path: string, query?: unknown) => call(path, query),
    post: (path: string, body?: unknown) => call(path, body),
    put: (path: string, body?: unknown) => call(path, body),
    patch: (path: string, body?: unknown) => call(path, body),
    delete: (path: string) => call(path),
    postForm: (path: string, body?: unknown) => call(path, body),
  } as unknown as ApiClient;
  return { client, asked };
}

let dispose: (() => void) | undefined;

/**
 * Draws `view` on the page with the models, the API and the components (`ReferenceChip`, `Modal`, and `more`) round
 * it
 */
export function show(client: ApiClient, view: () => JSX.Element, more: Record<string, unknown> = {}) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={{ ReferenceChip, Modal, ...more } as unknown as ComponentMap}>
        <ModelsProvider definitions={definitions}>
          <ApiProvider client={client}>{view()}</ApiProvider>
        </ModelsProvider>
      </ComponentsProvider>
    ),
    container,
  );
}

export function cleanUp() {
  dispose?.();
  dispose = undefined;
  document.body.innerHTML = "";
}

export const settle = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));

export const byLabel = <T extends HTMLElement>(label: string) => document.body.querySelector<T>(`[aria-label="${label}"]`);
export const byTestId = (id: string) => document.body.querySelector<HTMLElement>(`[data-testid="${id}"]`);
export const button = (name: string) =>
  [...document.body.querySelectorAll<HTMLButtonElement>("button")].find((each) => each.textContent?.trim() === name);

export const click = (element: Element | null | undefined) => {
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
  flush();
};

export const type = (label: string, text: string) => {
  const input = byLabel<HTMLInputElement>(label)!;
  input.value = text;
  input.dispatchEvent(new InputEvent("input", { bubbles: true }));
  flush();
};

/** Adds a condition on `name` with the search form's menu (as `SearchFields`' own tests do) */
export function addFilter(name: string) {
  const menu = document.body.querySelector<HTMLElement>('[role="combobox"][aria-label="Add a filter"]')!;
  if (menu.getAttribute("aria-expanded") !== "true") click(menu);
  const options = [...document.getElementById(menu.getAttribute("aria-controls")!)!.querySelectorAll<HTMLElement>('[role="option"]')];
  click(options.find((option) => option.dataset.value!.endsWith(`:${name}`)));
}
