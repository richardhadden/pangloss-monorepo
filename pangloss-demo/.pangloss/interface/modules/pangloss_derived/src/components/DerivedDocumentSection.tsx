import { createMemo, For, Loading, refresh, Show } from "solid-js";
import { buttonClass, SectionBar, useApi, useComponent, userIsLoggedIn, useToasts, useTranslations } from "@pangloss/interface-core";
import type { ItemSectionProps } from "@pangloss/interface-core";
import { clearContext, getWhy } from "../api";
import type { Why } from "../api";

/**
 * Why a document is there (a section after an item's contents): the rule that made it, what it rests on, what the
 * derivation passed through; for a derived document, a way to make it one's own; for a document someone made their
 * own, that, and whether the derivation it was made from still holds. Nothing for a document no rule made.
 */
export default function DerivedDocumentSection(props: ItemSectionProps) {
  const api = useApi();
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, modelName } = useTranslations();
  // (not for a document inside another, or an entity: only a head document can be derived; a head's meta names itself)
  const why = createMemo((): Promise<Why | null> => {
    const meta = props.item.meta as Record<string, unknown> | undefined;
    const asked = props.model.kind === "Document" && !!meta && (!meta.headNodeId || meta.headNodeId === props.id);
    return asked ? getWhy(api, props.type, props.id).catch(() => null) : Promise.resolve(null);
  });
  const toasts = useToasts();
  // (the author says that the document no longer rests on the derivation: what that passed through goes)
  const clear = () =>
    clearContext(api, props.type, props.id)
      .then(() => void refresh(why))
      .catch((error: unknown) => {
        console.error(error);
        toasts?.show(t("derived_clear_refused", "Not cleared"), "error");
      });
  return (
    <Loading>
      <Show when={why()}>
        {(found) => (
          <section data-testid="derived-why">
            <SectionBar>
              {found().converted ? t("derived_converted", "Made from a derivation") : t("derived_made_by", "Derived")}
            </SectionBar>
            <p class="mb-3 text-sm text-slate-600">
              {found().converted
                ? t("derived_converted_note", "This was a derived document, made by the rule {rule}; it is now this document's own, and the rule no longer writes it.", { rule: found().rule })
                : t("derived_made_note", "Made by the rule {rule}, from the documents below. It follows them: it is not edited by hand.", { rule: found().rule })}
            </p>
            <Show when={found().converted && !found().holds}>
              <p class="mb-3 text-sm font-semibold text-amber-700" data-testid="derived-lost">
                {t("derived_lost", "The derivation it was made from no longer holds.")}
              </p>
            </Show>
            <Show when={found().context.length > 0}>
              <p class="mb-3 flex flex-wrap items-center gap-2 text-sm text-slate-600" data-testid="derived-context">
                <span>
                  {t("derived_through", "Through: {labels}", { labels: found().context.map((c) => modelName(c)).join(", ") })}
                </span>
                <Show when={found().converted && userIsLoggedIn()}>
                  <button
                    type="button"
                    class={buttonClass("ordinary", "sm")}
                    title={t("derived_clear_help", "Say that this document no longer rests on the derivation: rules and searches then read it as plain")}
                    data-testid="derived-clear-context"
                    onClick={() => void clear()}
                  >
                    {t("derived_clear", "Clear")}
                  </button>
                </Show>
              </p>
            </Show>
            <div class="flex flex-wrap items-center gap-2">
              <For each={found().sources}>
                {(source) => (
                  <ReferenceChip
                    type={source.headType ?? source.type}
                    label={source.headLabel ?? source.label}
                    href={`/${encodeURIComponent(source.headType ?? source.type)}/${encodeURIComponent(source.headId ?? source.id)}${source.headId && source.headId !== source.id ? `?show=${encodeURIComponent(source.id)}` : ""}`}
                  />
                )}
              </For>
              <Show when={found().hiddenSources > 0}>
                <span class="text-sm text-slate-500">
                  {t("derived_more", "and {count} more", { count: found().hiddenSources })}
                </span>
              </Show>
            </div>
            <Show when={userIsLoggedIn() && !found().converted && found().convertsTo.length > 0}>
              <div class="mt-4 flex flex-wrap gap-2">
                <For each={found().convertsTo}>
                  {(to) => (
                    <a
                      href={`/derived/convert/${encodeURIComponent(props.type)}/${encodeURIComponent(props.id)}/${encodeURIComponent(to)}`}
                      class={buttonClass("ordinary", "sm")}
                      data-testid="derived-convert"
                    >
                      {t("derived_convert", "Make it my own: {type}", { type: modelName(to) })}
                    </a>
                  )}
                </For>
              </div>
            </Show>
          </section>
        )}
      </Show>
    </Loading>
  );
}
