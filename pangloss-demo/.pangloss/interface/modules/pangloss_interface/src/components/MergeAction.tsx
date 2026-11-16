import {
  ConsoleButton,
  EntityPicker,
  Modal,
  useApi,
  useModels,
  useTranslations,
  userIsLoggedIn,
} from "@pangloss/interface-core";
import type { ConsoleActionProps } from "@pangloss/interface-core";
import { useNavigate } from "@solidjs/router";
import { createSignal, For, Show, untrack } from "solid-js";
import { compareHref, mergeHref, mergesOf } from "../api";
import type { MergeRecord } from "../api";
import { mergeableTypes } from "../compare";
import { Heading, MergeIcon, Pair, StateBadge } from "./parts";

/** The button and its dialog, of one entity */
function Merge(props: { type: string; id: string }) {
  const api = useApi();
  const definitions = useModels();
  const navigate = useNavigate();
  const { t } = useTranslations();
  const type = untrack(() => props.type);
  const id = untrack(() => props.id);
  const [open, setOpen] = createSignal(false);
  // (the merges it is part of: read when the dialog opens; undefined until then)
  const [merges, setMerges] = createSignal<MergeRecord[]>();
  const [same, setSame] = createSignal(false);
  const show = () => {
    setSame(false);
    setOpen(true);
    mergesOf(api, type, id)
      .then(setMerges)
      .catch((error) => {
        console.error(error);
        setMerges([]);
      });
  };
  return (
    <>
      <ConsoleButton label={t("merge_button", "Merge with…")} onClick={show}>
        <span class="flex" data-testid="merge-button">
          <MergeIcon />
        </span>
      </ConsoleButton>
      <Show when={open()}>
        <Modal title={t("merge_dialog_title", "Merge with another that is the same")} onClose={() => setOpen(false)} size="lg">
          {/* (room under the box for the list of what it finds) */}
          <div class="flex min-h-96 flex-col gap-3 p-4 text-sm" data-testid="merge-dialog">
            <p>
              {t(
                "merge_dialog_help",
                "Find the one this is a duplicate of. The two are then shown side by side, before anything is changed.",
              )}
            </p>
            <EntityPicker
              types={mergeableTypes(definitions, type)}
              onPick={(entity) => {
                if (entity.id === id) {
                  setSame(true);
                  return;
                }
                setOpen(false);
                navigate(compareHref(type, id, entity.id));
              }}
            />
            <Show when={same()}>
              <p class="text-xs text-red-800" role="alert">
                {t("merge_dialog_same", "That is this one: choose another.")}
              </p>
            </Show>
            <Show when={(merges() ?? []).length > 0}>
              <Heading>{t("merge_dialog_merges", "Its merges")}</Heading>
              <ul class="flex flex-col gap-2" data-testid="merge-dialog-merges">
                <For each={merges()}>
                  {(record) => (
                    <li class="flex flex-wrap items-center gap-3">
                      <StateBadge record={record} />
                      <Pair record={record} />
                      <a class="text-xs font-semibold text-slate-600 uppercase hover:underline" href={mergeHref(record.id)}>
                        {t("merges_open", "Look at it")}
                      </a>
                    </li>
                  )}
                </For>
              </ul>
            </Show>
          </div>
        </Modal>
      </Show>
    </>
  );
}

/**
 * "Merge with…" in the console of an entity's page (a `consoleActions` entry): a dialog that finds the other entity
 * and goes to the comparison of the two, and lists the merges this one is part of. For someone logged in, on the
 * item's page only, and for entities: a document is not merged.
 */
export default function MergeAction(props: ConsoleActionProps) {
  return (
    <Show when={props.page === "item" && props.model.kind === "Entity" && userIsLoggedIn()}>
      <Show when={props.id} keyed>
        {(id) => <Merge type={props.type} id={id} />}
      </Show>
    </Show>
  );
}
