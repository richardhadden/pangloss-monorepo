import { createMemo, Errored, For, Loading, refresh, Show } from "solid-js";
import {
  PageFrame,
  PageTitle,
  RequireLogin,
  Spinner,
  useApi,
  useComponent,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate } from "@solidjs/router";
import type { RouteProps } from "@solidjs/router";
import { convertDocument, getConvertForm } from "../api";

/**
 * Making a derived document one's own: `/derived/convert/:type/:id/:to`. The form of the target class, filled in with
 * what the two classes share; nothing is written until it is saved, and then the derived document itself changes class
 * (same id and history). The documents it rests on are shown beside the form.
 */
export default function ConvertPage(props: RouteProps<"/derived/convert/:type/:id/:to">) {
  const api = useApi();
  const ItemForm = useComponent("ItemForm");
  const ErrorMessage = useComponent("ErrorMessage");
  const ReferenceChip = useComponent("ReferenceChip");
  const navigate = useNavigate();
  const { t, modelName } = useTranslations();
  const form = createMemo(() => getConvertForm(api, props.params.type, props.params.id, props.params.to));
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <PageTitle action={t("derived_convert_title", "Make it my own")} type={props.params.to} />
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<Spinner class="size-5" />}>
            <Show when={form()} keyed>
              {(loaded) => (
                <>
                  <p class="mb-3 text-sm text-slate-600" data-testid="convert-note">
                    {t("derived_convert_note", "This {from} becomes a {to}, with the same address and history. What is filled in is what the two share; the rest is yours to fill in. Nothing is written until you save.", {
                      from: modelName(props.params.type),
                      to: modelName(props.params.to),
                    })}
                  </p>
                  <div class="mb-4 flex flex-wrap items-center gap-2">
                    <For each={loaded.sources}>
                      {(source) => (
                        <ReferenceChip
                          type={source.targetType}
                          label={source.targetLabel ?? source.targetId}
                          href={`/${encodeURIComponent(source.targetType)}/${encodeURIComponent(source.targetId)}`}
                        />
                      )}
                    </For>
                  </div>
                  <ItemForm
                    type={loaded.type}
                    initial={loaded.initial}
                    sendBy={(body) =>
                      convertDocument(api, props.params.type, props.params.id, loaded.type, loaded.version, body)
                    }
                    // (someone, or the worker, wrote it meanwhile: the form is made again from what it is now)
                    onReload={() => void refresh(form)}
                    onSaved={(saved) => navigate(`/${saved.type}/${encodeURIComponent(saved.id)}`)}
                    onCancel={() => navigate(`/${props.params.type}/${encodeURIComponent(props.params.id)}`)}
                  />
                </>
              )}
            </Show>
          </Loading>
        </Errored>
      </PageFrame>
    </RequireLogin>
  );
}
