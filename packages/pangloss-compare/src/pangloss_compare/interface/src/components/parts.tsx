import { For, Loading, Show } from "solid-js";
import {
  createInBrowser,
  useComponent,
  useModels,
  useModules,
  userIsLoggedIn,
  useTranslations,
} from "@pangloss/interface-core";
import type { EntityChip, PairEntry, Relation, StatementChip } from "../api";
import { entityHref, fieldOf, fieldsSaid, HOW_WORDS, RELATION_WORDS, verdictRelation } from "../compared";

// What the section "Compared" and the page of two side by side both draw: the words of a relation, of its fields, a
// user's name, and whose claim a statement is

/** Text of the frame (not content) */
export const frame = "shrink-0 text-xs font-semibold text-slate-500 uppercase select-none";

/** A relation in words */
export function useRelationWords() {
  const { t } = useTranslations();
  return (relation: Relation) => t(...RELATION_WORDS[relation]);
}

/** A person's verdict in words: as the relation it says (`two_events` is "Two events") */
export function useVerdictWords() {
  const words = useRelationWords();
  return (verdict: string) => {
    const relation = verdictRelation(verdict);
    return Object.hasOwn(RELATION_WORDS, relation) ? words(relation) : verdict;
  };
}

/** The name of a field of the answer (camelCase) by the first of `types` that has it, as the interface names fields */
export function useAnswerFieldName() {
  const definitions = useModels();
  const { fieldName } = useTranslations();
  return (types: readonly (string | null | undefined)[], key: string) => {
    const found = fieldOf(definitions, types, key);
    return found ? fieldName(found.model, found.name) : key;
  };
}

/**
 * What a pair says of the fields, in words: a disagreement "on Town", what was carried out otherwise "(When: late)",
 * by each field's label; "" where it says nothing of them
 */
export function useFieldsWords() {
  const { t } = useTranslations();
  const name = useAnswerFieldName();
  return (pair: Pick<PairEntry, "relation" | "fields" | "how" | "common" | "other">, statement: StatementChip) => {
    const said = fieldsSaid(pair);
    if (said.length === 0) return "";
    const named = said
      .map(({ field, how }) => {
        const label = name([pair.common, statement.type, pair.other.type], field);
        return how ? t("compare_field_how", "{field}: {how}", { field: label, how: t(...HOW_WORDS[how]) }) : label;
      })
      .join(", ");
    return pair.relation === "disagree"
      ? t("compare_fields_on", "on {fields}", { fields: named })
      : t("compare_targets", "({fields})", { fields: named });
  };
}

/**
 * A user's name: a link to their page for someone logged in, if a module gives one (as the console names them). The
 * name alone is drawn on the server and while it is read who is logged in: the link comes after, in the browser
 * (`inBrowser`), so that nothing waits under the boundary of the part it is in
 */
export function UserName(props: { username: string }) {
  const { userHref } = useModules();
  const inBrowser = createInBrowser();
  const plain = () => <span data-testid="compare-user">{props.username}</span>;
  return (
    // (no boundary of its own on the server, inside the section's: one nested there hydrated wrongly before, as
    // "Similar" found. Reading who is logged in may wait, so in the browser it has one)
    <Show when={inBrowser()} fallback={plain()}>
      <Loading fallback={plain()}>
        <Show when={userIsLoggedIn() && userHref(props.username)} fallback={plain()}>
          {(href) => (
            <a href={href()} class="underline-offset-2 hover:text-slate-800 hover:underline" data-testid="compare-user">
              {props.username}
            </a>
          )}
        </Show>
      </Loading>
    </Show>
  );
}

/** An entity of an answer as a chip: a link to its page where its class was read, else the chip alone */
export function EntityReference(props: { entity: EntityChip }) {
  const ReferenceChip = useComponent("ReferenceChip");
  return (
    <ReferenceChip
      type={props.entity.type ?? ""}
      label={props.entity.label ?? props.entity.id}
      href={entityHref(props.entity)}
    />
  );
}

/** "According to" and the chip of each entity whose claim a statement is (none: nothing) */
export function Sources(props: { sources: readonly EntityChip[] }) {
  const { t } = useTranslations();
  return (
    <Show when={props.sources.length > 0}>
      <span class="flex flex-wrap items-center gap-2" data-testid="compare-source">
        <span class={frame}>{t("compare_according_to", "according to")}</span>
        <For each={props.sources}>{(source) => <EntityReference entity={source} />}</For>
      </span>
    </Show>
  );
}
