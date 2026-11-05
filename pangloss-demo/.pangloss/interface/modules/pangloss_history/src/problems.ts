import { useTranslations } from "@pangloss/interface-core";
import type { Problem } from "./api";

/** The last name in a path of the stored version (`action.carried_out_by[0]` → `carried_out_by`) */
function lastField(path: string | null | undefined): string | undefined {
  return path
    ?.split(".")
    .map((part) => part.replace(/\[\d+\]$/, ""))
    .filter((part) => part !== "" && !/^\d+$/.test(part))
    .at(-1);
}

/** One line of the notice: the problems of one kind (and blocking or not), said once, naming all their fields */
export interface ProblemLine {
  text: string;
  blocking: boolean;
  /** The messages of the API, for a developer (a tooltip) */
  details: string[];
}

// What a kind says of one name and of several (`{field}`, `{fields}`: quoted, joined as the language joins a list).
// A kind that names nothing says `none`
const SENTENCES: Record<string, { one: [string, string]; many: [string, string]; none?: [string, string] }> = {
  "removed-field": {
    one: ["history_problem_removed_field", "{field} is no longer part of this record, so its old value isn't shown here."],
    many: ["history_problem_removed_fields", "{fields} are no longer part of this record, so their old values aren't shown here."],
  },
  "missing-required": {
    one: ["history_problem_missing_required", "{field} is now required, but this version has nothing in it."],
    many: ["history_problem_missing_required_many", "{fields} are now required, but this version has nothing in them."],
  },
  "model-removed": {
    one: ["history_problem_model_removed", "Records of the kind {field} no longer exist, so this part can't be brought back."],
    many: ["history_problem_models_removed", "Records of the kinds {fields} no longer exist, so these parts can't be brought back."],
  },
  "type-changed": {
    one: ["history_problem_type_changed", "{field} now holds a different kind of value, and the old one doesn't fit it."],
    many: ["history_problem_types_changed", "{fields} now hold different kinds of value, and the old ones don't fit."],
  },
  "reference-not-allowed": {
    one: ["history_problem_reference_not_allowed", "{field} links to something it is no longer allowed to link to."],
    many: ["history_problem_references_not_allowed", "{fields} link to things they are no longer allowed to link to."],
  },
  "cardinality-changed": {
    one: ["history_problem_cardinality_changed", "{field} now takes only one value, but this version has several."],
    many: ["history_problem_cardinalities_changed", "{fields} now take only one value each, but this version has several."],
  },
  validation: {
    one: ["history_problem_validation", "{field} doesn't have a value that would be accepted today."],
    many: ["history_problem_validations", "{fields} don't have values that would be accepted today."],
    none: ["history_problem_validation_none", "Some of it wouldn't be accepted today."],
  },
  "unsupported-change": {
    one: ["history_problem_unsupported", "{field} was changed in a way that can't yet be applied to old versions."],
    many: ["history_problem_unsupported_many", "{fields} were changed in a way that can't yet be applied to old versions."],
    none: ["history_problem_unsupported_none", "Since this version, the data was changed in a way that can't yet be applied to old versions."],
  },
  "hand-written-migration": {
    one: ["history_problem_hand_written", "Since this version, the data was changed in a way that can't be followed automatically, so some of it may now mean something different."],
    many: ["history_problem_hand_written", "Since this version, the data was changed in a way that can't be followed automatically, so some of it may now mean something different."],
    none: ["history_problem_hand_written", "Since this version, the data was changed in a way that can't be followed automatically, so some of it may now mean something different."],
  },
  "unknown-position": {
    one: ["history_problem_unknown_position", "It isn't known when this version was saved, so it is shown exactly as it was stored."],
    many: ["history_problem_unknown_position", "It isn't known when this version was saved, so it is shown exactly as it was stored."],
    none: ["history_problem_unknown_position", "It isn't known when this version was saved, so it is shown exactly as it was stored."],
  },
};

/**
 * The problems of a version as a person who edits would say them, not one who wrote the models: one line for each
 * kind of problem (blocking or not), naming every field it is about as the form names it, so that nothing is said
 * twice; no migration or model jargon (the API's messages are kept for a tooltip). A kind not known here is its
 * messages, each once. `type` is the item's, for a problem that names no model of its own.
 */
export function useProblemLines() {
  const { t, fieldName, modelName, language } = useTranslations();
  return (problems: Problem[], type: string): ProblemLine[] => {
    const groups = new Map<string, { kind: string; blocking: boolean; names: string[]; details: string[]; message: string }>();
    for (const problem of problems) {
      const known = problem.kind in SENTENCES;
      // (one of a kind not known here is grouped only with the same message)
      const key = `${problem.blocking}:${problem.kind}:${known ? "" : problem.message}`;
      const group =
        groups.get(key) ??
        groups.set(key, { kind: problem.kind, blocking: problem.blocking, names: [], details: [], message: problem.message }).get(key)!;
      const field = problem.field ?? lastField(problem.path);
      const name =
        problem.kind === "hand-written-migration" || problem.kind === "unknown-position"
          ? undefined
          : field
            ? fieldName(problem.model ?? type, field)
            : problem.model
              ? modelName(problem.model)
              : undefined;
      if (name !== undefined && !group.names.includes(name)) group.names.push(name);
      if (!group.details.includes(problem.message)) group.details.push(problem.message);
    }
    const list = new Intl.ListFormat(language(), { type: "conjunction" });
    return [...groups.values()].map((group) => {
      const sentences = SENTENCES[group.kind];
      const quoted = group.names.map((name) => `“${name}”`);
      let text: string;
      if (!sentences) text = group.message;
      else if (quoted.length === 0)
        text = sentences.none ? t(...sentences.none) : t(sentences.many[0], sentences.many[1], { fields: t("history_problem_some_fields", "Some fields") });
      else if (quoted.length === 1) text = t(sentences.one[0], sentences.one[1], { field: quoted[0]! });
      else text = t(sentences.many[0], sentences.many[1], { fields: list.format(quoted) });
      return { text, blocking: group.blocking, details: group.details };
    });
  };
}
