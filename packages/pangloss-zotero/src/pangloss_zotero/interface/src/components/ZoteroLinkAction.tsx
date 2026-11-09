import { ApiError, buttonClass, ConsoleButton, getItem, Modal, useApi, useComponent, userIsLoggedIn, useToasts, useTranslations } from "@pangloss/interface-core";
import type { ConsoleActionProps } from "@pangloss/interface-core";
import { revalidate, useNavigate } from "@solidjs/router";
import { createMemo, createSignal, refresh, Show, untrack } from "solid-js";
import { getClasses, linkItem, unlinkItem } from "../api";
import type { Summary } from "../api";
import { ItemPicker, ZoteroIcon } from "./ItemPicker";

const reasonOf = (error: unknown) =>
  error instanceof ApiError ? error.detail : error instanceof Error ? error.message : String(error);

const pageOf = (item: { type: string; id: string }) =>
  `/${encodeURIComponent(item.type)}/${encodeURIComponent(item.id)}`;

/** The buttons of one item, which is of a class an item can be made into */
function Linker(props: { type: string; id: string; page: "item" | "edit"; fallback: string }) {
  const api = useApi();
  const toasts = useToasts();
  const navigate = useNavigate();
  const { t } = useTranslations();
  const ReferenceChip = useComponent("ReferenceChip");
  const type = untrack(() => props.type);
  const id = untrack(() => props.id);
  const item = createMemo(() => getItem(api, type, id) as Promise<Record<string, unknown>>);
  const linked = () => item().zoteroUrl as string | null | undefined;
  const [picking, setPicking] = createSignal(false);
  const [unlinking, setUnlinking] = createSignal(false);
  const [busy, setBusy] = createSignal(false);
  // (on the form, what has not been saved is lost: the item is read again)
  const lost = () =>
    props.page === "edit" ? t("zotero_unsaved_lost", "Changes in the form that are not saved are lost.") : undefined;

  const done = (kept: { type: string; id: string }) => {
    void revalidate();
    refresh(item);
    // (the node that is the item may be another one, after a merge; and a form is read again)
    if (kept.id !== id || untrack(() => props.page) === "edit") navigate(pageOf(kept));
  };

  const link = async (address: string) => {
    setBusy(true);
    try {
      const kept = await linkItem(api, type, id, address);
      setPicking(false);
      toasts?.show(t("zotero_linked", "Linked to the Zotero item"), "success");
      done(kept);
    } catch (error) {
      toasts?.show(t("zotero_link_refused", "Not linked: {reason}", { reason: reasonOf(error) }), "error");
    } finally {
      setBusy(false);
    }
  };
  const pick = async (picked: Summary) => {
    try {
      const found = (await getItem(api, untrack(() => props.fallback), picked.id)) as Record<string, unknown>;
      await link(String(found.zoteroUrl));
    } catch (error) {
      toasts?.show(t("zotero_link_refused", "Not linked: {reason}", { reason: reasonOf(error) }), "error");
    }
  };
  const unlink = async () => {
    setBusy(true);
    try {
      const again = await unlinkItem(api, type, id);
      setUnlinking(false);
      toasts?.show(
        t("zotero_unlinked", "Unlinked: the Zotero item is “{label}” again", { label: again.label }),
        "success",
      );
      done({ type, id });
    } catch (error) {
      toasts?.show(t("zotero_unlink_refused", "Not unlinked: {reason}", { reason: reasonOf(error) }), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Show
        when={linked()}
        fallback={
          <ConsoleButton label={t("zotero_link", "Link to Zotero")} text onClick={() => setPicking(true)}>
            <span class="flex" data-testid="zotero-link">
              <ZoteroIcon />
            </span>
          </ConsoleButton>
        }
      >
        <ConsoleButton label={t("zotero_unlink", "Unlink from Zotero")} text onClick={() => setUnlinking(true)}>
          <span class="flex" data-testid="zotero-unlink">
            <ZoteroIcon />
          </span>
        </ConsoleButton>
      </Show>
      <Show when={picking()}>
        <ItemPicker
          title={t("zotero_link_title", "Link to an item of the Zotero library")}
          note={[
            t(
              "zotero_link_note",
              "This takes the item's fields and address. If the item is already in the database, the two become one: the one that something refers to is kept.",
            ),
            lost(),
          ]
            .filter(Boolean)
            .join(" ")}
          fallback={props.fallback}
          onPick={(picked) => void pick(picked)}
          onAddress={(address) => void link(address)}
          onClose={() => setPicking(false)}
        />
      </Show>
      <Show when={unlinking()}>
        <Modal title={t("zotero_unlink_title", "Unlink from the Zotero item?")} onClose={() => setUnlinking(false)}>
          <div class="flex flex-col gap-4 p-4 text-sm" data-testid="zotero-unlink-dialog">
            <div class="flex items-center gap-2">
              <ReferenceChip type={type} label={String(item().label ?? "")} href={pageOf({ type, id })} />
            </div>
            <p class="text-slate-600">
              {t(
                "zotero_unlink_note",
                "This keeps its own fields and what refers to it, and loses the Zotero fields. The item becomes an entry of its own again.",
              )}{" "}
              {lost()}
            </p>
            <div class="flex justify-end gap-2">
              <button type="button" class={buttonClass("ordinary", "md")} onClick={() => setUnlinking(false)}>
                {t("cancel", "Cancel")}
              </button>
              <button type="button" class={buttonClass("danger", "md")} disabled={busy()} onClick={() => void unlink()}>
                {t("zotero_unlink", "Unlink from Zotero")}
              </button>
            </div>
          </div>
        </Modal>
      </Show>
    </>
  );
}

/**
 * *Link to Zotero* and *Unlink* in the console of an item of a class that an item can be made into (a `consoleActions`
 * entry), for someone logged in. Linking takes an item of the library (merging with its node, if it has one);
 * unlinking takes it off again.
 */
export default function ZoteroLinkAction(props: ConsoleActionProps) {
  const api = useApi();
  const classes = createMemo(() => getClasses(api));
  return (
    <Show when={userIsLoggedIn() && classes().targets.includes(props.type)}>
      <Linker type={props.type} id={props.id} page={props.page} fallback={classes().fallback} />
    </Show>
  );
}
