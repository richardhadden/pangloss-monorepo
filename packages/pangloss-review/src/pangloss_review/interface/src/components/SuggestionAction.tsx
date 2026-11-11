import { useApi, useItemForm, useModels, userIsLoggedIn, useToasts, useTranslations } from "@pangloss/interface-core";
import type { PartActionProps } from "@pangloss/interface-core";
import { createSignal, lazy, Loading, Show } from "solid-js";
import { getMentionsOfSuggestion, getSimilarSuggestions, getSuggestion, giveIdentification } from "../api";
import { isSuggestion, UNRECONCILED } from "../parts";
import { candidatesIn, confirmedPart, entityInPlace, fresh, partAt, pathOf, strangers } from "./confirming";
import type { Asked } from "./confirming";
import { reasonOf, TickIcon } from "./taskIcons";

// (the dialog's code is fetched when it is first opened)
const ConfirmDialog = lazy(() => import("./ConfirmDialog"));

// (yellow: something that waits for a person)
const WAITING = "bg-yellow-300 text-yellow-950 hover:bg-yellow-400";
const WORDS = "shrink-0 cursor-pointer items-center gap-1.5 text-xs font-semibold whitespace-nowrap uppercase select-none";
const LOOKS = {
  // (the first thing in the part's head bar, after its type, and said in words: at the other end from cut, copy and
  // remove, so that it is neither pressed for one of them nor one of them for it)
  bar: `flex border-r-[0.5px] border-slate-400/70 px-3 ${WORDS} ${WAITING}`,
  // (in a line with chips, where the part has no bar)
  inline: `inline-flex h-6 rounded-xs border-[0.5px] border-slate-400/70 px-2 ${WORDS} ${WAITING}`,
};

/**
 * Confirms an identification that a toolchain suggested, in the form of its document, as an edit of the form like
 * any other: the part becomes an identification, whatever else has been changed, and is saved with the rest (the
 * server then says who identified it, and gives the URIs). So someone working through a document confirms each as
 * they reach it. A click does it at once, unless there is something to ask first, which a dialog does:
 *
 * - it would give URIs to someone (one candidate, and URIs: the wrong person would be easy to miss), or someone else
 *   has those URIs already;
 * - other parts are of the same person and could be done with it: suggestions that name a URI it names or have the
 *   same candidates, and unreconciled mentions that name its URI.
 *
 * Of those, the ones in this document are in the form too, and are changed there with it; the ones in other
 * documents are done by the server, at once and in the background.
 */
function ConfirmButton(props: {
  id: string;
  look: keyof typeof LOOKS;
  item: Record<string, unknown>;
  replace: (next: Record<string, unknown>) => void;
}) {
  const api = useApi();
  const toasts = useToasts();
  const definitions = useModels();
  const form = useItemForm();
  const { t } = useTranslations();
  const [asked, setAsked] = createSignal<Asked>();
  const [busy, setBusy] = createSignal(false);
  const refused = (error: unknown) => {
    console.error(error);
    toasts?.show(t("review_confirm_refused", "Not confirmed: {reason}", { reason: reasonOf(error) }), "error");
    return undefined;
  };
  const confirm = (found: Asked, also: string[], mentions: string[]) => {
    const target = props.item.target;
    const one = found.suggestion.candidates.length === 1 ? found.suggestion.candidates[0] : undefined;
    const ticked = <T extends { id: string; inForm: boolean }>(rows: T[], ids: string[], inForm: boolean) =>
      rows.filter((row) => row.inForm === inForm && ids.includes(row.id));
    // (the others in other documents first, with what this one holds while it still holds it)
    const elsewhere = ticked(found.similar, also, false).map((row) => row.id);
    const mentioned = one ? ticked(found.mentions, mentions, false).map((row) => row.id) : [];
    const others =
      elsewhere.length + mentioned.length > 0
        ? giveIdentification(api, props.id, elsewhere, target, mentioned, one).catch(refused)
        : Promise.resolve(undefined);
    // (those of this document, in the form: found as it is now, before anything of it is changed)
    const root = form.plain();
    let here = 0;
    for (const row of ticked(found.similar, also, true)) {
      const path = pathOf(root, row.id);
      const part = path && partAt(root, path);
      if (!path || !part || !isSuggestion(definitions, String(part.type))) continue;
      const given = { ...part, target: fresh(definitions, target) };
      form.set(path, confirmedPart(definitions, given, row.becomes ?? "Identification"));
      here += 1;
    }
    for (const row of one ? ticked(found.mentions, mentions, true) : []) {
      const path = pathOf(root, row.id);
      const part = path && partAt(root, path);
      if (!path || !part || part.type !== UNRECONCILED || !one) continue;
      form.set(path, entityInPlace(part, one));
      here += 1;
    }
    props.replace(confirmedPart(definitions, props.item, found.suggestion.becomes ?? "Identification"));
    setAsked(undefined);
    toasts?.show(t("review_confirmed_in_form", "Confirmed: it is saved with the document"));
    if (here > 0)
      toasts?.show(
        t("review_done_in_form", "{count} more in this document are done with it", { count: String(here) }),
      );
    void others.then((given) => {
      if (given && given.queued > 0)
        toasts?.show(
          t("review_given_to_others", "{count} more are being given the same, in the background", {
            count: String(given.queued),
          }),
        );
    });
  };
  const press = () => {
    setBusy(true);
    Promise.all([
      getSuggestion(api, props.id),
      getSimilarSuggestions(api, props.id),
      getMentionsOfSuggestion(api, props.id),
    ])
      .then(([saved, similar, mentions]) => {
        // (who it could be is what the form says now; the URIs are those that are saved, which the server gives)
        const suggestion = { ...saved, candidates: candidatesIn(definitions, props.item) };
        const root = form.plain();
        // (one of this document counts while the form still has it as it was: not one confirmed or taken out there)
        const still = (id: string, is: (type: string) => boolean) => {
          const path = pathOf(root, id);
          const part = path && partAt(root, path);
          return !!part && is(String(part.type));
        };
        const found: Asked = {
          suggestion,
          similar: similar
            .map((row) => ({ ...row, inForm: row.head.id === saved.head.id }))
            .filter((row) => !row.inForm || still(row.id, (type) => isSuggestion(definitions, type))),
          // (a mention is reconciled with the one it is of: with several candidates there is no one)
          mentions:
            suggestion.candidates.length === 1
              ? mentions
                  .map((row) => ({ ...row, inForm: row.head.id === saved.head.id }))
                  .filter((row) => !row.inForm || still(row.id, (type) => type === UNRECONCILED))
              : [],
        };
        const givesUris = suggestion.uris.length > 0 && suggestion.candidates.length === 1;
        if (givesUris || found.similar.length > 0 || found.mentions.length > 0 || strangers(suggestion).length > 0)
          setAsked(found);
        else confirm(found, [], []);
      })
      .catch((error: unknown) => {
        // (not in the saved document: made in this form, which a toolchain's suggestion is not)
        console.error(error);
        toasts?.show(
          t("review_not_saved", "This is not in the saved document (any more). Save the document first."),
          "error",
        );
      })
      .finally(() => setBusy(false));
  };
  return (
    <>
      <button
        type="button"
        class={LOOKS[props.look]}
        title={t("review_confirm_hint", "Confirm this identification as your own")}
        disabled={busy()}
        data-testid="confirm-button"
        onClick={press}
      >
        <TickIcon />
        {t("review_confirm_identification", "Confirm identification")}
      </button>
      <Show when={asked()}>
        {(found) => (
          <Loading fallback={null}>
            <ConfirmDialog
              asked={found()}
              onClose={() => setAsked(undefined)}
              onConfirm={(also, mentions) => confirm(found(), also, mentions)}
            />
          </Loading>
        )}
      </Show>
    </>
  );
}

/**
 * On an identification that a toolchain suggested (`partActions`), in the form that edits its document, for someone
 * logged in: a yellow button at the start of its bar, "Confirm identification", which confirms it.
 */
export function SuggestionAction(props: PartActionProps) {
  const definitions = useModels();
  // (in the form only: it is confirmed where it can be corrected, not from a page that is read)
  const found = () =>
    props.page === "edit" &&
    props.place !== "body" &&
    props.replace &&
    isSuggestion(definitions, props.type) &&
    typeof props.item.id === "string"
      ? { id: props.item.id, replace: props.replace, look: props.place }
      : undefined;
  return (
    <Show when={found()}>
      {(part) => (
        // (who is logged in may still be being read)
        <Loading fallback={null}>
          <Show when={userIsLoggedIn()}>
            <ConfirmButton id={part().id} look={part().look} item={props.item} replace={part().replace} />
          </Show>
        </Loading>
      )}
    </Show>
  );
}
