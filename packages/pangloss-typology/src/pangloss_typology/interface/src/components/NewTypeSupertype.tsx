import { badgeClass, createItem, EntityPicker, FieldRow, useApi, useComponent, useTranslations } from "@pangloss/interface-core";
import type { NewItemActionProps, NewItemForm } from "@pangloss/interface-core";
import { createSignal, Show, untrack } from "solid-js";
import { moveType } from "../api";

// (the relation from a type to the one it is below: kept by the typology, so on no form of its own)
const IS_SUBTYPE_OF = "is_subtype_of";

/** Whether a model is the entity of a typology (`RoleType`): it has the relation to its supertype, kept by the typology */
export function isTypologyEntity(model: NewItemActionProps["model"]): boolean {
  return model.kind === "Entity" && model.fields.some((field) => field.name === IS_SUBTYPE_OF && field.readOnly);
}

function Supertype(props: { type: string; form: NewItemForm }) {
  const api = useApi();
  const { t } = useTranslations();
  const ReferenceChip = useComponent("ReferenceChip");
  const [below, setBelow] = createSignal<{ id: string; type: string; label: string }>();

  // How Save sends it, at the top level or below another: as any entity is made, with everything in the form, and with
  // no supertype, which the form leaves out as the typology keeps it (a `Create` wants every relation, so `[]`, the
  // one value a create may give it); then moved below the one chosen. (Made the usual way, it was refused)
  const type = untrack(() => props.type);
  const sendBelow = (supertype: string | undefined) =>
    props.form.sendBy(async (body) => {
      const { type: _, ...fields } = body;
      const made = await createItem(api, type, { ...fields, isSubtypeOf: [] });
      if (supertype) await moveType(api, type, made.id, supertype);
      return made;
    });
  sendBelow(undefined);
  const choose = (picked: { id: string; type: string; label: string }) => {
    sendBelow(picked.id);
    setBelow(picked);
  };
  const topLevel = () => {
    sendBelow(undefined);
    setBelow(undefined);
  };

  return (
    <FieldRow
      name={t("typology_supertype", "Below")}
      description={t("typology_supertype_note", "The type it is a subtype of; or none, at the top level")}
    >
      <Show
        when={below()}
        fallback={
          <div class="flex w-full min-w-0 flex-col items-start gap-2" data-testid="typology-supertype">
            <span class={badgeClass} data-testid="typology-top-level">
              {t("typology_top_level", "Top level")}
            </span>
            <div class="w-full">
              <EntityPicker
                types={[props.type]}
                onPick={choose}
                placeholder={t("typology_find_supertype", "Or find the type it is below")}
              />
            </div>
          </div>
        }
      >
        {(picked) => (
          <span class="flex max-w-full min-w-0" data-testid="typology-supertype-chosen">
            <ReferenceChip
              type={picked().type}
              label={picked().label}
              onRemove={topLevel}
              removeLabel={t("typology_to_top_level", "At the top level instead")}
            />
          </span>
        )}
      </Show>
    </FieldRow>
  );
}

/**
 * The type a new type is below (a `newItemFields` entry: a row first among the fields of a new type, on its page and in
 * the dialog of a relation, where a type is made without the tree). Its relation to its supertype is kept by the
 * typology, and is on no form: Save makes it with none, and then moves it below the one chosen.
 */
export default function NewTypeSupertype(props: NewItemActionProps) {
  return (
    <Show when={isTypologyEntity(props.model)}>
      <Supertype type={props.type} form={props.form} />
    </Show>
  );
}
