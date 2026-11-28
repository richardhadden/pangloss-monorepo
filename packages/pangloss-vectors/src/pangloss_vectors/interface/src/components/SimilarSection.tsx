import { createEffect, createMemo, createSignal, Errored, For, Loading, Show, untrack } from "solid-js";
import type { JSX } from "@solidjs/web";
import {
  createInBrowser,
  MenuSelect,
  SectionBar,
  useApi,
  useComponent,
  useModules,
  userIsLoggedIn,
  useSessionKey,
  useTranslations,
} from "@pangloss/interface-core";
import type { ItemSectionProps, ListedLabels, ListFilter } from "@pangloss/interface-core";
import { getSimilar } from "../api";
import type { SimilarAnswer, SimilarResult } from "../api";
import {
  ALL_TYPES,
  barWidth,
  filtered,
  filtersOf,
  profileOptions,
  resultHref,
  similarityText,
  similarPath,
  similarQuery,
  SIMILAR_LIST,
  typeOptions,
} from "../similar";

const quiet = "text-sm text-slate-500";

// (the list's grid; its columns, with a last one for labels where a module gives them)
const GRID = "grid items-center justify-start gap-x-3 gap-y-2";

/** One item found: its chip, a bar as long as its similarity, and the figure; and where another module labels the
 *  list (`labelled`), a last cell for what it says of the item, after the figure, where its arrival moves nothing */
function Row(props: { result: SimilarResult; labelled: boolean; label: () => JSX.Element }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, language } = useTranslations();
  const figure = () => similarityText(props.result.similarity, language());
  return (
    <li
      class={["grid grid-cols-subgrid items-center", { "col-span-3": !props.labelled, "col-span-4": props.labelled }]}
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
      <Show when={props.labelled}>
        {/* (one line, cut where the room ends: a label never makes its row taller) */}
        <span class="flex min-w-0 items-center gap-1.5 overflow-hidden whitespace-nowrap" data-testid="similar-labels">
          {props.label()}
        </span>
      </Show>
    </li>
  );
}

/** A filter that another module gives the list: a checkbox and its words, as review's "Show resolved" is */
function Filter(props: { filter: ListFilter; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <label
      class="flex cursor-pointer items-center gap-1.5 text-sm text-slate-700 select-none"
      data-testid="similar-filter"
      data-filter={props.filter.key}
    >
      <input type="checkbox" checked={props.on} onChange={(event) => props.onChange(event.currentTarget.checked)} />
      {props.filter.label}
    </label>
  );
}

/**
 * The menus of the section's head: of the profile (when there are several) and of the type (when there are groups);
 * and, at the left, the filters other modules give the list. Where a module labels the list (`labelled`), the row is
 * there from the start, so that the filters' arrival moves nothing
 */
function Controls(props: {
  answer: SimilarAnswer;
  profile: string | undefined;
  group: string;
  onProfile: (profile: string) => void;
  onGroup: (group: string) => void;
  labelled: boolean;
  filters: readonly ListFilter[];
  on: readonly string[];
  onFilter: (key: string, on: boolean) => void;
}) {
  const { t, modelName } = useTranslations();
  return (
    <Show when={props.answer.profiles.length > 1 || props.answer.groups.length > 0 || props.labelled}>
      <div
        class={[
          "-mt-3 mb-4 flex justify-end gap-2",
          // (one line, kept from the start where a module labels the list: the filters, when they come, move nothing)
          { "items-center": props.labelled, "h-6.5": props.labelled },
        ]}
      >
        <Show when={props.filters.length > 0}>
          {/* (on a narrow page they scroll sideways rather than take a second line) */}
          <div
            class="mr-auto flex min-w-0 items-center gap-x-4 overflow-x-auto whitespace-nowrap"
            data-testid="similar-filters"
          >
            <For each={props.filters} keyed={(filter) => filter.key}>
              {(filter) => (
                <Filter
                  filter={filter()}
                  on={props.on.includes(filter().key)}
                  onChange={(on) => props.onFilter(filter().key, on)}
                />
              )}
            </For>
          </div>
        </Show>
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
 *
 * Another module may say something of what is listed (`listLabels` of the list `"similar"`: comparison labels each
 * statement with its relation to this one): its component is drawn in the browser only, after the list, in a boundary
 * of its own, and tells the section what it read; each row then has its label at its end and the head the module's
 * filters, which narrow what is listed without asking again. With no such module, or none that applies to the
 * item's class, the section is as it would be without them: no place kept, nothing asked.
 */
export default function SimilarSection(props: ItemSectionProps) {
  const api = useApi();
  const session = useSessionKey();
  const { t } = useTranslations();
  const loggedIn = createMemo(() => userIsLoggedIn());
  const inBrowser = createInBrowser();
  // (what labels the list, for this item's class: known as the page is drawn, so that its place is kept)
  const modules = useModules();
  const labellers = createMemo(() => modules.listLabels(SIMILAR_LIST, props.model));
  const labelled = () => labellers().length > 0;
  // (what each has told, by the labeller's name, of this item only: a link to another item's page draws this section
  // again with new props, not anew, and what was read of the last item's list is not this one's)
  const [told, setTold] = createSignal<ReadonlyMap<string, ListedLabels | undefined>>(new Map());
  const reads = createMemo(() =>
    labellers().map(({ name }) => {
      const found = told().get(name);
      return { name, read: found?.of === props.id ? found : undefined };
    }),
  );
  // (the filters that are on, by `app:key:filter`: none again on another item's page)
  const [on, setOn] = createSignal<readonly string[]>([]);
  createEffect(
    () => props.id,
    () => {
      setOn([]);
    },
  );
  // (none chosen: the API's default profile, and all types, even where the item's class is in one group)
  const [profile, setProfile] = createSignal<string | undefined>();
  const [group, setGroup] = createSignal(ALL_TYPES);
  const answer = createMemo(() => {
    session();
    return getSimilar(api, similarPath(props.type, props.id), similarQuery(profile(), group()));
  });
  const results = () => answer().results;
  // (what the labellers are told is listed: the same array while the answer is)
  const items = createMemo(() => results().map((result) => ({ id: result.id, type: result.type })));
  const filters = createMemo(() => filtersOf(reads()));
  const shown = () => filtered(results(), filters(), on());
  const read = (name: string, found: ListedLabels | undefined) => setTold((was) => new Map(was).set(name, found));
  const labelOf = (id: string) => () => reads().map((each) => each.read?.label(id));
  return (
    <Show when={answer().status !== "excluded"}>
      <section data-testid="similar-section">
        <SectionBar>{t("vectors_heading", "Similar")}</SectionBar>
        <Controls
          answer={answer()}
          profile={profile()}
          group={group()}
          onProfile={setProfile}
          onGroup={setGroup}
          labelled={labelled()}
          filters={filters()}
          on={on()}
          onFilter={(key, isOn) => setOn((was) => (isOn ? [...was.filter((each) => each !== key), key] : was.filter((each) => each !== key)))}
        />
        <Show
          when={answer().status !== "pending"}
          fallback={<p class={quiet}>{t("vectors_pending", "Not worked out yet")}</p>}
        >
          <Show when={results().length > 0} fallback={<p class={quiet}>{t("vectors_none", "Nothing similar found")}</p>}>
            <Show
              when={shown().length > 0}
              fallback={
                <p class={quiet} data-testid="similar-none-filtered">
                  {t("vectors_none_filtered", "Nothing listed here passes the filters")}
                </p>
              }
            >
              {/* (a grid: the chips are one column, the bars another; and the labels, where a module gives them) */}
              <ul
                class={[
                  GRID,
                  {
                    "grid-cols-[minmax(0,max-content)_auto_auto]": !labelled(),
                    // (the labels take what room is left, so that their arrival squeezes no chip)
                    "grid-cols-[minmax(0,max-content)_auto_auto_minmax(0,1fr)]": labelled(),
                  },
                ]}
              >
                <For each={shown()} keyed={(result) => result.id}>
                  {(result) => <Row result={result()} labelled={labelled()} label={labelOf(result().id)} />}
                </For>
              </ul>
            </Show>
          </Show>
          <Show when={answer().status === "rebuild_due" && loggedIn()}>
            <p class={[quiet, "mt-3"]}>{t("vectors_rebuild_due", "The similarity data is due for a rebuild")}</p>
          </Show>
        </Show>
        {/* (what labels the list: read in the browser once the list is drawn, each in a boundary of its own, made anew
            for each item (so that one that failed on the page before is tried again), drawing nothing; one that fails
            leaves the list as it is, and says why in the console) */}
        <Show when={labelled() && inBrowser()}>
          <For each={labellers()} keyed={(labeller) => labeller.name}>
            {(labeller) => {
              const name = untrack(labeller).name;
              const Labeller = untrack(labeller).component;
              return (
                <Show when={props.id} keyed>
                  {(id) => (
                    <Errored
                      fallback={(error) => {
                        // (said in the browser's console, as a section of a module that failed is)
                        console.error(`A list labeller of an interface module (${name}) failed:`, error());
                        return null;
                      }}
                    >
                      <Loading fallback={null}>
                        <Labeller
                          list={SIMILAR_LIST}
                          type={props.type}
                          id={id}
                          model={props.model}
                          items={items()}
                          onRead={(found) => read(name, found)}
                        />
                      </Loading>
                    </Errored>
                  )}
                </Show>
              );
            }}
          </For>
        </Show>
      </section>
    </Show>
  );
}
