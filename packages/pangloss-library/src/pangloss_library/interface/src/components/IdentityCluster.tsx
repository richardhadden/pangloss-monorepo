import { MenuSelect, useComponent, useTranslations } from "@pangloss/interface-core";
import type { ApiClient } from "@pangloss/interface-core";
import { useSearchParams } from "@solidjs/router";
import { For, Show } from "solid-js";
import { clusterClaimHref, disputes, further, hasCluster, stepsOf } from "../identity";
import type { Cluster, Ref, Steps } from "../identity";

const refHref = (ref: Ref) => `/${encodeURIComponent(ref.type)}/${encodeURIComponent(ref.id)}`;

/** The cluster of an entity, as the API reads it; nothing if it cannot be read (it is a help on the page) */
export function readCluster(api: ApiClient, id: string, steps: Steps = "all"): Promise<Cluster | null> {
  return api.get<Cluster>(`/identity/${encodeURIComponent(id)}/cluster`, { steps }).catch(() => null);
}

/**
 * What a reader should know before trusting a cluster, or merging in it: that it is large (one mistaken statement
 * may have joined two groups), that there is more of it than was followed, and each statement in a semantic space
 * that is about two of its members (it joins nothing, and may say they are not the same). The space is named: what
 * it means is not known here
 */
export function ClusterWarnings(props: { cluster: Cluster }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, modelName } = useTranslations();
  return (
    <Show when={props.cluster.large || props.cluster.truncated || props.cluster.inSpaces.length > 0}>
      <ul class="flex flex-col gap-2 text-sm" data-testid="identity-warnings">
        <Show when={props.cluster.large}>
          <li class="text-amber-900" data-testid="identity-large">
            {t(
              "identity_large",
              "This is a large group ({count} entities). One mistaken statement may have joined two groups: check the statements before merging.",
              { count: props.cluster.size },
            )}
          </li>
        </Show>
        <Show when={props.cluster.truncated}>
          <li class="text-amber-900" data-testid="identity-truncated">
            {t("identity_truncated", "There are more entities in this group than were followed.")}
          </li>
        </Show>
        <For each={disputes(props.cluster)}>
          {(dispute) => (
            <li class="flex flex-wrap items-center gap-2" data-testid="identity-dispute">
              <ReferenceChip type={dispute.between[0].type} label={dispute.between[0].label} href={refHref(dispute.between[0])} />
              <span class="text-amber-900">{t("identity_and", "and")}</span>
              <ReferenceChip type={dispute.between[1].type} label={dispute.between[1].label} href={refHref(dispute.between[1])} />
              <span class="text-amber-900">
                {t("identity_dispute", "are both in this group, though a statement in {spaces} is about the two:", {
                  spaces: dispute.claim.spaces.map((space) => modelName(space)).join(" › "),
                })}
              </span>
              <ReferenceChip
                type={dispute.claim.type}
                label={dispute.claim.label ?? dispute.claim.id}
                href={clusterClaimHref(dispute.claim)}
              />
            </li>
          )}
        </For>
      </ul>
    </Show>
  );
}

/**
 * Under what an entity is said to be the same as: those it is the same as only through others ("C, through B"),
 * how many entities the statements join in all, what to be warned of, and the choice to have what is said of the
 * others on this page too (kept in the page's address, `?same=all` or `?same=one`; `IdentityIncluded` shows it)
 */
export function ClusterPart(props: { cluster: Cluster | null }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  const [search, setSearch] = useSearchParams();
  const included = () => stepsOf(search.same) ?? "off";
  return (
    <Show when={hasCluster(props.cluster) && props.cluster}>
      {(cluster) => (
        <div class="flex flex-col gap-3 border-t-[0.5px] border-slate-400/70 pt-3" data-testid="identity-cluster">
          <Show when={further(cluster()).length > 0}>
            <div class="flex flex-col gap-2">
              <h2 class="text-xs font-semibold text-slate-700 uppercase select-none">
                {t("identity_further", "And so, through others, the same as")}
              </h2>
              <ul class="flex flex-col gap-2">
                <For each={further(cluster())}>
                  {(found) => (
                    <li class="flex flex-wrap items-center gap-2" data-testid="identity-further" data-id={found.member.id}>
                      <ReferenceChip type={found.member.type} label={found.member.label} href={refHref(found.member)} />
                      <span class="text-xs font-semibold text-slate-500 uppercase select-none">
                        {t("identity_through", "through")}
                      </span>
                      <For each={found.through}>
                        {(step) => <ReferenceChip type={step.type} label={step.label} href={refHref(step)} />}
                      </For>
                    </li>
                  )}
                </For>
              </ul>
            </div>
          </Show>
          <p class="text-sm text-slate-700" data-testid="identity-size">
            {t("identity_size", "These statements join {count} entities.", { count: cluster().size })}
          </p>
          <ClusterWarnings cluster={cluster()} />
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-sm text-slate-700">{t("identity_include", "Show what is said of them on this page:")}</span>
            <MenuSelect
              label={t("identity_include_label", "What is said of the entities said to be the same")}
              look="small"
              class="w-56"
              value={included()}
              options={[
                { value: "off", label: t("identity_include_off", "No") },
                { value: "all", label: t("identity_include_all", "Of all of them") },
                { value: "one", label: t("identity_include_one", "Only of those named directly") },
              ]}
              onChoose={(value) => setSearch({ same: value === "off" ? undefined : value }, { replace: true, scroll: false })}
            />
          </div>
        </div>
      )}
    </Show>
  );
}
