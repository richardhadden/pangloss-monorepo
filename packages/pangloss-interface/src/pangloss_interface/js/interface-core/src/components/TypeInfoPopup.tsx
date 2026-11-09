import { createEffect, createMemo, createSignal, For, Loading, onSettled, Show } from "solid-js";
import { useModels, userIsLoggedIn, useTranslations } from "../context";
import { kindRule, kindTint } from "../primitives";
import { acceptedTypes, editableFields, getModel, reflowHelp } from "../schema";
import type { AcceptedType } from "../schema";
import type { ModelDefinition } from "../types";
import { plainTint } from "./form/styles";

type Box = { left: number; right: number; top: number; bottom: number };

/** Where the popup goes: under what it is about, or beside it, on the other side if there is no room, and always on the screen */
export function placeTypeInfo(
  anchor: Box,
  size: { width: number; height: number },
  viewport: { width: number; height: number },
  side: "below" | "right",
): { left: number; top: number } {
  const gap = 6;
  const margin = 8;
  let left = anchor.left;
  let top = anchor.top;
  if (side === "below") {
    top = anchor.bottom + gap;
    if (top + size.height > viewport.height - margin && anchor.top - gap - size.height >= margin) {
      top = anchor.top - gap - size.height;
    }
  } else {
    left = anchor.right + gap;
    if (left + size.width > viewport.width - margin && anchor.left - gap - size.width >= margin) {
      left = anchor.left - gap - size.width;
    }
  }
  return {
    left: Math.max(margin, Math.min(left, viewport.width - size.width - margin)),
    top: Math.max(margin, Math.min(top, viewport.height - size.height - margin)),
  };
}

/**
 * The description of a type, while the pointer is on something marked `data-type-info="ModelName"` and Alt is held
 * (either first): its name and help text and, for someone logged in, its fields and what each accepts. There is one, in
 * the frame of the page; to have it, a chip only needs the attribute (`data-type-info-side="right"` to have it beside
 * rather than under). It takes no pointer events, so it never comes between the pointer and what is under it.
 */
export function TypeInfoPopup() {
  const definitions = useModels();
  const [anchor, setAnchor] = createSignal<HTMLElement | null>(null);
  const [alt, setAlt] = createSignal(false);
  let panel: HTMLDivElement | undefined;
  const shown = createMemo(() => {
    const element = anchor();
    // (not connected: the page changed under a pointer that has not moved)
    if (!alt() || !element?.isConnected) return undefined;
    const model = getModel(definitions, element.dataset.typeInfo ?? "");
    return model ? { model, element } : undefined;
  });
  onSettled(() => {
    const onOver = (event: MouseEvent) => {
      setAlt(event.altKey);
      setAnchor((event.target as Element | null)?.closest?.<HTMLElement>("[data-type-info]") ?? null);
    };
    const clear = () => setAnchor(null);
    // (only a popup that is showing: a scroll with none, as moving to a row near the end of a list can cause, must leave
    // what is under the pointer known, as no new mouseover comes for it)
    const dismiss = () => {
      if (shown()) clear();
    };
    // (held back while there is a popup: Alt on its own would otherwise go to the browser's menu, off a Mac)
    const onDown = (event: KeyboardEvent) => {
      if (event.key !== "Alt") return;
      setAlt(true);
      if (anchor()) event.preventDefault();
    };
    const onUp = (event: KeyboardEvent) => {
      if (event.key !== "Alt") return;
      if (shown()) event.preventDefault();
      setAlt(false);
    };
    // (Alt+Tab: the key is let go in another window)
    const onBlur = () => setAlt(false);
    const root = document.documentElement;
    document.addEventListener("mouseover", onOver);
    document.addEventListener("click", dismiss);
    document.addEventListener("scroll", dismiss, true);
    document.addEventListener("keydown", onDown);
    document.addEventListener("keyup", onUp);
    root.addEventListener("mouseleave", clear);
    window.addEventListener("blur", onBlur);
    return () => {
      document.removeEventListener("mouseover", onOver);
      document.removeEventListener("click", dismiss);
      document.removeEventListener("scroll", dismiss, true);
      document.removeEventListener("keydown", onDown);
      document.removeEventListener("keyup", onUp);
      root.removeEventListener("mouseleave", clear);
      window.removeEventListener("blur", onBlur);
    };
  });
  createEffect(shown, (now) => {
    if (!now || !panel) return;
    const size = panel.getBoundingClientRect();
    const side = now.element.dataset.typeInfoSide === "right" ? "right" : "below";
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const place = placeTypeInfo(now.element.getBoundingClientRect(), size, viewport, side);
    panel.style.left = `${place.left}px`;
    panel.style.top = `${place.top}px`;
  });
  return (
    <Show when={shown()}>
      {(now) => (
        <div
          ref={panel}
          role="tooltip"
          class="pointer-events-none fixed top-0 left-0 z-[60] max-h-[calc(100vh-1rem)] w-max max-w-sm overflow-hidden rounded-xs border-[0.5px] border-slate-400/70 bg-white text-left font-normal normal-case shadow-lg"
        >
          <TypeInfoContents model={now().model} />
        </div>
      )}
    </Show>
  );
}

function TypeInfoContents(props: { model: ModelDefinition }) {
  const definitions = useModels();
  const { t, modelName, modelHelp, fieldName } = useTranslations();
  const help = () => reflowHelp(modelHelp(props.model.name) || props.model.description || "");
  const fields = () => editableFields(props.model);
  return (
    <>
      {/* (as a chip's type is: the colour of the type, framed in it) */}
      <h2
        class={[
          "border-b-[0.5px] px-3 py-1.5 text-xs font-semibold uppercase",
          kindTint(props.model.kind, props.model.interfaceMeta?.colour) || plainTint,
          kindRule(props.model.kind, props.model.interfaceMeta?.colour),
        ]}
      >
        {modelName(props.model.name)}
      </h2>
      <Show when={help()}>
        <p class="px-3 pt-2 pb-2 text-xs whitespace-pre-line text-slate-600">{help()}</p>
      </Show>
      {/* (the rest waits for who is logged in, which the name and the help do not) */}
      <Loading fallback={null}>
        <Show when={userIsLoggedIn() && fields().length > 0}>
          <h3
            class={[
              "px-3 pt-2 text-xs font-semibold text-slate-500 uppercase",
              { "border-t-[0.5px]": !!help(), "border-slate-400/50": !!help() },
            ]}
          >
            {t("type_info_fields", "Fields")}
          </h3>
          <dl class="mt-1 px-3 pb-2 grid grid-cols-[auto_1fr] items-baseline gap-x-3 gap-y-1 text-xs">
            <For each={fields()}>
              {(field) => (
                <>
                  <dt class="font-semibold text-slate-500 uppercase">{fieldName(props.model.name, field.name)}</dt>
                  <dd class="flex flex-wrap gap-1">
                    <For each={acceptedTypes(definitions, field)}>{(type) => <Accepted type={type} />}</For>
                  </dd>
                </>
              )}
            </For>
          </dl>
        </Show>
      </Loading>
    </>
  );
}

function Accepted(props: { type: AcceptedType }) {
  const definitions = useModels();
  const { t, modelName, enumName } = useTranslations();
  const scalar = (name: string) => {
    switch (name) {
      case "str":
        return t("type_info_text", "Text");
      case "int":
        return t("type_info_whole_number", "Whole number");
      case "float":
      case "decimal":
        return t("type_info_number", "Number");
      case "bool":
        return t("type_info_yes_or_no", "Yes or no");
      case "date":
        return t("type_info_date", "Date");
      case "datetime":
        return t("type_info_date_time", "Date and time");
      case "time":
        return t("type_info_time", "Time");
      default:
        return t("type_info_duration", "Duration");
    }
  };
  const text = () => {
    const type = props.type;
    if (type.kind === "model") return modelName(type.name);
    if (type.kind === "enum") return enumName(type.name);
    if (type.kind === "scalar") return scalar(type.scalar);
    if (type.kind === "value") return type.value;
    if (type.kind === "typeVar") return type.name;
    return t("type_info_structured", "Several values");
  };
  const tint = () => {
    const type = props.type;
    if (type.kind !== "model") return "text-slate-600";
    const model = getModel(definitions, type.name);
    return [
      "rounded-xs px-1 text-[0.65rem] font-semibold uppercase",
      kindTint(model?.kind, model?.interfaceMeta?.colour) || plainTint,
    ];
  };
  return <span class={tint()}>{text()}</span>;
}
