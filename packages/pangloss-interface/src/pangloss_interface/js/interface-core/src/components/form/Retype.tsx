import { createMemo, createSignal, For, Show } from "solid-js";
import { useComponent, useModels, useTranslations } from "../../context";
import { menuGroups, narrowingChoices, retype, widerTypes } from "../../schema";
import type { FormData, LostField } from "../../schema";
import type { RelationOption } from "../../types";
import { TypeMenu } from "./TypeMenu";
import { buttonClass } from "../../primitives";

const typeOptions = (types: string[]): RelationOption[] =>
  types.map((type) => ({ kind: "document", type, edgeModel: null }));

/**
 * The buttons of a document inside another that change its type: to one below it (narrow, ↧) or
 * above it (widen, ↥), among those that the field it is in allows; with one to go to the button does
 * it, with several it opens a menu of them. What it holds goes to the fields of the new type
 * (`retype`). A narrowing never loses anything: a type below that has no room for what is filled in
 * (an artwork, where only a painting can go) is in the menu, greyed, saying what it would lose, and
 * cannot be chosen until that is changed. A widening that would lose something (a field only the
 * narrower type has) asks first, in a dialog that says what. Neither button is there when there is
 * no type to go to.
 */
export function RetypeButtons(props: {
  type: string;
  /** The types the field it is in can hold */
  options: RelationOption[];
  /** What it is called, for the buttons' names */
  name: string;
  buttonClass: string;
  value: () => FormData | undefined;
  onRetype: (value: FormData) => void;
}) {
  const definitions = useModels();
  const Modal = useComponent("Modal");
  const { t, modelName, fieldName } = useTranslations();
  const narrowings = createMemo(() =>
    narrowingChoices(definitions, props.value() ?? { type: props.type }, props.options),
  );
  const narrower = createMemo(() => menuGroups(definitions, typeOptions(narrowings().map((choice) => choice.type))));
  const lostName = (lost: LostField) =>
    lost.edgeProperties
      ? t("retype_lost_edge", "{field}: the properties of the relation", { field: fieldName(lost.model, lost.field) }) +
        (lost.count > 1 ? ` (${lost.count})` : "")
      : fieldName(lost.model, lost.field) + (lost.count > 1 ? ` (${lost.count})` : "");
  const unavailable = createMemo(() =>
    Object.fromEntries(
      narrowings()
        .filter((choice) => choice.lost.length > 0)
        .map((choice) => [
          choice.type,
          t("narrow_would_lose", "Would lose: {fields}", { fields: choice.lost.map(lostName).join(", ") }),
        ]),
    ),
  );
  const wider = createMemo(() =>
    menuGroups(definitions, typeOptions(widerTypes(definitions, props.type, props.options))),
  );
  const [asking, setAsking] = createSignal<{ to: string; lost: LostField[] }>();
  const change = (to: string, sure = false) => {
    const value = props.value();
    if (!value) return;
    const result = retype(definitions, value, to);
    if (result.lost.length > 0 && !sure) setAsking({ to, lost: result.lost });
    else props.onRetype(result.value);
  };
  return (
    <>
      <TypeMenu
        groups={narrower()}
        unavailable={unavailable()}
        label="↧"
        title={t("narrow_type", "Narrow {name} to a type below it", { name: props.name })}
        buttonClass={props.buttonClass}
        alignRight
        onChoose={(choice) => change(choice.type)}
      />
      <TypeMenu
        groups={wider()}
        label="↥"
        title={t("widen_type", "Widen {name} to a type above it", { name: props.name })}
        buttonClass={props.buttonClass}
        alignRight
        onChoose={(choice) => change(choice.type)}
      />
      <Show when={asking()}>
        {(ask) => (
          <Modal
            title={t("retype_title", "Change to {type}?", { type: modelName(ask().to) })}
            onClose={() => setAsking(undefined)}
          >
            <div class="flex flex-col gap-4 p-6 text-sm">
              <p>
                {t("retype_loses", "{type} has no room for what is in these fields of {from}, which will be lost:", {
                  type: modelName(ask().to),
                  from: modelName(props.type),
                })}
              </p>
              <ul class="list-disc pl-5" data-lost>
                <For each={ask().lost}>{(lost) => <li>{lostName(lost)}</li>}</For>
              </ul>
              <div class="flex justify-end gap-2">
                <button type="button" class={buttonClass("ordinary", "md")} autofocus onClick={() => setAsking(undefined)}>
                  {t("cancel", "Cancel")}
                </button>
                <button
                  type="button"
                  class={buttonClass("danger", "md")}
                  onClick={() => {
                    const to = ask().to;
                    setAsking(undefined);
                    change(to, true);
                  }}
                >
                  {t("retype_confirm", "Change the type")}
                </button>
              </div>
            </div>
          </Modal>
        )}
      </Show>
    </>
  );
}
