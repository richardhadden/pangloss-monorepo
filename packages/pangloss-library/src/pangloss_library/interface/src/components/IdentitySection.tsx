import {
  buttonClass,
  getIncoming,
  getItem,
  numberBadgeClass,
  useApi,
  useComponent,
  useModels,
  useTranslations,
  userIsLoggedIn,
} from "@pangloss/interface-core";
import type { ApiClient, ItemSectionProps, ModelDefinitions } from "@pangloss/interface-core";
import { createMemo, createSignal, For, Show } from "solid-js";
import { byContext, claimDirect, claimHref, claimsHeld, contested, grouped, identityIncoming } from "../identity";
import type { Claim, Group, IdentityIncoming } from "../identity";
import { ClusterPart, readCluster } from "./IdentityCluster";

// (how many of a reverse field are read: an entity is said to be the same as a few others, not hundreds)
const READ = 100;

type Data = Record<string, unknown>;

/** The claims of identity about an entity, from what refers to it; whether there are more than were read */
export async function readClaims(
  api: ApiClient,
  definitions: ModelDefinitions,
  type: string,
  id: string,
  fields: IdentityIncoming[],
): Promise<{ claims: Claim[]; more: boolean }> {
  const pages = await Promise.all(
    fields.map(async (field) => {
      const page = await getIncoming(api, type, id, field.key, 1, READ);
      const items = page.results as Data[];
      const claims = field.direct
        ? // (the statement is listed without its fields: each is read for the entities it names)
          (
            await Promise.all(
              items.map((item) =>
                getItem(api, String(item.type), String(item.id), { incomingLimit: 0, extras: false }).then(
                  (read) => claimDirect(item, read, id, definitions),
                  () => [] as Claim[],
                ),
              ),
            )
          ).flat()
        : items.flatMap((item) => claimsHeld(item, id, definitions));
      return { claims, more: page.count > items.length };
    }),
  );
  return { claims: pages.flatMap((page) => page.claims), more: pages.some((page) => page.more) };
}

/** One entity the page's entity is said to be the same as: its chip, how many statements say so, and they, on demand */
function Other(props: { group: Group; type: string; id: string; contested: boolean }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t } = useTranslations();
  const [open, setOpen] = createSignal(false);
  const other = () => props.group.other;
  // (merged into the entity of the page: the claim is why, and there is nothing left to compare)
  const mergedHere = () => other().mergedInto === props.id;
  return (
    <li class="flex flex-col gap-2" data-testid="identity-other" data-id={other().id}>
      <div class="flex flex-wrap items-center gap-2">
        <ReferenceChip
          type={other().type}
          label={other().label}
          href={other().mergedInto ? undefined : `/${encodeURIComponent(other().type)}/${encodeURIComponent(other().id)}`}
        />
        <Show when={other().mergedInto}>
          <span class="text-xs text-slate-600" data-testid="identity-merged">
            {mergedHere()
              ? t("identity_merged_here", "merged into this")
              : t("identity_merged_elsewhere", "merged into another")}
          </span>
        </Show>
        <button
          type="button"
          class={buttonClass("quiet")}
          aria-expanded={open() ? "true" : "false"}
          data-testid="identity-count"
          onClick={() => setOpen(!open())}
        >
          <span class={[numberBadgeClass, "bg-slate-600 text-white"]}>{props.group.claims.length}</span>
          {props.group.claims.length === 1
            ? t("identity_statement", "statement")
            : t("identity_statements", "statements")}
        </button>
        <Show when={props.contested}>
          <span class="text-xs text-amber-800" data-testid="identity-contested">
            {t("identity_contested", "said otherwise too")}
          </span>
        </Show>
        <Show when={userIsLoggedIn() && !other().mergedInto}>
          <a
            class={buttonClass("ordinary")}
            href={`/${encodeURIComponent(props.type)}/${encodeURIComponent(props.id)}/merge/${encodeURIComponent(other().id)}`}
            data-testid="identity-compare"
          >
            {t("identity_compare", "Compare, or merge")}
          </a>
        </Show>
      </div>
      <Show when={open()}>
        <ul class="ml-4 flex flex-col gap-2 border-l-2 border-slate-300 pl-3" data-testid="identity-claims">
          <For each={props.group.claims}>
            {(claim) => (
              <li class="flex flex-wrap items-center gap-2">
                <ReferenceChip type={claim.statement.type} label={claim.statement.label} href={claimHref(claim)} />
                <Show when={claim.head.id !== claim.statement.id}>
                  <span class="text-xs font-semibold text-slate-500 uppercase select-none">{t("identity_in", "in")}</span>
                  <ReferenceChip
                    type={claim.head.type}
                    label={claim.head.label}
                    href={`/${encodeURIComponent(claim.head.type)}/${encodeURIComponent(claim.head.id)}`}
                  />
                </Show>
                <Show when={claim.argument}>
                  <span class="text-sm text-slate-700">“{claim.argument}”</span>
                </Show>
              </li>
            )}
          </For>
        </ul>
      </Show>
    </li>
  );
}

function Claims(props: { type: string; id: string; fields: IdentityIncoming[] }) {
  const api = useApi();
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  // (with them the cluster, the entities the statements join at any number of steps, which the server reads: asked
  // for at the same time, and waited for as one, so that the server renders the section in one more pass, not two)
  const both = createMemo(() =>
    Promise.all([
      // (a help on the page: if it cannot be read, the page is shown without)
      readClaims(api, definitions, props.type, props.id, props.fields).catch(() => ({ claims: [] as Claim[], more: false })),
      readCluster(api, props.id),
    ]),
  );
  const read = () => both()[0];
  const cluster = () => both()[1];
  const groups = () => grouped(read().claims);
  const disputed = () => contested(groups());
  return (
    <Show when={groups().length > 0}>
      <section
        class="mb-6 flex flex-col gap-3 rounded-xs border-[0.5px] border-slate-400/70 bg-slate-100 px-3 py-2.5"
        data-testid="identity-section"
      >
        <For each={byContext(groups())}>
          {(context) => (
            <div class="flex flex-col gap-2" data-testid="identity-context" data-spaces={context.spaces.join("/")}>
              <h2 class="text-xs font-semibold text-slate-700 uppercase select-none">
                <Show
                  when={context.spaces.length > 0}
                  fallback={t("identity_same", "Said to be the same as")}
                >
                  {t("identity_same_in", "Said to be the same as, in {spaces}", {
                    spaces: context.spaces.map((space) => modelName(space)).join(" › "),
                  })}
                </Show>
              </h2>
              <ul class="flex flex-col gap-2">
                <For each={context.groups}>
                  {(group) => (
                    <Other
                      group={group}
                      type={props.type}
                      id={props.id}
                      contested={disputed().has(group.other.id)}
                    />
                  )}
                </For>
              </ul>
            </div>
          )}
        </For>
        <Show when={read().more}>
          <p class="text-xs text-slate-500">{t("identity_more", "There are more statements than are shown here.")}</p>
        </Show>
        <ClusterPart cluster={cluster()} />
      </section>
    </Show>
  );
}

/**
 * Above the contents of an entity's page (an `itemNotices` entry): the entities it is said to be the same as, each
 * a chip with how many statements say so (shown on demand, each a chip to its place in its document), those said
 * plainly first and then those in a semantic space ("in Negative": said *not* to be the same), under the space's
 * name. For someone logged in, each has the way to the comparison of the two, where they can be merged. Under them,
 * the cluster (`ClusterPart`): those it is the same as through others, how many there are, and what to be warned of.
 *
 * Nothing is asked of the API for a type that no claim of identity can name (`identityIncoming`).
 */
export default function IdentitySection(props: ItemSectionProps) {
  const definitions = useModels();
  const fields = () => (props.model.kind === "Entity" ? identityIncoming(definitions, props.type) : []);
  return (
    <Show when={fields().length > 0}>
      <Claims type={props.type} id={props.id} fields={fields()} />
    </Show>
  );
}
