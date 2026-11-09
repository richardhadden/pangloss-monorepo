import { ApiError, badgeClass, buttonClass, Modal, problemsOf, tableCellClass, tableClass, tableHeadCellClass, tableHeadRowClass, tableRowClass, useApi, useComponent, useCurrentUser, useTranslations, whileVisible } from "@pangloss/interface-core";
import { invoke } from "@solidjs/web/server-functions";
import { createSignal, Errored, For, Loading, onSettled, Show, untrack } from "solid-js";
import { endSessions, setPassword } from "../api";
import { tokensFeed, usersFeed } from "../feed";
import { createTokensAdmin, createUsersAdmin } from "../state";
import type { ShownUser, UsersAdmin } from "../state";

const reasonOf = (error: unknown) =>
  error instanceof ApiError ? problemsOf(error).join("; ") : error instanceof Error ? error.message : String(error);

const button = buttonClass("ordinary");
// (the actions in each row of the table: quiet, so that the rows are not a wall of buttons)
const rowButton = buttonClass("quiet");
const input = "w-full rounded-xs border-[0.5px] border-slate-400/70 bg-white px-2 py-1 text-sm";
const label = "block text-xs font-semibold uppercase";

function Refused(props: { reason: string | undefined }) {
  return (
    <Show when={props.reason}>
      <p class="mb-3 text-sm text-red-700" role="alert">
        {props.reason}
      </p>
    </Show>
  );
}

/** A password and the same again (as the command line asks) */
function PasswordFields(props: { password: () => string; setPassword: (value: string) => void; repeat: () => string; setRepeat: (value: string) => void }) {
  const { t } = useTranslations();
  return (
    <>
      <label class={label}>
        {t("users_password", "Password")}
        <input
          class={input}
          type="password"
          autocomplete="new-password"
          required
          value={props.password()}
          onInput={(event) => props.setPassword(event.currentTarget.value)}
        />
      </label>
      <label class={label}>
        {t("users_password_repeat", "Password again")}
        <input
          class={input}
          type="password"
          autocomplete="new-password"
          required
          value={props.repeat()}
          onInput={(event) => props.setRepeat(event.currentTarget.value)}
        />
      </label>
    </>
  );
}

function DialogButtons(props: { onCancel: () => void; submit: string; busy: boolean }) {
  const { t } = useTranslations();
  return (
    <div class="flex justify-end gap-2 pt-2">
      <button type="button" class={buttonClass("ordinary", "md")} onClick={() => props.onCancel()}>
        {t("users_cancel", "Cancel")}
      </button>
      <button type="submit" class={buttonClass("primary", "md")} disabled={props.busy}>
        {props.submit}
      </button>
    </div>
  );
}

function NewUserDialog(props: { users: UsersAdmin; onClose: () => void }) {
  const { t } = useTranslations();
  const [username, setUsername] = createSignal("");
  const [email, setEmail] = createSignal("");
  const [fullName, setFullName] = createSignal("");
  const [password, setPasswordValue] = createSignal("");
  const [repeat, setRepeat] = createSignal("");
  const [admin, setAdminValue] = createSignal(false);
  const [busy, setBusy] = createSignal(false);
  const [refused, setRefused] = createSignal<string | undefined>();
  return (
    <Modal title={t("users_new", "New user")} onClose={props.onClose}>
      <form
        class="space-y-3 p-4"
        data-testid="users-admin-new-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (password() !== repeat()) {
            setRefused(t("users_passwords_differ", "The two passwords are not the same"));
            return;
          }
          setBusy(true);
          // (the row is shown at once; the dialog stays until the API has accepted it, to say why if it does not)
          props.users
            .add(
              {
                username: username(),
                email: email(),
                password: password(),
                fullName: fullName() || null,
                admin: admin(),
              },
              () => props.onClose(),
            )
            .catch((error) => {
              setRefused(reasonOf(error));
              setBusy(false);
            });
        }}
      >
        <Refused reason={refused()} />
        <label class={label}>
          {t("users_username", "Username")}
          <input class={input} required value={username()} onInput={(event) => setUsername(event.currentTarget.value)} />
        </label>
        <label class={label}>
          {t("users_email", "Email")}
          <input class={input} type="email" required value={email()} onInput={(event) => setEmail(event.currentTarget.value)} />
        </label>
        <label class={label}>
          {t("users_full_name", "Full name")}
          <input class={input} value={fullName()} onInput={(event) => setFullName(event.currentTarget.value)} />
        </label>
        <PasswordFields password={password} setPassword={setPasswordValue} repeat={repeat} setRepeat={setRepeat} />
        <label class="flex items-center gap-1.5 text-sm">
          <input type="checkbox" checked={admin()} onChange={(event) => setAdminValue(event.currentTarget.checked)} />
          {t("users_is_admin", "Admin")}
        </label>
        <DialogButtons onCancel={props.onClose} submit={t("users_create", "Create")} busy={busy()} />
      </form>
    </Modal>
  );
}

function SetPasswordDialog(props: { username: string; onDone: () => void; onClose: () => void }) {
  const api = useApi();
  const { t } = useTranslations();
  const username = untrack(() => props.username);
  const [password, setPasswordValue] = createSignal("");
  const [repeat, setRepeat] = createSignal("");
  const [busy, setBusy] = createSignal(false);
  const [refused, setRefused] = createSignal<string | undefined>();
  return (
    <Modal title={t("users_set_password_of", "Set the password of {username}", { username })} onClose={props.onClose}>
      <form
        class="space-y-3 p-4"
        data-testid="users-admin-password-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (password() !== repeat()) {
            setRefused(t("users_passwords_differ", "The two passwords are not the same"));
            return;
          }
          setBusy(true);
          setPassword(api, username, password())
            .then(() => props.onDone())
            .catch((error) => {
              setRefused(reasonOf(error));
              setBusy(false);
            });
        }}
      >
        <Refused reason={refused()} />
        <p class="text-sm text-slate-600">{t("users_password_ends_sessions", "This ends all the user's sessions.")}</p>
        <PasswordFields password={password} setPassword={setPasswordValue} repeat={repeat} setRepeat={setRepeat} />
        <DialogButtons onCancel={props.onClose} submit={t("users_set_password", "Set password")} busy={busy()} />
      </form>
    </Modal>
  );
}

function TokensContents(props: { username: string }) {
  const api = useApi();
  const { t, language } = useTranslations();
  const username = untrack(() => props.username);
  const tokens = createTokensAdmin({
    username,
    api,
    feed: (signal) =>
      whileVisible((connection) => invoke(tokensFeed, { signal: connection }, username), signal),
  });
  const view = tokens.view;
  const [name, setName] = createSignal("");
  const [scope, setScope] = createSignal<"read" | "write">("write");
  const [days, setDays] = createSignal("");
  const [made, setMade] = createSignal<string | undefined>();
  const [refused, setRefused] = createSignal<string | undefined>();
  const date = (when: string) => new Date(when).toLocaleDateString(language());
  return (
    <div class="p-4" data-testid="users-admin-tokens">
      <Refused reason={refused()} />
      <Show when={made()}>
        <div class="mb-3 border-[0.5px] border-amber-400 bg-amber-50 p-2 text-sm">
          <p class="mb-1">{t("users_token_once", "Keep this now: it cannot be shown again.")}</p>
          <code class="break-all select-all" data-testid="users-admin-new-token">
            {made()}
          </code>
        </div>
      </Show>
      <Show
        when={view.items.length > 0 || !view.ready}
        fallback={<p class="py-2 text-sm text-slate-500">{t("users_tokens_none", "No tokens")}</p>}
      >
        <ul class="mb-3">
          <For each={view.items} keyed={(token) => token.id}>
            {(token) => (
              <li
                class="flex items-center gap-3 border-b-[0.5px] border-slate-300 py-1.5 text-sm"
                data-testid="users-admin-token"
              >
                <span class="font-medium">{token().name}</span>
                <span class="text-xs text-slate-600 uppercase">
                  {token().scope === "read" ? t("users_token_read", "Read") : t("users_token_write", "Write")}
                </span>
                <span class="text-xs text-slate-600">
                  <Show when={token().expiresWhen} fallback={t("users_token_no_expiry", "No expiry")}>
                    {(when) => t("users_token_expires", "Expires {date}", { date: date(when()) })}
                  </Show>
                  {" · "}
                  <Show when={token().lastUsedWhen} fallback={t("users_token_never_used", "Never used")}>
                    {(when) => t("users_token_last_used", "Last used {date}", { date: date(when()) })}
                  </Show>
                </span>
                <button
                  type="button"
                  class={`${button} ml-auto`}
                  disabled={token().pending}
                  onClick={() => tokens.revoke(token().id).catch((error) => setRefused(reasonOf(error)))}
                >
                  {t("users_token_revoke", "Revoke")}
                </button>
              </li>
            )}
          </For>
        </ul>
      </Show>
      <form
        class="grid grid-cols-[1fr_auto_6rem_auto] items-end gap-2"
        data-testid="users-admin-token-form"
        onSubmit={(event) => {
          event.preventDefault();
          setRefused(undefined);
          const form = event.currentTarget;
          tokens
            .create({ name: name(), scope: scope(), expiresDays: Number(days()) || null }, (token) => {
              setMade(token);
              setName("");
              setDays("");
              form.reset();
            })
            .catch((error) => setRefused(reasonOf(error)));
        }}
      >
        <label class={label}>
          {t("users_token_name", "What is it for?")}
          <input class={input} required value={name()} onInput={(event) => setName(event.currentTarget.value)} />
        </label>
        <label class={label}>
          {t("users_token_scope", "Scope")}
          <select
            class={input}
            value={scope()}
            onChange={(event) => setScope(event.currentTarget.value as "read" | "write")}
          >
            <option value="write" textContent={t("users_token_write", "Write")} />
            <option value="read" textContent={t("users_token_read", "Read")} />
          </select>
        </label>
        <label class={label}>
          {t("users_token_days", "Days")}
          <input class={input} type="number" min="1" value={days()} onInput={(event) => setDays(event.currentTarget.value)} />
        </label>
        <button type="submit" class={button}>
          {t("users_create", "Create")}
        </button>
      </form>
    </div>
  );
}

function TokensDialog(props: { username: string; onClose: () => void }) {
  const ErrorMessage = useComponent("ErrorMessage");
  const { t } = useTranslations();
  return (
    <Modal title={t("users_tokens_of", "Tokens of {username}", { username: props.username })} onClose={props.onClose} size="lg">
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>}>
          <TokensContents username={props.username} />
        </Loading>
      </Errored>
    </Modal>
  );
}

function Flag(props: { on: boolean; text: string; class: string }) {
  return (
    <Show when={props.on}>
      <span class={[badgeClass, "mr-1", props.class]}>{props.text}</span>
    </Show>
  );
}

/** An email or full name, sent when it is left or Enter is pressed. (An empty one is none) */
function Detail(props: {
  name: string;
  type: string;
  value: string | null | undefined;
  save: (value: string | null) => Promise<unknown>;
  onRefused: (reason: string) => void;
}) {
  return (
    <input
      class="-ml-1 w-full rounded-xs border-[0.5px] border-transparent bg-transparent px-1 py-0.5 text-sm hover:border-slate-300 focus:border-slate-400 focus:bg-white"
      type={props.type}
      aria-label={props.name}
      value={props.value ?? ""}
      onChange={(event) => {
        const field = event.currentTarget;
        const before = untrack(() => props.value) ?? "";
        props.save(field.value.trim() || null).catch((error) => {
          // (the store goes back by itself; this is what was typed over it)
          field.value = before;
          props.onRefused(reasonOf(error));
        });
      }}
    />
  );
}

function UserRow(props: { user: ShownUser; users: UsersAdmin; me: boolean; onRefused: (reason: string | undefined) => void }) {
  const api = useApi();
  const { t, language } = useTranslations();
  const [settingPassword, setSettingPassword] = createSignal(false);
  const [showingTokens, setShowingTokens] = createSignal(false);
  const refuse = (error: unknown) => props.onRefused(reasonOf(error));
  // (ending your own sessions logs you out: the page then asks for a login)
  const afterEndingSessions = () => {
    if (untrack(() => props.me)) window.location.assign("/admin");
  };
  const yourself = () => (props.me ? t("users_yourself", "You cannot change this for yourself") : undefined);
  const created = () => (props.user.createdWhen ? new Date(props.user.createdWhen).toLocaleDateString(language()) : "");
  const username = () => props.user.username;
  return (
    <tr
      class={[tableRowClass, { "opacity-50": props.user.pending }]}
      data-testid="users-admin-row"
      data-username={username()}
      data-admin={String(props.user.admin)}
      data-disabled={String(props.user.disabled)}
    >
      <td class={[tableCellClass, "font-medium"]}>
        <a class="hover:underline" href={`/users/${encodeURIComponent(username())}`}>
          {username()}
        </a>
      </td>
      <td class={tableCellClass}>
        <Detail
          name={t("users_full_name", "Full name")}
          type="text"
          value={props.user.fullName}
          save={(fullName) => props.users.update(username(), { fullName })}
          onRefused={props.onRefused}
        />
      </td>
      <td class={tableCellClass}>
        <Detail
          name={t("users_email", "Email")}
          type="email"
          value={props.user.email}
          save={(email) => props.users.update(username(), { email })}
          onRefused={props.onRefused}
        />
      </td>
      <td class={[tableCellClass, "whitespace-nowrap"]}>
        <Flag on={props.user.admin} text={t("users_is_admin", "Admin")} class="bg-slate-200 text-slate-800" />
        <Flag on={props.user.disabled} text={t("users_is_disabled", "Disabled")} class="bg-red-100 text-red-800" />
      </td>
      <td class={[tableCellClass, "whitespace-nowrap text-slate-600"]}>{created()}</td>
      <td class={[tableCellClass, "text-right whitespace-nowrap"]}>
        <div class="flex justify-end gap-1">
          <button
            type="button"
            class={rowButton}
            disabled={props.me || props.user.pending}
            title={yourself()}
            onClick={() => props.users.setAdmin(username(), !props.user.admin).catch(refuse)}
          >
            <Show when={props.user.admin} fallback={t("users_make_admin", "Make admin")}>
              {t("users_remove_admin", "Remove admin")}
            </Show>
          </button>
          <button
            type="button"
            class={rowButton}
            disabled={props.me || props.user.pending}
            title={yourself()}
            onClick={() => props.users.setDisabled(username(), !props.user.disabled).catch(refuse)}
          >
            <Show when={props.user.disabled} fallback={t("users_disable", "Disable")}>
              {t("users_enable", "Enable")}
            </Show>
          </button>
          <button type="button" class={rowButton} disabled={props.user.pending} onClick={() => setSettingPassword(true)}>
            {t("users_password", "Password")}
          </button>
          <button
            type="button"
            class={rowButton}
            disabled={props.user.pending}
            onClick={() => endSessions(api, username()).then(afterEndingSessions).catch(refuse)}
          >
            {t("users_end_sessions", "End sessions")}
          </button>
          <button type="button" class={rowButton} disabled={props.user.pending} onClick={() => setShowingTokens(true)}>
            {t("users_tokens", "Tokens")}
          </button>
        </div>
        <Show when={settingPassword()}>
          <SetPasswordDialog
            username={username()}
            onDone={() => {
              setSettingPassword(false);
              afterEndingSessions();
            }}
            onClose={() => setSettingPassword(false)}
          />
        </Show>
        <Show when={showingTokens()}>
          <TokensDialog username={username()} onClose={() => setShowingTokens(false)} />
        </Show>
      </td>
    </tr>
  );
}

function UsersContents() {
  const api = useApi();
  const { t } = useTranslations();
  const users = createUsersAdmin({
    api,
    feed: (signal) =>
      whileVisible((connection) => invoke(usersFeed, { signal: connection }), signal),
  });
  const view = users.view;
  const me = () => useCurrentUser()?.username;
  const [adding, setAdding] = createSignal(false);
  const [refused, setRefused] = createSignal<string | undefined>();
  return (
    <>
      <Refused reason={refused()} />
      <div class="mb-2 flex justify-end">
        <button type="button" class={button} onClick={() => setAdding(true)}>
          {t("users_new", "New user")}
        </button>
      </div>
      <table class={tableClass}>
        <thead>
          <tr class={tableHeadRowClass}>
            <th class={tableHeadCellClass}>{t("users_username", "Username")}</th>
            <th class={tableHeadCellClass}>{t("users_full_name", "Full name")}</th>
            <th class={tableHeadCellClass}>{t("users_email", "Email")}</th>
            <th class={tableHeadCellClass}>{t("users_status", "Status")}</th>
            <th class={tableHeadCellClass}>{t("users_created", "Created")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <For each={view.items} keyed={(user) => user.username}>
            {(user) => <UserRow user={user()} users={users} me={user().username === me()} onRefused={setRefused} />}
          </For>
        </tbody>
      </table>
      <Show when={adding()}>
        <NewUserDialog users={users} onClose={() => setAdding(false)} />
      </Show>
    </>
  );
}

/** Managing users, a part of `/admin`: all that `pangloss users` does. A change is shown at once (optimistically) and what is shown otherwise comes from a live feed */
export default function UsersAdminSection() {
  const ErrorMessage = useComponent("ErrorMessage");
  const { t } = useTranslations();
  // (the feed is opened only in the browser: the server would send a first answer, and the browser would not open it again)
  const [inBrowser, setInBrowser] = createSignal(false);
  onSettled(() => {
    setInBrowser(true);
  });
  const loading = <p class="text-sm text-slate-500">{t("loading", "Loading…")}</p>;
  return (
    <section data-testid="admin-users">
      <h2 class="mb-3 text-sm font-semibold uppercase">{t("users", "Users")}</h2>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Show when={inBrowser()} fallback={loading}>
          <Loading fallback={loading}>
            <UsersContents />
          </Loading>
        </Show>
      </Errored>
    </section>
  );
}
