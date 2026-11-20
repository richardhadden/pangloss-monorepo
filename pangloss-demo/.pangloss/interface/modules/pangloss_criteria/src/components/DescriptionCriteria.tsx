import { FieldRow, getModel, menuGroups, TypeGrid, useItemForm, useModels, useTranslations } from "@pangloss/interface-core";
import type { ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import { createMemo, createSignal, Show, untrack } from "solid-js";
import type { Criteria } from "../api";
import { criteriaOf, DESCRIPTION } from "../value";
import { createCriteriaEditing, CriteriaFields, CriteriaResult } from "./CriteriaForm";

/** Whether the type is a shared description (or a class below it) */
function isDescription(definitions: ModelDefinitions, type: string): boolean {
  return (getModel(definitions, DESCRIPTION)?.concreteTypes ?? [DESCRIPTION]).includes(type);
}

/**
 * The classes a shared description may be of: every class of entity that can be searched, at the top of its
 * hierarchy (the grid shows the classes below each)
 */
function describable(definitions: ModelDefinitions): string[] {
  const searched = (name: string) => definitions.searchPatterns?.[name]?.kind === "entity";
  return Object.values(definitions.models)
    .filter((model) => model.kind === "Entity" && searched(model.name))
    .filter((model) => !model.parent || !searched(model.parent))
    .map((model) => model.name)
    .sort();
}

/** The criteria of one class, being edited, written into the form at `criteria` as they change */
function OfClass(props: { type: string; start: Criteria | null; onBack: () => void }) {
  const form = useItemForm();
  const editing = createCriteriaEditing(
    untrack(() => ({
      type: props.type,
      start: props.start,
      named: () => [],
      onChange: (criteria: Criteria | null) => form.set(["criteria"], criteria),
    })),
  );
  return (
    <div class="flex w-full min-w-0 flex-col gap-4" data-testid="description-criteria">
      <CriteriaFields editing={editing} onBack={props.onBack} />
      <CriteriaResult editing={editing} />
    </div>
  );
}

/**
 * The criteria of a shared description in its form (the row `newItemFields` and `editItemFields` give it: its
 * `criteria` are not edited as a plain field, `InterfaceMeta(hide_on_forms=("criteria",))`): the class first, for a
 * new one (`TypeGrid`, as a mention's dialog has it), then the search form of the class and what it finds, as in the
 * dialog of a mention. Back chooses another class, and the criteria go. Nothing for a form of another class
 */
function Row() {
  const form = useItemForm();
  const definitions = useModels();
  const { fieldName, t } = useTranslations();
  // (what it was saved with, shown in the form of its class; not once another class has been chosen)
  let start = untrack(() => criteriaOf({ criteria: form.get(["criteria"]) }));
  const [type, setType] = createSignal<string | undefined>(start?.type);
  const groups = createMemo(() =>
    menuGroups(definitions, describable(definitions).map((name) => ({ kind: "entity" as const, type: name, edgeModel: null }))),
  );
  const back = () => {
    start = null;
    form.set(["criteria"], null);
    setType(undefined);
  };
  const name = () => fieldName(DESCRIPTION, "criteria");
  return (
    <FieldRow name={name()} path={["criteria"]} required met={type() !== undefined}>
      <Show
        when={type()}
        keyed
        fallback={
          <div class="flex w-full min-w-0 flex-col gap-2" data-testid="description-choose-type">
            <span class="text-sm text-slate-700">{t("criteria_choose_type", "What is described")}</span>
            <div class="overflow-hidden rounded-xs border-[0.5px] border-dashed border-slate-400/80 bg-white/60">
              <TypeGrid groups={groups()} onChoose={(choice) => setType(choice.type)} />
            </div>
          </div>
        }
      >
        {(chosen) => <OfClass type={chosen} start={start?.type === chosen ? start : null} onBack={back} />}
      </Show>
    </FieldRow>
  );
}

/** (`newItemFields`, `editItemFields`) The row of the criteria of a shared description; nothing in another form */
export default function DescriptionCriteria(props: { type: string; model: ModelDefinition }) {
  const definitions = useModels();
  return (
    <Show when={isDescription(definitions, props.type)}>
      <Row />
    </Show>
  );
}
