import { SectionBar, Spinner, useApi, useComponent, useTranslations } from "@pangloss/interface-core";
import type { ItemSectionProps } from "@pangloss/interface-core";
import { useSearchParams } from "@solidjs/router";
import { createMemo, createSignal, For, Loading, onSettled, Show } from "solid-js";
import { hasCluster, stepsOf } from "../identity";
import type { Ref, Steps } from "../identity";
import { ClusterWarnings, readCluster } from "./IdentityCluster";

const refHref = (ref: Ref) => `/${encodeURIComponent(ref.type)}/${encodeURIComponent(ref.id)}`;

function Included(props: { id: string; steps: Steps }) {
  const api = useApi();
  const ReferenceChip = useComponent("ReferenceChip");
  const ItemContents = useComponent("ItemContents");
  const { t } = useTranslations();
  const read = createMemo(() => readCluster(api, props.id, props.steps));
  // (what refers to each of the others is read in the browser, once the page is there: on the server it would be
  // a read that waits for the cluster, which waits for the page, and each wait is a pass more of the rendering)
  const [inBrowser, setInBrowser] = createSignal(false);
  onSettled(() => {
    setInBrowser(true);
  });
  const labelOf = (id: string) => read()?.members.find((member) => member.id === id);
  return (
    <Show when={hasCluster(read()) && read()}>
      {(cluster) => (
        <section data-testid="identity-included" data-steps={props.steps}>
          <SectionBar>{t("identity_included", "Said of the entities said to be the same")}</SectionBar>
          <p class="mb-4 text-sm text-slate-700">
            {t(
              "identity_included_note",
              "What follows is said of other entities, which statements say are the same as this one. It is not said of this one.",
            )}
          </p>
          <div class="mb-6">
            <ClusterWarnings cluster={cluster()} />
          </div>
          <div class="flex flex-col gap-10">
            <For each={cluster().members}>
              {(member) => (
                <div data-testid="identity-included-of" data-id={member.id}>
                  <div class="mb-4 flex flex-wrap items-center gap-2 border-b-[0.5px] border-slate-400/70 pb-2">
                    <span class="text-xs font-semibold text-slate-500 uppercase select-none">
                      {t("identity_said_of", "Said of")}
                    </span>
                    <ReferenceChip type={member.type} label={member.label} href={refHref(member)} />
                    <Show when={member.through.length > 0}>
                      <span class="text-xs font-semibold text-slate-500 uppercase select-none">
                        {t("identity_through", "through")}
                      </span>
                      <For each={member.through}>
                        {(id) => (
                          <Show when={labelOf(id)}>
                            {(step) => <ReferenceChip type={step().type} label={step().label} href={refHref(step())} />}
                          </Show>
                        )}
                      </For>
                    </Show>
                  </div>
                  {/* (the other entity with nothing of its own read: what refers to it is read here, as on its page) */}
                  <Show when={inBrowser()} fallback={<Spinner class="size-5 text-slate-500" />}>
                    <Loading fallback={<Spinner class="size-5 text-slate-500" />}>
                      <ItemContents item={{ type: member.type, id: member.id, label: member.label, incomingCounts: null }} />
                    </Loading>
                  </Show>
                </div>
              )}
            </For>
          </div>
        </section>
      )}
    </Show>
  );
}

/**
 * After the contents of an entity's page (an `itemSections` entry), when the page's address asks for it (`?same=all`,
 * the whole cluster, or `?same=one`, only those a statement names with this entity; chosen in the section above the
 * contents): what refers to each of the other entities of its cluster, under that entity's chip, so that nothing
 * said of another is taken for something said of this one.
 */
export default function IdentityIncluded(props: ItemSectionProps) {
  const [search] = useSearchParams();
  const steps = () => (props.model.kind === "Entity" ? stepsOf(search.same) : null);
  return <Show when={steps()}>{(chosen) => <Included id={props.id} steps={chosen()} />}</Show>;
}
