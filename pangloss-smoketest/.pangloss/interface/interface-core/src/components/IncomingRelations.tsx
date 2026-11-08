import { createEffect, createMemo, createSignal, Errored, Loading, Show } from "solid-js";
import type { ParentProps } from "solid-js";
import { Dynamic } from "@solidjs/web";
import type { JSX } from "@solidjs/web";
import { getIncoming, getIncomingFields, INCOMING_PAGE, INCOMING_SHOWN } from "../api";
import {
  useApi,
  useComponent,
  useIncomingView,
  useModels,
  useModules,
  useTranslations,
} from "../context";
import type { IncomingEntry, ModelDefinition } from "../types";
import { Spinner } from "../primitives";
import { fieldGridClass, fieldRuleClass, smallButtonClass } from "./form/styles";
import { VirtualRows } from "./VirtualRows";

type Data = Record<string, unknown>;

const isObject = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const asItems = (value: unknown): Data[] =>
  (Array.isArray(value) ? value : value ? [value] : []).filter(isObject);

/** What has been read of what refers to an item since the item was: by the key of the incoming field, the items it has now */
type Read = Record<string, Data[]>;

/**
 * From how many of what refers to an entity on, the rows of it are rendered only as they come on show
 * (`VirtualRows`): every chip costs a millisecond or so to make and to hydrate, and an entity can have thousands
 */
export const INCOMING_VIRTUAL_FROM = 200;
// (the height of a row before it is measured: a name and a line or two of chips; the space between rows, as `gap-y-5`)
const ROW_HEIGHT = 80;
const ROW_GAP = 20;
// (a row rendered on its own, out of the grid of the fields: the same columns as the grid, see `fieldGridClass`)
const ownRowClass = "grid grid-cols-[10rem_minmax(0,1fr)] gap-x-6 @max-md:grid-cols-1";

export interface IncomingRelationsProps {
  /**
   * The item, as the API sends it: its incoming fields hold what was read with it (all of it, or the first of each
   * with `incomingCounts`), or none of it was (`incomingCounts` null), and it is read here
   */
  item: Data;
  model: ModelDefinition;
  /** Whether rows of the item's own fields come before: the first row is then ruled off from them */
  afterFields?: boolean;
  /** Draws some of what refers, as chips */
  chips: (items: Data[]) => JSX.Element;
}

/**
 * What refers to an item from elsewhere (its model's `incoming` fields): a row of chips for each field, after the
 * rows of its own fields and laid out as they are; or, on its page, an interface module's view of it
 * (`incomingViews`, chosen in the console), which takes some of it and shows that after the rows in its own way,
 * the rest staying by field.
 *
 * What the item carries is shown (an item read whole, or with the first few of each field and how many there are,
 * `incomingCounts`). An item read without it (`incomingCounts` null: the item's page reads the item first, so that
 * it is on show at once) has it read here, the first few of each field (`INCOMING_SHOWN`), in a boundary of its own:
 * on the server it is streamed after the item; in the browser the page is not kept waiting. (The item page puts it in
 * a `Reveal` with the modules' sections: they show after it, not before it and then lower down.) A row that has more
 * ends in "and N more" (`MoreIncoming`), and a module's view says how many it is without (`ReadAllIncoming`). Many
 * rows are rendered only as they come on show (`INCOMING_VIRTUAL_FROM`).
 */
export function IncomingRelations(props: IncomingRelationsProps) {
  return (
    <Show
      when={props.item.incomingCounts === null}
      fallback={
        <IncomingRows
          item={props.item}
          model={props.model}
          afterFields={props.afterFields}
          chips={props.chips}
          counts={isObject(props.item.incomingCounts) ? (props.item.incomingCounts as Record<string, number>) : undefined}
          initial={props.item}
        />
      }
    >
      <FetchedIncoming {...props} />
    </Show>
  );
}

// (not read with the item: read here, and again with a new item, as after logging in or out, when what a reader may
// see of it is not the same)
function FetchedIncoming(props: IncomingRelationsProps) {
  const api = useApi();
  const ErrorMessage = useComponent("ErrorMessage");
  const read = createMemo(() => {
    const item = props.item;
    return getIncomingFields(api, String(item.type), String(item.id), INCOMING_SHOWN);
  });
  // (the `Loading` outermost: it is the boundary the page's `Reveal` orders, and an `Errored` between would sever it)
  return (
    <Loading
      fallback={
        <p class={["text-slate-500", { "mt-5": props.afterFields }]} data-testid="incoming-loading">
          <Spinner class="size-5" />
        </p>
      }
    >
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <IncomingRows
          item={props.item}
          model={props.model}
          afterFields={props.afterFields}
          chips={props.chips}
          counts={read().counts}
          initial={read().fields}
        />
      </Errored>
    </Loading>
  );
}

/** A row of what refers to the item by one field: the field's name, and the items it has now */
interface FieldRow {
  key: string;
  name: string;
  items: Data[];
  /** Whether the row can read more of the field (by field; a module's view reads for all at once) */
  more: boolean;
}

function IncomingRows(props: {
  item: Data;
  model: ModelDefinition;
  afterFields?: boolean;
  chips: (items: Data[]) => JSX.Element;
  /** How many there are in each field, when not all was read */
  counts?: Record<string, number>;
  /** What was read: the items of each field, by key */
  initial: Data;
}) {
  const { incomingName } = useTranslations();
  const definitions = useModels();
  const views = useModules().incomingViews();
  const incoming = useIncomingView();
  const page = () => ({ type: String(props.item.type), id: String(props.item.id) });
  // What has been read since (forgotten when what was read with the item is read again)
  const [read, setRead] = createSignal<Read>(() => (void props.initial, {}));
  const itemsOf = (key: string): Data[] => read()[key] ?? asItems(props.initial[key]);
  // (how many of a field the page does not have)
  const leftOf = (key: string) => Math.max(0, (props.counts?.[key] ?? 0) - itemsOf(key).length);
  const partial = createMemo(() =>
    (props.model.incoming ?? [])
      .filter((field) => leftOf(field.key) > 0)
      .map((field) => ({ key: field.key, items: itemsOf(field.key) })),
  );
  const entries = createMemo<IncomingEntry[]>(() =>
    (props.model.incoming ?? []).flatMap((field) =>
      itemsOf(field.key).map((item) => ({
        key: field.key,
        name: incomingName(props.model.name, field.name),
        item,
      })),
    ),
  );
  // (the views that have something to show)
  const offered = createMemo(() =>
    views.length > 0 ? views.filter((view) => entries().some((entry) => view.takes(entry.item, definitions))) : [],
  );
  // (the console offers each for as long as it has something)
  createEffect(offered, (now) => {
    const withdraw = now.map((view) => incoming.offer(view.name));
    return () => withdraw.forEach((done) => done());
  });
  const view = () => offered().find((view) => view.name === incoming.chosen());
  const taken = createMemo(() => {
    const chosen = view();
    return chosen ? entries().filter((entry) => chosen.takes(entry.item, definitions)) : [];
  });
  // The rows: every field that has something; with a view, only what it does not take, by the field it is in
  const rows = createMemo<FieldRow[]>(() => {
    if (!view()) {
      return (props.model.incoming ?? [])
        .filter((field) => itemsOf(field.key).length > 0)
        .map((field) => ({
          key: field.key,
          name: incomingName(props.model.name, field.name),
          items: itemsOf(field.key),
          more: true,
        }));
    }
    const groups = new Map<string, FieldRow>();
    for (const entry of entries()) {
      if (taken().includes(entry)) continue;
      const group = groups.get(entry.key) ?? { key: entry.key, name: entry.name, items: [], more: false };
      group.items.push(entry.item);
      groups.set(entry.key, group);
    }
    return [...groups.values()];
  });
  const virtual = () => entries().length >= INCOMING_VIRTUAL_FROM;
  return (
    <>
      <Show when={rows().length > 0}>
        <dl class={[fieldGridClass, { "mt-5": props.afterFields }]} data-testid="incoming-by-field">
          <VirtualRows
            rows={rows()}
            virtual={virtual()}
            soon={entries().length >= INCOMING_VIRTUAL_FROM / 2}
            estimateSize={ROW_HEIGHT}
            gap={ROW_GAP}
            class="col-span-full"
            rowClass={ownRowClass}
          >
            {(row, index) => (
              <IncomingRow name={row.name} ruled={props.afterFields || index() > 0}>
                {props.chips(row.items)}
                <Show when={row.more && leftOf(row.key) > 0}>
                  <MoreIncoming
                    page={page()}
                    field={row.key}
                    items={row.items}
                    left={leftOf(row.key)}
                    onRead={(items) => setRead((before) => ({ ...before, [row.key]: items }))}
                  />
                </Show>
              </IncomingRow>
            )}
          </VirtualRows>
        </dl>
      </Show>
      <Show when={view() && partial().length > 0}>
        <ReadAllIncoming
          page={page()}
          fields={partial()}
          left={partial().reduce((sum, field) => sum + leftOf(field.key), 0)}
          onRead={(found) => setRead((before) => ({ ...before, ...found }))}
        />
      </Show>
      <Show when={view()}>
        {(chosen) => (
          <Errored
            fallback={(error) => {
              // (said in the browser's console, so that a module's author sees why there is nothing)
              console.error("A view of an interface module failed:", error());
              return null;
            }}
          >
            <Loading fallback={null}>
              {/* (`Dynamic`: the view chosen is read where it is shown, so another one chosen is shown) */}
              <Dynamic
                component={chosen().component}
                type={page().type}
                id={page().id}
                model={props.model}
                entries={taken()}
              />
            </Loading>
          </Errored>
        )}
      </Show>
    </>
  );
}

/**
 * A key on the left, chips on the right, laid out as a row of the item's fields is (a row of the same grid, or one
 * of its own, see `ownRowClass`), with more room above it and between its items, and the chips of a line centred on
 * each other (some are taller, wrapped in semantic spaces). `ruled`: a hairline above it (not the first row, unless
 * the item's own fields come before)
 */
function IncomingRow(props: ParentProps<{ name: string; ruled: boolean }>) {
  return (
    <div
      class={[
        "col-span-full grid grid-cols-subgrid gap-y-1.5",
        { "border-t": props.ruled, [fieldRuleClass]: props.ruled, "pt-6": props.ruled, "@max-sm:pt-3": props.ruled },
      ]}
    >
      <dt class="pt-1 text-xs font-semibold text-slate-500 uppercase">{props.name}</dt>
      <dd class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-6">{props.children}</dd>
    </div>
  );
}

/**
 * After the items of a row of what refers to an entity, when there are more than were read with it: "and 109 more",
 * which reads the next of them (a hundred at a time, by label, as the first were) and gives the row what it has now.
 */
function MoreIncoming(props: {
  page: { type: string; id: string };
  field: string;
  /** What the row has */
  items: Data[];
  /** How many it does not have */
  left: number;
  onRead: (items: Data[]) => void;
}) {
  const api = useApi();
  const { t } = useTranslations();
  const [reading, setReading] = createSignal(false);
  const read = async () => {
    setReading(true);
    try {
      // (whole pages from the start: what the row has of the page it is in is read again with the rest of it)
      const page = Math.floor(props.items.length / INCOMING_PAGE) + 1;
      const kept = props.items.slice(0, (page - 1) * INCOMING_PAGE);
      const answer = await getIncoming(api, props.page.type, props.page.id, props.field, page);
      props.onRead([...kept, ...answer.results]);
    } finally {
      setReading(false);
    }
  };
  return (
    <button
      type="button"
      class={[smallButtonClass, "text-slate-600 disabled:text-slate-400"]}
      disabled={reading()}
      data-testid="incoming-more"
      onClick={() => void read()}
    >
      {t("incoming_more", "and {count} more", { count: props.left })}
    </button>
  );
}

/**
 * Above an interface module's view of what refers to an entity, when not all of it has been read: the view has only
 * what the page has (sorted by date, the first few of each field are not the earliest), so it says how many are
 * missing, and reads them all when asked.
 */
function ReadAllIncoming(props: {
  page: { type: string; id: string };
  /** The fields that have more than was read, by key, with what each has */
  fields: { key: string; items: Data[] }[];
  left: number;
  /** (once, with every field: the view is laid out again for each change of what it has) */
  onRead: (read: Read) => void;
}) {
  const api = useApi();
  const { t } = useTranslations();
  const [reading, setReading] = createSignal(false);
  const all = async (key: string): Promise<Data[]> => {
    let items: Data[] = [];
    for (let page = 1; ; page++) {
      const answer = await getIncoming(api, props.page.type, props.page.id, key, page, 500);
      items = [...items, ...answer.results];
      if (answer.results.length === 0 || items.length >= answer.count) return items;
    }
  };
  const read = async () => {
    setReading(true);
    try {
      const keys = props.fields.map((field) => field.key);
      const found: Read = {};
      // (a few fields at a time: an entity can have a hundred)
      const next = async (): Promise<void> => {
        const key = keys.shift();
        if (key === undefined) return;
        found[key] = await all(key);
        return next();
      };
      await Promise.all(Array.from({ length: 6 }, next));
      props.onRead(found);
    } finally {
      setReading(false);
    }
  };
  return (
    <p class="mt-6 flex flex-wrap items-center gap-3 text-xs text-slate-600" data-testid="incoming-not-read">
      <span>{t("incoming_not_read", "{count} more refer to this and are not read yet", { count: props.left })}</span>
      <button
        type="button"
        class={[smallButtonClass, "text-slate-600 disabled:text-slate-400"]}
        disabled={reading()}
        onClick={() => void read()}
      >
        {t("incoming_read_all", "Read them all")}
      </button>
    </p>
  );
}
