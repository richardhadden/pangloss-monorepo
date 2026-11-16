import { PageFrame, PageTitle, RequireLogin, Spinner, useComponent, useToasts, useTranslations } from "@pangloss/interface-core";
import { revalidate, useNavigate } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { createSignal, Errored, Loading, Show } from "solid-js";
import { mergeHref } from "../api";
import type { MergeResult } from "../api";
import { Comparison } from "./Comparison";
import { MergeSummary } from "./MergeSummary";

/**
 * `/:type/:id/merge/:other`: the entity `id`, which stays, beside the entity `other`, which it is to absorb, with
 * what the survivor is to have. For someone logged in. Once merged, the page says what was done, with the documents
 * to look at; a proposal goes to its own page.
 */
export default function ComparePage(props: RouteProps<"/:type/:id/merge/:other">) {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const navigate = useNavigate();
  const toasts = useToasts();
  const { t } = useTranslations();
  // (the two in the address, which a swap changes: the comparison is made anew for another pair)
  const pair = () => `${props.params.type}/${props.params.id}/${props.params.other}`;
  const [made, setMade] = createSignal<MergeResult>();
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <PageTitle action={t("merge_title", "Merge")} type={props.params.type} />
        <Console type={props.params.type} />
        <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">
          {t("merge_heading", "Merge two that are one")}
        </h1>
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p class="pt-2 text-slate-500"><Spinner class="size-5" /></p>}>
            <Show when={made()}>{(result) => <MergeSummary result={result()} />}</Show>
            <Show when={made() ? undefined : pair()} keyed>
              {(_pair) => (
                <Comparison
                  type={props.params.type}
                  survivor={props.params.id}
                  absorbed={props.params.other}
                  onMerged={(result) => {
                    toasts?.show(t("merge_done", "Merged"), "success");
                    void revalidate();
                    setMade(result);
                  }}
                  onProposed={(record) => {
                    toasts?.show(t("merge_proposed", "Proposed: someone else verifies it"), "success");
                    navigate(mergeHref(record.id));
                  }}
                />
              )}
            </Show>
          </Loading>
        </Errored>
      </PageFrame>
    </RequireLogin>
  );
}
