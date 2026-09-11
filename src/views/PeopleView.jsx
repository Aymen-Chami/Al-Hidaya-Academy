// Accounts. Management can look; only the Principal creates staff accounts, changes roles
// or deactivates people (the server enforces this). A prepared account is activated when the
// person signs up with that email — they keep the role set here.
import { useCallback, useId, useState } from "react";
import { MailPlus, ShieldAlert, UserPlus, Users } from "lucide-react";
import { adminApi } from "../api/endpoints";
import { ROLE_LABELS, isPrincipal, useAuth } from "../auth/context";
import { ActionButton, EmptyState, ErrorState, Field, LoadingState, PageHeader, SearchField, Segmented } from "../components/ui";
import { useAction, useDebounced, useResource } from "../lib/hooks";
import { formatDate, fullName } from "../lib/domain";
import { cx } from "../lib/cx";

const ROLES = ["family", "teacher", "management", "principal"];

export default function PeopleView({ notify }) {
  const { user } = useAuth();
  const principal = isPrincipal(user);
  const [role, setRole] = useState("all");
  const [query, setQuery] = useState("");
  const q = useDebounced(query.trim(), 250);
  const fetcher = useCallback(() => adminApi.users({ role: role === "all" ? undefined : role, q: q || undefined }), [role, q]);
  const res = useResource(fetcher, { interval: 0 });
  const { run, busy } = useAction(notify);
  const searchId = useId();

  return (
    <div className="page">
      <PageHeader
        eyebrow="People"
        icon={Users}
        title="Accounts"
        description="Families, teachers and staff. Add a teacher here, then they sign up with the same email to set a password."
      />

      {principal ? (
        <section className="panel" aria-labelledby="new-account-title">
          <div className="panel__header">
            <span className="panel__icon" aria-hidden="true">
              <UserPlus size={20} />
            </span>
            <div>
              <h2 id="new-account-title" className="panel__title">
                Add an account
              </h2>
              <p className="panel__subtitle">We'll email them an invitation to finish signing up.</p>
            </div>
          </div>
          <NewAccountForm
            busy={busy === "create"}
            onSubmit={(values) =>
              run("create", () => adminApi.createUser(values), {
                success: (u) => `${fullName(u)} was added as ${ROLE_LABELS[u.role].toLowerCase()}.`,
                after: res.reload,
              })
            }
          />
        </section>
      ) : (
        <p className="notice">
          <ShieldAlert size={18} aria-hidden="true" />
          Only the Principal can add accounts or change roles.
        </p>
      )}

      <div className="queue-toolbar">
        <Segmented
          label="Filter by role"
          options={[{ value: "all", label: "Everyone" }, ...ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] }))]}
          value={role}
          onChange={setRole}
        />
        <SearchField id={searchId} query={query} setQuery={setQuery} compact label="Search people" placeholder="Search name or email" />
      </div>

      {res.loading ? (
        <LoadingState label="Loading accounts…" />
      ) : !res.data ? (
        <ErrorState error={res.error} onRetry={res.reload} />
      ) : res.data.length === 0 ? (
        <EmptyState icon={Users} title="No accounts match">
          Try another name, email or role.
        </EmptyState>
      ) : (
        <ul className="people-list">
          {res.data.map((u) => (
            <li key={u.id} className={cx("person", !u.is_active && "person--inactive")}>
              <span className="person__avatar" aria-hidden="true">
                {u.first_name[0]}
                {u.last_name[0]}
              </span>
              <div className="person__main">
                <p className="person__name">
                  {fullName(u)}
                  {u.id === user.id && <span className="person__you">You</span>}
                </p>
                <p className="person__meta">
                  <a href={`mailto:${u.email}`}>{u.email}</a>
                  {u.phone ? ` · ${u.phone}` : ""} · joined {formatDate(u.created_at)}
                </p>
              </div>
              <div className="person__tags">
                {!u.activated && (
                  <span className="status-pill status-pill--warning" title="They haven't signed up with this email yet">
                    <MailPlus size={12} aria-hidden="true" />
                    Invited
                  </span>
                )}
                {!u.is_active && <span className="status-pill status-pill--neutral">Deactivated</span>}
              </div>
              <div className="person__controls">
                {principal && u.id !== user.id ? (
                  <>
                    <label className="sr-only" htmlFor={`role-${u.id}`}>
                      Role for {fullName(u)}
                    </label>
                    <select
                      id={`role-${u.id}`}
                      className="input input--sm"
                      value={u.role}
                      disabled={busy === `role-${u.id}`}
                      onChange={(e) =>
                        run(`role-${u.id}`, () => adminApi.updateUser(u.id, { role: e.target.value }), {
                          success: `${u.first_name} is now ${ROLE_LABELS[e.target.value].toLowerCase()}.`,
                          after: res.reload,
                        })
                      }
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABELS[r]}
                        </option>
                      ))}
                    </select>
                    <ActionButton
                      className={u.is_active ? "btn btn--danger-ghost btn--sm" : "btn btn--ghost btn--sm"}
                      busy={busy === `active-${u.id}`}
                      onClick={() =>
                        run(`active-${u.id}`, () => adminApi.updateUser(u.id, { is_active: !u.is_active }), {
                          success: u.is_active ? `${u.first_name} was deactivated and signed out.` : `${u.first_name} was reactivated.`,
                          after: res.reload,
                        })
                      }
                    >
                      {u.is_active ? "Deactivate" : "Reactivate"}
                    </ActionButton>
                  </>
                ) : (
                  <span className="status-pill status-pill--info">{ROLE_LABELS[u.role]}</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NewAccountForm({ onSubmit, busy }) {
  const empty = { email: "", first_name: "", last_name: "", role: "teacher", send_invite: true };
  const [form, setForm] = useState(empty);
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const valid = form.email.includes("@") && form.first_name.trim() && form.last_name.trim();

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (!valid) return;
        const created = await onSubmit({ ...form, email: form.email.trim(), first_name: form.first_name.trim(), last_name: form.last_name.trim() });
        if (created) setForm(empty);
      }}
    >
      <div className="form-grid form-grid--people">
        <Field label="Email" className="form-grid__name">
          <input className="input" type="email" value={form.email} onChange={set("email")} autoComplete="off" />
        </Field>
        <Field label="First name">
          <input className="input" value={form.first_name} onChange={set("first_name")} autoComplete="off" />
        </Field>
        <Field label="Last name">
          <input className="input" value={form.last_name} onChange={set("last_name")} autoComplete="off" />
        </Field>
        <Field label="Role">
          <select className="input" value={form.role} onChange={set("role")}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="panel__footer">
        <ActionButton type="submit" className="btn btn--primary" busy={busy} disabled={!valid}>
          <UserPlus size={16} aria-hidden="true" />
          Add account
        </ActionButton>
        <label className="checkbox">
          <input type="checkbox" checked={form.send_invite} onChange={set("send_invite")} />
          Email them an invitation
        </label>
      </div>
    </form>
  );
}
