import { buttonClass, Modal, useComponent, useTranslations } from "@pangloss/interface-core";
import { createSignal, For, Show } from "solid-js";
import { strangers } from "./confirming";
import type { Asked } from "./confirming";
import { hrefOf, TickIcon } from "./taskIcons";
import { MentionWhere, Offered, RowNotes, SuggestionWhere } from "./where";

interface DialogProps {
  asked: Asked;
  /** Confirm it in the form, and with it the suggestions and the mentions named */
  onConfirm: (also: string[], mentions: string[]) => void;
  onClose: () => void;
}

const WARNING = "flex flex-col gap-2 rounded-xs border-[0.5px] border-yellow-500 bg-yellow-100 p-3 text-sm text-yellow-950";

function Contents(props: DialogProps) {
  const { t } = useTranslations();
  const ReferenceChip = useComponent("ReferenceChip");
  const suggestion = () => props.asked.suggestion;
  const similar = () => props.asked.similar;
  const mentions = () => props.asked.mentions;
  // (the boxes as the reader left them: one not touched is ticked if it names the same URI, which says it is the
  // same person; one that only has the same candidates is for the reader to tick)
  const [toggled, setToggled] = createSignal<Record<string, boolean>>({});
  const chosen = (row: { id: string; sameUri?: boolean }, byUri = !!row.sameUri) => toggled()[row.id] ?? byUri;
  const toggle = (rows: { id: string }[], on: boolean) =>
    setToggled({ ...toggled(), ...Object.fromEntries(rows.map((row) => [row.id, on])) });
  // (the toolchain, and which version of it)
  const suggestedBy = () => [suggestion().identifiedBy, suggestion().toolchainVersion].filter(Boolean).join(" ");
  const confirm = () =>
    props.onConfirm(
      similar()
        .filter((row) => chosen(row))
        .map((row) => row.id),
      mentions()
        .filter((row) => chosen(row, true))
        .map((row) => row.id),
    );
  // (the one who takes the URIs, where confirming gives them)
  const taker = () =>
    suggestion().uris.length > 0 && suggestion().candidates.length === 1 ? suggestion().candidates[0] : undefined;
  return (
    <div class="flex min-w-0 flex-col gap-4" data-testid="confirm-panel">
      <SuggestionWhere suggestion={suggestion()} />
      <p class="text-sm text-slate-600">
        <Show
          when={suggestedBy()}
          fallback={t("review_confirm_help", "Confirming says that you have checked it: it becomes your identification.")}
        >
          {t(
            "review_confirm_help_by",
            "Suggested by {toolchain}. Confirming says that you have checked it: it becomes your identification.",
            { toolchain: suggestedBy() },
          )}
        </Show>
      </p>
      <Show when={strangers(suggestion()).length > 0}>
        {/* (the URIs are someone's already, and not a candidate's: one of the two is wrong) */}
        <div class={WARNING} role="alert" data-testid="confirm-uri-known">
          <p class="font-semibold">
            {t("review_uri_known", "Its URI is already that of someone who is not among the candidates:")}
          </p>
          <span class="flex flex-wrap gap-2">
            <For each={strangers(suggestion())}>
              {(known) => <ReferenceChip type={known.type} label={known.label ?? known.id} href={hrefOf(known)} />}
            </For>
          </span>
        </div>
      </Show>
      <Show when={taker()}>
        {(candidate) => (
          // (asked about plainly: URIs given to the wrong person are not easily seen afterwards)
          <div class={WARNING} role="alert" data-testid="confirm-uris-warning">
            <p class="font-semibold">
              {t(
                "review_uris_warning",
                "Confirming gives these URIs to this one, when the document is saved. Check that it is the right one.",
              )}
            </p>
            <span>
              <ReferenceChip type={candidate().type} label={candidate().label ?? candidate().id} href={hrefOf(candidate())} />
            </span>
            <ul class="flex flex-col gap-0.5 text-xs break-all" data-testid="confirm-uris">
              <For each={suggestion().uris}>{(uri) => <li>{uri}</li>}</For>
            </ul>
          </div>
        )}
      </Show>
      <Show when={suggestion().uris.length > 0 && !taker()}>
        <p class="text-xs break-all text-slate-600" data-testid="confirm-uris">
          {t("review_uris_not_given", "URIs (given only when there is one candidate): {uris}", {
            uris: suggestion().uris.join(", "),
          })}
        </p>
      </Show>
      <Show
        when={similar().length > 0}
        fallback={
          <p class="py-2 text-sm text-slate-500" data-testid="confirm-no-similar">
            {t("review_similar_suggestions_none", "No other suggestion says the same")}
          </p>
        }
      >
        <p class="text-sm text-slate-600">
          {t(
            "review_similar_suggestions_help",
            "These are of the same person: they name the same URI (ticked), or suggest the same candidates, about as likely. Those ticked are given the same identification: in this document with it, in others now, in the background.",
          )}
        </p>
        <Offered
          rows={similar()}
          heading={t("review_suggestion", "Suggestion")}
          testid="confirm-similar"
          chosen={(row) => chosen(row)}
          onToggle={toggle}
        >
          {(row) => (
            <>
              <SuggestionWhere suggestion={row} />
              <RowNotes sameUri={row.sameUri} inForm={row.inForm} />
            </>
          )}
        </Offered>
      </Show>
      <Show when={mentions().length > 0 && suggestion().candidates[0]}>
        {(one) => (
          <>
            <p class="text-sm text-slate-600">
              {t(
                "review_same_uri_mentions_help",
                "These unreconciled mentions name the same URI. Those ticked are reconciled with {label}.",
                { label: one().label ?? one().id },
              )}
            </p>
            <Offered
              rows={mentions()}
              heading={t("review_mention", "Mention")}
              testid="confirm-mentions"
              chosen={(row) => chosen(row, true)}
              onToggle={toggle}
            >
              {(row) => (
                <>
                  <MentionWhere mention={row} />
                  <RowNotes sameUri inForm={row.inForm} />
                </>
              )}
            </Offered>
          </>
        )}
      </Show>
      <div class="flex justify-end gap-2">
        <button type="button" class={buttonClass("ordinary", "md")} onClick={props.onClose}>
          {t("cancel", "Cancel")}
        </button>
        <button type="button" class={buttonClass("primary", "md")} data-testid="confirm-submit" onClick={confirm}>
          <TickIcon />
          {t("review_confirm", "Confirm")}
        </button>
      </div>
    </div>
  );
}

/**
 * Confirming an identification that a toolchain suggested in a form, where there is something to ask first: what it
 * says, who would be given its URIs, and the other parts that are of the same person
 */
export default function ConfirmDialog(props: DialogProps) {
  const { t } = useTranslations();
  return (
    <Modal title={t("review_confirm_title", "Confirm an identification")} onClose={props.onClose} size="lg">
      <div class="overflow-y-auto p-4" data-testid="confirm-dialog">
        <Contents {...props} />
      </div>
    </Modal>
  );
}
