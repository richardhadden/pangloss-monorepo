import { buttonClass, useApi, useComponent, useToasts, useTranslations } from "@pangloss/interface-core";
import { revalidate } from "@solidjs/router";
import { createSignal, Show, untrack } from "solid-js";
import { hrefOf, reasonOf, resolveDescription } from "../api";
import type { Candidate } from "../api";
import { CandidatePages } from "./Candidates";

export interface ResolveDialogProps {
  /** The id of the description (its `MatchesCriteria`) */
  id: string;
  /** How many places of its document are the same one (`sameOne`), if known */
  places?: number | null;
  /** Whether it has a mark (`sameOne`): it may be one of several places of the same one */
  marked?: boolean;
  onClose: () => void;
}

/**
 * "This is…": the candidates of a description, each with "This is the one"; the one chosen is asked about once, and
 * then put in the description's place (`POST /api/criteria/{id}/resolve`: an update of its document, by the user, in
 * which the criteria stay in the document's history). Then the page reads its item again, and shows the entity where
 * the card was. A description that is one of several places of the same one says that the entity is put in all of
 * them (the server fills every place of its mark). (Fetched when it is first opened: only someone logged in has the
 * button)
 */
export default function ResolveDialog(props: ResolveDialogProps) {
  const Modal = useComponent("Modal");
  const ReferenceChip = useComponent("ReferenceChip");
  const api = useApi();
  const toasts = useToasts();
  const { t } = useTranslations();
  const [chosen, setChosen] = createSignal<Candidate>();
  const [busy, setBusy] = createSignal(false);
  // (several places: how many, if known; with a mark and no count, "every place")
  const several = () => (props.places ?? 0) > 1 || (props.marked === true && (props.places ?? null) === null);
  const allPlaces = () =>
    (props.places ?? 0) > 1
      ? t("criteria_resolve_all_places", "It is put in all {count} places of this document that are the same one.", {
          count: String(props.places),
        })
      : t("criteria_resolve_every_place", "It is put in every place of this document that is the same one.");
  const confirm = async () => {
    const candidate = untrack(chosen);
    if (!candidate) return;
    setBusy(true);
    try {
      await resolveDescription(api, props.id, candidate);
    } catch (error) {
      console.error(error);
      setBusy(false);
      toasts?.show(t("criteria_resolve_refused", "Not resolved: {reason}", { reason: reasonOf(error) }), "error");
      return;
    }
    const label = candidate.label ?? candidate.id;
    toasts?.show(
      (props.places ?? 0) > 1
        ? t("criteria_resolved_places", "{label} is now in the {count} places of the description", { label, count: String(props.places) })
        : t("criteria_resolved", "{label} is now in the place of the description", { label }),
      "success",
    );
    props.onClose();
    // (the item's page reads it again: the entity is shown where the card was)
    void revalidate();
  };
  return (
    <Modal title={t("criteria_this_is", "This is…")} onClose={props.onClose} size="lg">
      <div class="flex min-h-0 flex-col gap-4 overflow-y-auto p-4" data-testid="criteria-resolve-dialog">
        <Show
          when={chosen()}
          fallback={
            <>
              <p class="text-sm text-slate-600">
                {t(
                  "criteria_this_is_help",
                  "Who it is: the one chosen takes the place of the description, and the document is saved as a new version. The criteria stay in its history.",
                )}
              </p>
              <Show when={several()}>
                <p class="text-sm text-slate-700" data-testid="criteria-resolve-places">
                  {allPlaces()}
                </p>
              </Show>
              <CandidatePages
                id={props.id}
                empty={t("criteria_no_candidates_to_choose", "There are no candidates to choose from")}
                action={(candidate) => (
                  <button type="button" class={buttonClass("ordinary")} onClick={() => setChosen(candidate)}>
                    {t("criteria_this_is_the_one", "This is the one")}
                  </button>
                )}
              />
              <div class="flex justify-end">
                <button type="button" class={buttonClass("ordinary", "md")} onClick={() => props.onClose()}>
                  {t("cancel", "Cancel")}
                </button>
              </div>
            </>
          }
        >
          {(candidate) => (
            <div class="flex flex-col gap-4" data-testid="criteria-resolve-confirm">
              <p class="text-sm text-slate-700">
                {t("criteria_resolve_question", "Put this one in the place of the description, and save the document?")}
              </p>
              <Show when={several()}>
                <p class="text-sm text-slate-700" data-testid="criteria-resolve-places">
                  {allPlaces()}
                </p>
              </Show>
              <span>
                <ReferenceChip
                  type={candidate().type}
                  label={candidate().label ?? candidate().id}
                  href={hrefOf(candidate())}
                />
              </span>
              <div class="flex justify-end gap-2">
                <button type="button" class={buttonClass("ordinary", "md")} disabled={busy()} onClick={() => setChosen(undefined)}>
                  {t("back", "Back")}
                </button>
                <button
                  type="button"
                  class={buttonClass("primary", "md")}
                  disabled={busy()}
                  data-testid="criteria-resolve-submit"
                  onClick={() => void confirm()}
                >
                  {t("criteria_resolve", "Put in its place")}
                </button>
              </div>
            </div>
          )}
        </Show>
      </div>
    </Modal>
  );
}
