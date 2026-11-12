import {
  ApiError,
  buttonClass,
  getEditView,
  getItem,
  getModel,
  inputClass,
  ItemValue,
  MenuSelect,
  Modal,
  segmentClass,
  segmentedClass,
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableHeadRowClass,
  useApi,
  useComponent,
  useCurrentUser,
  useModels,
  useToasts,
  useTranslations,
} from "@pangloss/interface-core";
import type { ApiClient, HeadView, ModelDefinitions } from "@pangloss/interface-core";
import { createMemo, createSignal, For, refresh, Show, untrack } from "solid-js";
import {
  compareHref,
  getPermissions,
  itemHref,
  mergeEntities,
  previewMerge,
  proposeMerge,
  rejectMerge,
  verifyMerge,
} from "../api";
import type { MergeRecord, MergeResult, Values } from "../api";
import {
  chosenValues,
  classChoices,
  isEmpty,
  notKept,
  referringKinds,
  rows as rowsOf,
  startingChoice,
  valueOf,
} from "../compare";
import type { Choice, Choices, Row } from "../compare";
import { HeadChip, Heading, Notice, reasonOf, TypeCounts } from "./parts";

/** The class at which two entities of one family are read and merged: the topmost entity class above `type` */
export function familyTop(definitions: ModelDefinitions, type: string): string {
  let top = type;
  for (let model = getModel(definitions, type); model?.kind === "Entity"; ) {
    top = model.name;
    model = model.parent ? getModel(definitions, model.parent) : undefined;
  }
  return top;
}

// (an entity as its own class edits it: read first at the class of the family, which says what class it is)
const readEntity = (api: ApiClient, top: string, id: string): Promise<HeadView> =>
  getItem(api, top, id, { incomingLimit: 0, extras: false }).then((found) => getEditView(api, found.type, found.id));

export interface ComparisonProps {
  /** A class both entities are of (the one in the address) */
  type: string;
  /** The entity that stays, and the one it absorbs */
  survivor: string;
  absorbed: string;
  /** The proposal that is being looked at, by someone who may verify or reject it */
  proposal?: MergeRecord;
  /** Called with the merge that was made, the proposal that was recorded, or the proposal as it is once rejected */
  onMerged: (result: MergeResult) => void;
  onProposed: (record: MergeRecord) => void;
  onRejected?: (record: MergeRecord) => void;
}

/**
 * Two entities side by side, a row for each field that either has something in, and what the survivor is to have:
 * chosen row by row, starting from what the API suggests (or, for a proposal, from what was proposed). Under the
 * rows, what the merge would do: how much refers to each, the documents that name both, and whether it can be made.
 * Then the buttons: merge (asked again in a dialog that names both), propose, or verify and reject.
 *
 * It reads the two entities, what the user may do and the preview: draw it in a `Loading`.
 */
export function Comparison(props: ComparisonProps) {
  const api = useApi();
  const definitions = useModels();
  const toasts = useToasts();
  const ReferenceChip = useComponent("ReferenceChip");
  const { t, modelName, fieldName } = useTranslations();
  const survivor = untrack(() => props.survivor);
  const absorbed = untrack(() => props.absorbed);
  const proposal = untrack(() => props.proposal);
  const top = familyTop(
    definitions,
    untrack(() => props.type),
  );
  const user = () => useCurrentUser()?.username;

  const read = createMemo(() =>
    Promise.all([readEntity(api, top, survivor), readEntity(api, top, absorbed), getPermissions(api)]).then(
      ([a, b, permissions]) => ({ a, b, permissions }),
    ),
  );
  const a = () => read().a;
  const b = () => read().b;
  // (the class the survivor is to take: the one proposed, or none said, which is the API's choice)
  const [asClass, setAsClass] = createSignal<string | undefined>(proposal?.survivorType ?? undefined);
  const preview = createMemo(() => previewMerge(api, top, survivor, { absorb: absorbed, asClass: asClass() }));

  // (a proposal's own fields are where the rows start, unless an entity has changed since it was made)
  const proposalIsCurrent = () =>
    proposal !== undefined &&
    proposal.survivorVersion === a().meta.version &&
    proposal.absorbedVersion === b().meta.version;
  const suggested = (): Values | null | undefined =>
    proposal?.values && proposalIsCurrent() && (asClass() ?? proposal.survivorType) === proposal.survivorType
      ? proposal.values
      : preview().values;
  const type = () => asClass() ?? preview().survivorType ?? a().type;
  const classes = () => classChoices(definitions, a().type, b().type, preview().survivorType);
  const model = () => getModel(definitions, type());
  const rows = (): Row[] => {
    const found = model();
    return found ? rowsOf(found, a(), b(), definitions) : [];
  };
  const lost = () => notKept(definitions, type(), [a(), b()]);

  // What the person chose, over what each row starts with; the label typed, over the one suggested
  const [chosen, setChosen] = createSignal<Choices>({});
  const [typedLabel, setTypedLabel] = createSignal<string>();
  const choiceOf = (row: Row): Choice => chosen()[row.field.key] ?? startingChoice(row, suggested(), definitions);
  const label = () => typedLabel() ?? String(suggested()?.label ?? a().label ?? "");
  const choose = (row: Row, choice: Choice) => setChosen((now) => ({ ...now, [row.field.key]: choice }));
  const chooseClass = (name: string) => {
    // (another class has other fields, and other values suggested: the choices start again)
    setChosen({});
    setAsClass(name);
  };
  const values = () =>
    chosenValues(
      rows(),
      Object.fromEntries(rows().map((row) => [row.field.key, choiceOf(row)])),
      suggested(),
      label(),
      type(),
      definitions,
    );
  const body = () => ({
    absorb: absorbed,
    values: values(),
    asClass: type(),
    versionInto: a().meta.version,
    versionAbsorb: b().meta.version,
  });

  const [note, setNote] = createSignal("");
  const [confirming, setConfirming] = createSignal(false);
  const [rejecting, setRejecting] = createSignal(false);
  const [reason, setReason] = createSignal("");
  const [busy, setBusy] = createSignal(false);

  const direct = () => read().permissions.direct;
  // (over the limit: for an admin, whoever else may merge)
  const tooLarge = () => preview().large && !read().permissions.large;
  const own = () => proposal !== undefined && proposal.proposedBy === user();
  const fieldLabel = (row: Row) => fieldName(model()?.name ?? type(), row.field.name);

  // What a refusal says, and the page read again where it was because something changed meanwhile
  const refused = (error: unknown) => {
    console.error(error);
    setConfirming(false);
    if (error instanceof ApiError && error.status === 412) {
      toasts?.show(
        t("merge_stale", "Not done: one of the two was changed meanwhile. They are shown again, as they are now."),
        "error",
      );
      setChosen({});
      setTypedLabel(undefined);
      refresh(read);
      refresh(preview);
      return;
    }
    toasts?.show(t("merge_refused", "Not done: {reason}", { reason: reasonOf(error) }), "error");
  };
  const run = async <T,>(send: () => Promise<T>, then: (result: T) => void) => {
    setBusy(true);
    try {
      then(await send());
    } catch (error) {
      refused(error);
    } finally {
      setBusy(false);
    }
  };
  const merge = () =>
    run(
      () => (proposal ? verifyMerge(api, proposal.id, body()) : mergeEntities(api, top, survivor, body())),
      (result) => props.onMerged(result),
    );
  const propose = () =>
    run(
      () => proposeMerge(api, top, survivor, { ...body(), note: note().trim() || undefined }),
      (record) => props.onProposed(record),
    );
  const reject = () =>
    run(
      () => rejectMerge(api, proposal!.id, reason().trim()),
      (record) => {
        setRejecting(false);
        props.onRejected?.(record);
      },
    );

  const choiceWords = (choice: Choice) => {
    switch (choice) {
      case "a":
        return t("merge_choice_a", "Stays");
      case "b":
        return t("merge_choice_b", "Absorbed");
      case "both":
        return t("merge_choice_both", "Both");
      case "suggested":
        return t("merge_choice_suggested", "Suggested");
    }
  };
  // (what is offered for a row: what was suggested too, while it is none of the others)
  const optionsOf = (row: Row): Choice[] =>
    startingChoice(row, suggested(), definitions) === "suggested" ? [...row.options, "suggested"] : row.options;
  const cell = `${tableCellClass} align-top`;

  return (
    <Show
      when={a().id !== b().id}
      fallback={
        <Notice tone="refused" testid="merge-same">
          {t("merge_same_entity", "These are one entity already: there is nothing to merge.")}
        </Notice>
      }
    >
      <div data-testid="merge-comparison" data-type={type()}>
        <table class={tableClass}>
          <thead>
            <tr class={tableHeadRowClass}>
              <th class={[tableHeadCellClass, "w-40"]} scope="col">
                {t("merge_field", "Field")}
              </th>
              <th class={[tableHeadCellClass, "w-1/4"]} scope="col">
                <span class="flex flex-col items-start gap-1.5">
                  <span>{t("merge_stays", "Stays")}</span>
                  <span class="font-normal text-slate-900 normal-case" data-testid="merge-survivor">
                    <HeadChip head={{ id: a().id, type: a().type, label: a().label }} />
                  </span>
                </span>
              </th>
              <th class={[tableHeadCellClass, "w-1/4"]} scope="col">
                <span class="flex flex-col items-start gap-1.5">
                  <span>{t("merge_absorbed", "Absorbed")}</span>
                  <span class="font-normal text-slate-900 normal-case" data-testid="merge-absorbed">
                    <HeadChip head={{ id: b().id, type: b().type, label: b().label }} />
                  </span>
                </span>
              </th>
              <th class={tableHeadCellClass} scope="col">
                {t("merge_result", "After the merge")}
              </th>
            </tr>
          </thead>
          <tbody>
            <Show when={classes().length > 1}>
              <tr class="border-b-[0.5px] border-slate-500/30" data-testid="merge-row" data-field="type">
                <th class={[cell, "text-left text-xs font-semibold text-slate-600 uppercase"]} scope="row">
                  {t("merge_class", "Type")}
                </th>
                <td class={cell}>{modelName(a().type)}</td>
                <td class={cell}>{modelName(b().type)}</td>
                <td class={cell}>
                  <MenuSelect
                    label={t("merge_class", "Type")}
                    look="small"
                    class="w-56"
                    value={type()}
                    options={classes().map((name) => ({ value: name, label: modelName(name), type: name }))}
                    onChoose={chooseClass}
                  />
                  <Show when={lost().length > 0}>
                    <p class="mt-2 text-xs text-amber-800" data-testid="merge-not-kept">
                      {t("merge_not_kept", "Not kept, as a {type} has no such field: {fields}", {
                        type: modelName(type()),
                        fields: lost()
                          .map((each) => fieldName(each.model, each.field.name))
                          .join(", "),
                      })}
                    </p>
                  </Show>
                </td>
              </tr>
            </Show>
            <tr class="border-b-[0.5px] border-slate-500/30" data-testid="merge-row" data-field="label">
              <th class={[cell, "text-left text-xs font-semibold text-slate-600 uppercase"]} scope="row">
                {t("label", "Label")}
              </th>
              <td class={cell}>{a().label}</td>
              <td class={cell}>{b().label}</td>
              <td class={cell}>
                <div class="flex flex-col items-start gap-2">
                  <div class={segmentedClass}>
                    <button
                      type="button"
                      class={segmentClass(label() === a().label)}
                      onClick={() => setTypedLabel(String(a().label ?? ""))}
                    >
                      {choiceWords("a")}
                    </button>
                    <button
                      type="button"
                      class={segmentClass(label() === b().label && label() !== a().label)}
                      onClick={() => setTypedLabel(String(b().label ?? ""))}
                    >
                      {choiceWords("b")}
                    </button>
                  </div>
                  <input
                    type="text"
                    class={inputClass}
                    aria-label={t("merge_label_after", "The label after the merge")}
                    data-testid="merge-label"
                    value={label()}
                    onInput={(event) => setTypedLabel(event.currentTarget.value)}
                  />
                </div>
              </td>
            </tr>
            <For each={rows()} keyed={(row) => row.field.key}>
              {(row) => (
                <tr
                  class="border-b-[0.5px] border-slate-500/30"
                  data-testid="merge-row"
                  data-field={row().field.key}
                  data-choice={choiceOf(row())}
                >
                  <th class={[cell, "text-left text-xs font-semibold text-slate-600 uppercase"]} scope="row">
                    {fieldLabel(row())}
                  </th>
                  <td class={cell}>
                    <Show when={!isEmpty(row().a)}>
                      <ItemValue value={row().a} field={row().field} />
                    </Show>
                  </td>
                  <td class={cell}>
                    <Show when={!isEmpty(row().b)}>
                      <ItemValue value={row().b} field={row().field} />
                    </Show>
                  </td>
                  <td class={cell}>
                    <div class="flex flex-col items-start gap-2">
                      <div class={segmentedClass} role="group" aria-label={fieldLabel(row())}>
                        <For each={optionsOf(row())}>
                          {(choice) => (
                            <button
                              type="button"
                              class={segmentClass(choiceOf(row()) === choice)}
                              aria-pressed={choiceOf(row()) === choice ? "true" : "false"}
                              data-choice={choice}
                              onClick={() => choose(row(), choice)}
                            >
                              {choiceWords(choice)}
                            </button>
                          )}
                        </For>
                      </div>
                      <div data-testid="merge-result-value">
                        <Show
                          when={!isEmpty(valueOf(row(), choiceOf(row()), suggested(), definitions))}
                          fallback={<span class="text-xs text-slate-500">{t("merge_nothing", "Nothing")}</span>}
                        >
                          <ItemValue
                            value={valueOf(row(), choiceOf(row()), suggested(), definitions)}
                            field={row().field}
                          />
                        </Show>
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </For>
          </tbody>
        </table>
        <p class="mt-3 text-xs text-slate-500">
          {t(
            "merge_values_kept",
            "What is not chosen is not lost: it stays on the entity absorbed, which is kept. The survivor has the URLs of both.",
          )}
        </p>

        <Heading>{t("merge_what_refers", "What refers to each")}</Heading>
        <dl class="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 text-sm">
          <dt>
            <ReferenceChip type={a().type} label={String(a().label ?? a().id)} />
          </dt>
          <dd data-testid="merge-refer-survivor">
            <Show
              when={referringKinds(preview().referToSurvivor).length > 0}
              fallback={<span class="text-slate-500">{t("merge_nothing_refers", "Nothing refers to it")}</span>}
            >
              <TypeCounts counts={referringKinds(preview().referToSurvivor)} />
            </Show>
          </dd>
          <dt>
            <ReferenceChip type={b().type} label={String(b().label ?? b().id)} />
          </dt>
          <dd data-testid="merge-refer-absorbed">
            <Show
              when={referringKinds(preview().referToAbsorbed).length > 0}
              fallback={<span class="text-slate-500">{t("merge_nothing_refers", "Nothing refers to it")}</span>}
            >
              <TypeCounts counts={referringKinds(preview().referToAbsorbed)} />
            </Show>
          </dd>
        </dl>

        <Show when={preview().collapsed.length > 0}>
          <Heading>{t("merge_collapsed", "These name both in one relation, and will name the survivor once")}</Heading>
          <div class="flex flex-wrap gap-2" data-testid="merge-collapsed">
            <For each={preview().collapsed}>{(head) => <HeadChip head={head} />}</For>
          </div>
        </Show>
        <Show when={preview().both.length > 0}>
          <Heading>{t("merge_both", "These name both in different relations, and will name the survivor in each")}</Heading>
          <div class="flex flex-wrap gap-2" data-testid="merge-both">
            <For each={preview().both}>{(head) => <HeadChip head={head} />}</For>
          </div>
        </Show>

        <div class="mt-8 flex flex-col gap-3">
          <Show
            when={preview().possible}
            fallback={
              <Notice tone="refused" testid="merge-impossible">
                <span class="font-semibold">{t("merge_impossible", "These two cannot be merged:")}</span>
                <ul class="w-full list-disc pl-5">
                  <For each={preview().refused}>{(why) => <li>{why}</li>}</For>
                </ul>
              </Notice>
            }
          >
            <p class="text-sm" data-testid="merge-heads">
              {t(
                "merge_will_write",
                "The merge will write {heads} documents and entities. It can be undone: the entity absorbed is kept.",
                { heads: preview().heads.toLocaleString() },
              )}
              <Show when={preview().kept > 0}>
                {" "}
                {t("merge_kept", "{kept} references stay on the entity absorbed, as their relations say they must.", {
                  kept: preview().kept.toLocaleString(),
                })}
              </Show>
            </p>
            <Show when={tooLarge()}>
              <Notice tone="refused" testid="merge-too-large">
                {t("merge_too_large", "That is more than {limit}: a merge of this size is made by an admin.", {
                  limit: preview().limit.toLocaleString(),
                })}
              </Notice>
            </Show>
          </Show>
          <Show when={proposal !== undefined && !proposalIsCurrent()}>
            <Notice tone="waiting" testid="merge-proposal-changed">
              {t(
                "merge_proposal_changed",
                "One of the two has changed since this was proposed: the rows are what they are now, not what was chosen then.",
              )}
            </Notice>
          </Show>
          <Show when={own()}>
            <Notice tone="waiting" testid="merge-own-proposal">
              {t("merge_own_proposal", "You proposed this merge: someone else verifies it.")}
            </Notice>
          </Show>
          <Show when={proposal === undefined && !direct() && preview().possible}>
            <label class="flex flex-col gap-1.5 text-xs font-semibold text-slate-600 uppercase">
              {t("merge_note", "Why they are one (for whoever verifies it)")}
              <textarea
                class={[inputClass, "h-20 font-normal normal-case"]}
                data-testid="merge-note"
                value={note()}
                onInput={(event) => setNote(event.currentTarget.value)}
              />
            </label>
          </Show>
          <div class="flex flex-wrap justify-end gap-2">
            <Show when={proposal === undefined}>
              <a class={buttonClass("ordinary", "md")} href={compareHref(top, absorbed, survivor)} data-testid="merge-swap">
                {t("merge_swap", "Swap the two")}
              </a>
              <a class={buttonClass("ordinary", "md")} href={itemHref(a().type, a().id)}>
                {t("cancel", "Cancel")}
              </a>
            </Show>
            <Show when={proposal !== undefined}>
              <button
                type="button"
                class={buttonClass("danger", "md")}
                disabled={busy()}
                data-testid="merge-reject"
                onClick={() => setRejecting(true)}
              >
                {own() ? t("merge_withdraw", "Withdraw") : t("merge_reject", "Reject")}
              </button>
            </Show>
            <Show
              when={proposal !== undefined || direct()}
              fallback={
                <button
                  type="button"
                  class={[buttonClass("primary", "md"), "gap-2"]}
                  disabled={busy() || !preview().possible || tooLarge()}
                  data-testid="merge-propose"
                  onClick={() => void propose()}
                >
                  {t("merge_propose", "Propose the merge")}
                </button>
              }
            >
              <button
                type="button"
                class={[buttonClass("primary", "md"), "gap-2"]}
                disabled={busy() || !preview().possible || tooLarge() || own()}
                data-testid="merge-start"
                onClick={() => setConfirming(true)}
              >
                {proposal ? t("merge_verify", "Verify and merge") : t("merge_merge", "Merge")}
              </button>
            </Show>
          </div>
        </div>

        <Show when={confirming()}>
          <Modal title={t("merge_confirm_title", "Merge these two?")} onClose={() => setConfirming(false)} size="lg">
            <div class="flex flex-col gap-4 p-4 text-sm" data-testid="merge-confirm-dialog">
              <div class="flex flex-wrap items-center gap-2">
                <ReferenceChip type={b().type} label={String(b().label ?? b().id)} />
                <span>{t("merge_confirm_into", "will be merged into")}</span>
                <ReferenceChip type={type()} label={label()} />
              </div>
              <p>
                {t(
                  "merge_confirm_what",
                  "Everything that refers to the first will refer to the second: {heads} documents and entities are written, each with a new version.",
                  { heads: preview().heads.toLocaleString() },
                )}
              </p>
              <p class="text-xs text-slate-500">
                {t(
                  "merge_confirm_undo",
                  "The entity absorbed is kept, marked as merged, so the merge can be undone. What is written to the survivor after the merge stays on it.",
                )}
              </p>
              <div class="flex justify-end gap-2">
                <button type="button" class={buttonClass("ordinary", "md")} onClick={() => setConfirming(false)} autofocus>
                  {t("cancel", "Cancel")}
                </button>
                <button
                  type="button"
                  class={buttonClass("primary", "md")}
                  disabled={busy()}
                  data-testid="merge-confirm"
                  onClick={() => void merge()}
                >
                  {busy() ? t("merge_merging", "Merging…") : t("merge_merge", "Merge")}
                </button>
              </div>
            </div>
          </Modal>
        </Show>
        <Show when={rejecting()}>
          <Modal title={t("merge_reject_title", "Reject this proposal?")} onClose={() => setRejecting(false)}>
            <div class="flex flex-col gap-4 p-4 text-sm" data-testid="merge-reject-dialog">
              <label class="flex flex-col gap-1.5 text-xs font-semibold text-slate-600 uppercase">
                {t("merge_reject_reason", "Why (kept with the proposal)")}
                <textarea
                  class={[inputClass, "h-20 font-normal normal-case"]}
                  data-testid="merge-reject-reason"
                  value={reason()}
                  onInput={(event) => setReason(event.currentTarget.value)}
                />
              </label>
              <div class="flex justify-end gap-2">
                <button type="button" class={buttonClass("ordinary", "md")} onClick={() => setRejecting(false)}>
                  {t("cancel", "Cancel")}
                </button>
                <button
                  type="button"
                  class={buttonClass("danger", "md")}
                  disabled={busy()}
                  data-testid="merge-reject-confirm"
                  onClick={() => void reject()}
                >
                  {t("merge_reject", "Reject")}
                </button>
              </div>
            </div>
          </Modal>
        </Show>
      </div>
    </Show>
  );
}
