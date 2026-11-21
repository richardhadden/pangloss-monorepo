import { createMemo, createSignal, For, Show } from "solid-js";
import {
  MenuSelect,
  SectionBar,
  useApi,
  useComponent,
  userIsLoggedIn,
  useSessionKey,
  useTranslations,
} from "@pangloss/interface-core";
import type { ItemSectionProps } from "@pangloss/interface-core";
import { getSimilar } from "../api";
import type { SimilarAnswer, SimilarResult } from "../api";
import {
  ALL_TYPES,
  barWidth,
  profileOptions,
  resultHref,
  similarityText,
  similarPath,
  similarQuery,
  typeOptions,
} from "../similar";

const quiet = "text-sm text-slate-500";

/** One item found: its chip, a bar as long as its similarity, and the figure */
function Row(props: { result: SimilarResult }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, language } = useTranslations();
  const figure = () => similarityText(props.result.similarity, language());
  return (
    <li
      class="col-span-3 grid grid-cols-subgrid items-center"
      data-testid="similar-row"
      data-similarity={String(props.result.similarity)}
    >
      <span class="min-w-0">
        <ReferenceChip type={props.result.type} label={props.result.label} href={resultHref(props.result)} />
      </span>
      {/* (slate only: a colour here would mean nothing) */}
      <span
        class="block h-1 w-24 bg-slate-200"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={props.result.similarity}
        aria-label={t("vectors_similarity", "Similarity {value}", { value: figure() })}
      >
        <span class="block h-full bg-slate-500" style={{ width: barWidth(props.result.similarity) }} />
      </span>
      <span class="text-xs text-slate-500 tabular-nums" aria-hidden="true">
        {figure()}
      </span>
    </li>
  );
}

/** The menus of the section's head: of the profile (when there are several) and of the type (when there are groups) */
function Controls(props: {
  answer: SimilarAnswer;
  profile: string | undefined;
  group: string;
  onProfile: (profile: string) => void;
  onGroup: (group: string) => void;
}) {
  const { t, modelName } = useTranslations();
  return (
    <Show when={props.answer.profiles.length > 1 || props.answer.groups.length > 0}>
      <div class="-mt-3 mb-4 flex justify-end gap-2">
        <Show when={props.answer.profiles.length > 1}>
          <MenuSelect
            label={t("vectors_profile", "Profile")}
            look="small"
            options={profileOptions(props.answer.profiles)}
            value={props.profile ?? props.answer.profiles[0]}
            onChoose={props.onProfile}
          />
        </Show>
        <Show when={props.answer.groups.length > 0}>
          <MenuSelect
            label={t("vectors_type", "Type")}
            look="small"
            options={typeOptions(props.answer.groups, t("vectors_all_types", "All types"), modelName)}
            value={props.group}
            onChoose={props.onGroup}
          />
        </Show>
      </div>
    </Show>
  );
}

/**
 * The items most like this one (`itemSections.Similar`), after the item's contents, on the page of every document and
 * entity, a head's or a nested document's: nearest first, each a chip with a bar of its similarity. The menus in its
 * head choose the profile and narrow to a type (a group); a choice changes the request, not the address.
 *
 * It reads `GET /api/{type}/{id}/similar` itself, directly in a memo: the boundary is the one `ItemSections` gives
 * every section (a boundary of its own, nested in that one, hydrated wrongly), so nothing shows until the answer has
 * come, and it never shows before what refers to the item. Read again on login and logout (`useSessionKey`): what a
 * reader may see among the results is not the same. An item whose class has no vectors shows nothing at all.
 */
export default function SimilarSection(props: ItemSectionProps) {
  const api = useApi();
  const session = useSessionKey();
  const { t } = useTranslations();
  const loggedIn = createMemo(() => userIsLoggedIn());
  // (none chosen: the API's default profile, and all types, even where the item's class is in one group)
  const [profile, setProfile] = createSignal<string | undefined>();
  const [group, setGroup] = createSignal(ALL_TYPES);
  const answer = createMemo(() => {
    session();
    return getSimilar(api, similarPath(props.type, props.id), similarQuery(profile(), group()));
  });
  const results = () => answer().results;
  return (
    <Show when={answer().status !== "excluded"}>
      <section data-testid="similar-section">
        <SectionBar>{t("vectors_heading", "Similar")}</SectionBar>
        <Controls answer={answer()} profile={profile()} group={group()} onProfile={setProfile} onGroup={setGroup} />
        <Show
          when={answer().status !== "pending"}
          fallback={<p class={quiet}>{t("vectors_pending", "Not worked out yet")}</p>}
        >
          <Show when={results().length > 0} fallback={<p class={quiet}>{t("vectors_none", "Nothing similar found")}</p>}>
            {/* (a grid: the chips are one column, the bars another) */}
            <ul class="grid grid-cols-[minmax(0,max-content)_auto_auto] items-center justify-start gap-x-3 gap-y-2">
              <For each={results()} keyed={(result) => result.id}>
                {(result) => <Row result={result()} />}
              </For>
            </ul>
          </Show>
          <Show when={answer().status === "rebuild_due" && loggedIn()}>
            <p class={[quiet, "mt-3"]}>{t("vectors_rebuild_due", "The similarity data is due for a rebuild")}</p>
          </Show>
        </Show>
      </section>
    </Show>
  );
}
