// Management + Principal: set up classes, assign teachers, and manage rosters and waitlists.
// Teachers are real accounts (picked from a list, not typed). Adding a child searches existing
// students or creates a walk-in. Staff adds are approved when the Principal does them and
// pending (awaiting the Principal) when Management does.
import { useId, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  CircleCheck,
  Eye,
  EyeOff,
  GraduationCap,
  Hourglass,
  NotebookPen,
  Pencil,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { adminApi } from "../api/endpoints";
import { isPrincipal, useAuth } from "../auth/context";
import {
  ActionButton,
  Chip,
  ConfirmStrip,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  PageHeader,
  PeriodCard,
  PublishBadge,
  StatusPill,
} from "../components/ui";
import { useAction, useDebounced, useResource } from "../lib/hooks";
import { PERIODS, fullName, periodLabel, plural, priorityText, splitName } from "../lib/domain";
import { cx } from "../lib/cx";

const CAN_TEACH = ["teacher", "management", "principal"];
const fetchUsers = () => adminApi.users();

export default function ManageView({ notify }) {
  const { user } = useAuth();
  const classesRes = useResource(adminApi.classes, { interval: 10000 });
  const usersRes = useResource(fetchUsers, { interval: 0 });
  const { run, busy } = useAction(notify);
  const [collapsed, setCollapsed] = useState({});
  const [editingId, setEditingId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const principal = isPrincipal(user);

  if (classesRes.loading) return <LoadingState label="Loading classes…" />;
  if (!classesRes.data) return <ErrorState error={classesRes.error} onRetry={classesRes.reload} />;

  const classes = classesRes.data;
  const reload = classesRes.reload;
  const teachers = (usersRes.data ?? []).filter((u) => CAN_TEACH.includes(u.role) && u.is_active);

  const draftCount = classes.filter((c) => !c.published).length;
  const seatsHeld = classes.reduce((n, c) => n + c.seats_taken, 0);
  const pendingCount = classes.reduce((n, c) => n + c.roster.filter((r) => r.status === "pending").length, 0);
  const waitlistCount = classes.reduce((n, c) => n + c.waitlist_count, 0);

  return (
    <div className="page">
      <PageHeader
        eyebrow={principal ? "Principal" : "Management"}
        icon={ShieldCheck}
        title="Classes"
        description="Add classes, assign teachers, and manage rosters and waitlists. Changes save to the sheet right away and families are emailed when it affects them."
      />

      <div className="stat-row">
        <Stat value={classes.length} label="Classes on the sheet" />
        <Stat value={draftCount} label="Drafts (hidden)" />
        <Stat value={seatsHeld} label="Seats held" />
        <Stat value={pendingCount} label="Awaiting approval" />
        <Stat value={waitlistCount} label="On waitlists" />
      </div>

      <section className="panel" aria-labelledby="add-class-title">
        <div className="panel__header">
          <span className="panel__icon" aria-hidden="true">
            <Plus size={20} />
          </span>
          <div>
            <h2 id="add-class-title" className="panel__title">
              Add a class
            </h2>
            <p className="panel__subtitle">New classes are published to the sign-up sheet immediately.</p>
          </div>
        </div>
        <ClassForm
          teachers={teachers}
          busy={busy === "create"}
          submitLabel="Add to sheet"
          onSubmit={(values) =>
            run("create", () => adminApi.createClass(values), { success: (c) => `${c.name} was added to the sheet.`, after: reload })
          }
        />
      </section>

      <div className="section-heading">
        <h2 className="section-heading__title">Classes on the sheet ({classes.length})</h2>
        {draftCount > 0 && <span className="section-heading__meta">{plural(draftCount, "draft")} not visible to families</span>}
      </div>
      {classes.length === 0 && (
        <EmptyState icon={NotebookPen} title="No classes yet — add the first one above.">
          It'll appear on the sign-up sheet as soon as you save it.
        </EmptyState>
      )}

      <div className="period-grid">
        {PERIODS.map((period, i) => {
          // Server order: drafts first, then published, each by sort order.
          const items = classes.filter((c) => c.period === period);
          const drafts = items.filter((c) => !c.published).length;
          const siblings = (c) => items.filter((x) => x.published === c.published);
          return (
            <PeriodCard
              key={period}
              index={i + 1}
              period={period}
              title={periodLabel(period)}
              summary={plural(items.length, "class", "es")}
              empty={items.length === 0}
              collapsed={!!collapsed[period]}
              onToggle={() => setCollapsed((prev) => ({ ...prev, [period]: !prev[period] }))}
              badges={
                drafts > 0 && (
                  <span className="status-pill status-pill--draft">
                    <EyeOff size={12} aria-hidden="true" />
                    {plural(drafts, "draft")}
                  </span>
                )
              }
            >
              {items.length === 0 ? (
                <EmptyState size="compact" icon={NotebookPen} title="No classes in this period yet.">
                  Use the form above to add one.
                </EmptyState>
              ) : (
                <ul className="class-list">
                  {items.map((c) => {
                    const group = siblings(c);
                    const idx = group.findIndex((x) => x.id === c.id);
                    return editingId === c.id ? (
                      <li key={c.id} className="admin-card admin-card--editing">
                        <ClassForm
                          teachers={teachers}
                          initial={c}
                          busy={busy === `save-${c.id}`}
                          submitLabel="Save changes"
                          onCancel={() => setEditingId(null)}
                          onSubmit={async (values) => {
                            const changes = diff(c, values);
                            if (Object.keys(changes).length === 0) return setEditingId(null);
                            const ok = await run(`save-${c.id}`, () => adminApi.updateClass(c.id, changes), { success: "Class updated.", after: reload });
                            if (ok) setEditingId(null);
                            return ok;
                          }}
                        />
                      </li>
                    ) : (
                      <AdminClassCard
                        key={c.id}
                        cls={c}
                        canUp={idx > 0}
                        canDown={idx < group.length - 1}
                        busy={busy}
                        run={run}
                        reload={reload}
                        principal={principal}
                        confirmingDelete={confirmDeleteId === c.id}
                        setConfirmDelete={(on) => setConfirmDeleteId(on ? c.id : null)}
                        onEdit={() => {
                          setConfirmDeleteId(null);
                          setEditingId(c.id);
                        }}
                      />
                    );
                  })}
                </ul>
              )}
            </PeriodCard>
          );
        })}
      </div>
    </div>
  );
}

// Only send what changed (the server treats teacher_id specially: a new teacher locks the claim).
function diff(cls, values) {
  const out = {};
  if (values.name !== cls.name) out.name = values.name;
  if (values.description !== cls.description) out.description = values.description;
  if (values.period !== cls.period) out.period = values.period;
  if (values.capacity !== cls.capacity) out.capacity = values.capacity;
  if (values.teacher_id !== (cls.teacher?.id ?? null)) out.teacher_id = values.teacher_id;
  return out;
}

function ClassForm({ teachers, initial, onSubmit, onCancel, busy, submitLabel }) {
  const [form, setForm] = useState(() => ({
    name: initial?.name ?? "",
    period: initial?.period ?? "1",
    capacity: String(initial?.capacity ?? 10),
    teacher_id: initial?.teacher?.id ? String(initial.teacher.id) : "",
    description: initial?.description ?? "",
  }));
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const capacity = Number(form.capacity);
  const valid = form.name.trim() && capacity >= 1 && capacity <= 500;
  // Keep the current teacher selectable even if their account is no longer in the list.
  const options = initial?.teacher && !teachers.some((t) => t.id === initial.teacher.id) ? [...teachers, { id: initial.teacher.id, first_name: initial.teacher.label, last_name: "", role: "teacher" }] : teachers;

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (!valid) return;
        const ok = await onSubmit({
          name: form.name.trim(),
          period: form.period,
          capacity,
          teacher_id: form.teacher_id ? Number(form.teacher_id) : null,
          description: form.description.trim(),
        });
        if (ok && !initial) setForm((f) => ({ ...f, name: "", description: "", teacher_id: "" }));
      }}
    >
      <div className="form-grid">
        <Field label="Class name" className="form-grid__name">
          <input className="input" placeholder="Class name" value={form.name} onChange={set("name")} maxLength={120} />
        </Field>
        <Field label="Period">
          <select className="input" value={form.period} onChange={set("period")}>
            {PERIODS.map((p) => (
              <option key={p} value={p}>
                {periodLabel(p)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Seats">
          <input className="input" type="number" min={1} max={500} value={form.capacity} onChange={set("capacity")} />
        </Field>
        <Field label="Teacher" optional className="form-grid__full" hint="Only staff accounts can teach. Assigned teachers can't drop the class themselves.">
          <select className="input" value={form.teacher_id} onChange={set("teacher_id")}>
            <option value="">No teacher yet</option>
            {options.map((t) => (
              <option key={t.id} value={t.id}>
                {fullName(t).trim()}
                {t.role !== "teacher" ? ` (${t.role})` : ""}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Description" optional className="form-grid__full">
          <textarea className="input" placeholder="Short description" value={form.description} onChange={set("description")} maxLength={2000} />
        </Field>
      </div>
      <div className="panel__footer">
        <ActionButton type="submit" className="btn btn--primary" busy={busy} disabled={!valid}>
          {initial ? <CircleCheck size={16} aria-hidden="true" /> : <Plus size={16} aria-hidden="true" />}
          {submitLabel}
        </ActionButton>
        {onCancel && (
          <button type="button" className="btn btn--ghost" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

function AdminClassCard({ cls: c, canUp, canDown, busy, run, reload, principal, confirmingDelete, setConfirmDelete, onEdit }) {
  const move = (direction) => run(`move-${c.id}`, () => adminApi.moveClass(c.id, direction), { after: reload });
  const heldBy = c.roster.length;

  return (
    <li className={cx("admin-card", !c.published && "admin-card--draft")}>
      <div className="admin-card__header">
        <div className="admin-card__heading">
          <h3 className="admin-card__title">{c.name}</h3>
          <div className="admin-card__tags">
            <PublishBadge published={c.published} />
          </div>
        </div>
        <div className="admin-card__toolbar">
          <button type="button" className="icon-btn" onClick={() => move("up")} disabled={!canUp || busy === `move-${c.id}`} aria-label={`Move ${c.name} up`}>
            <ArrowUp size={16} />
          </button>
          <button type="button" className="icon-btn" onClick={() => move("down")} disabled={!canDown || busy === `move-${c.id}`} aria-label={`Move ${c.name} down`}>
            <ArrowDown size={16} />
          </button>
          <span className="toolbar-divider" aria-hidden="true" />
          <button type="button" className="icon-btn" onClick={onEdit} aria-label={`Edit ${c.name}`}>
            <Pencil size={16} />
          </button>
          <button type="button" className="icon-btn icon-btn--danger" onClick={() => setConfirmDelete(true)} aria-label={`Delete ${c.name}`} aria-expanded={confirmingDelete}>
            <Trash2 size={16} />
          </button>
          <ActionButton
            className="btn btn--ghost btn--sm"
            busy={busy === `publish-${c.id}`}
            onClick={() =>
              run(`publish-${c.id}`, () => adminApi.updateClass(c.id, { published: !c.published }), {
                success: c.published ? "Class unpublished." : "Class published.",
                after: reload,
              })
            }
          >
            {c.published ? <EyeOff size={14} aria-hidden="true" /> : <Eye size={14} aria-hidden="true" />}
            {c.published ? "Unpublish" : "Publish"}
          </ActionButton>
        </div>
      </div>

      {confirmingDelete && (
        <ConfirmStrip
          title={`Delete “${c.name}”?`}
          body={`${
            heldBy || c.waitlist_count
              ? `This also removes ${[heldBy && plural(heldBy, "enrolled student"), c.waitlist_count && `${c.waitlist_count} on the waitlist`].filter(Boolean).join(" and ")}, and their families are emailed. `
              : ""
          }This can't be undone.`}
          confirmLabel="Delete class"
          busy={busy === `delete-${c.id}`}
          onCancel={() => setConfirmDelete(false)}
          onConfirm={() => run(`delete-${c.id}`, () => adminApi.deleteClass(c.id), { success: "Class removed.", after: reload })}
        />
      )}

      {c.description && <p className="admin-card__desc">{c.description}</p>}

      <dl className="admin-rows">
        <div className="admin-row">
          <dt>
            <GraduationCap size={14} aria-hidden="true" />
            Teacher
          </dt>
          <dd>
            {c.teacher ? (
              <div>
                <Chip
                  label={`${c.teacher.label}${c.teacher_locked ? " (assigned)" : " (claimed)"}`}
                  title={c.teacher.email}
                  removeLabel={`Remove teacher ${c.teacher.label}`}
                  busy={busy === `unassign-${c.id}`}
                  onRemove={() => run(`unassign-${c.id}`, () => adminApi.unassignTeacher(c.id), { success: "Teacher removed from class.", after: reload })}
                />
              </div>
            ) : (
              <span className="admin-row__empty">No teacher yet — sign-ups open once one is assigned or claims it.</span>
            )}
          </dd>
        </div>

        <div className="admin-row">
          <dt>
            <Users size={14} aria-hidden="true" />
            Students{" "}
            <span className="admin-row__count">
              {c.seats_taken}/{c.capacity}
            </span>
          </dt>
          <dd>
            {c.roster.length === 0 ? (
              <span className="admin-row__empty">None yet</span>
            ) : (
              <ul className="chip-list">
                {c.roster.map((r) => (
                  <li key={r.enrollment_id} className="roster__entry">
                    <Chip
                      label={`${r.first_name} ${r.last_name}`}
                      tone={r.status === "pending" ? "pending" : undefined}
                      title={r.family ? `${fullName(r.family)} · ${r.family.email}${r.family.phone ? ` · ${r.family.phone}` : ""}` : "Walk-in (no family account)"}
                      busy={busy === `kick-${r.enrollment_id}`}
                      onRemove={() =>
                        run(`kick-${r.enrollment_id}`, () => adminApi.removeEnrollment(r.enrollment_id), {
                          success: `${r.first_name} ${r.last_name} was removed from the class.`,
                          after: reload,
                        })
                      }
                    />
                    {r.status === "pending" && <StatusPill status="pending" short />}
                  </li>
                ))}
              </ul>
            )}
            {c.seats_available > 0 && (
              <StudentPicker
                classLabel={c.name}
                busy={busy === `add-${c.id}`}
                onPick={(student) =>
                  run(`add-${c.id}`, () => adminApi.enroll(c.id, student.id), {
                    success: (res) =>
                      res.status === "approved"
                        ? `${student.first_name} ${student.last_name} was added.`
                        : `${student.first_name} ${student.last_name} was added — pending the Principal's approval.`,
                    after: reload,
                  })
                }
                onCreate={(first, last) =>
                  run(`add-${c.id}`, async () => {
                    const s = await adminApi.createStudent(first, last);
                    return adminApi.enroll(c.id, s.id);
                  }, {
                    success: (res) => `${first} ${last} was added as a walk-in${res?.status === "pending" ? " — pending the Principal's approval" : ""}.`,
                    after: reload,
                  })
                }
                principal={principal}
              />
            )}
          </dd>
        </div>

        {c.waitlist.length > 0 && (
          <div className="admin-row admin-row--waitlist">
            <dt>
              <Hourglass size={14} aria-hidden="true" />
              Waitlist <span className="admin-row__count">{c.waitlist.length}</span>
            </dt>
            <dd>
              <ul className="chip-list">
                {c.waitlist.map((w) => (
                  <li key={w.entry_id}>
                    <Chip
                      tone="waitlist"
                      label={`#${w.position} ${w.first_name} ${w.last_name}${w.priority ? " • " + priorityText(w.priority) : ""}`}
                      title={w.family ? `${fullName(w.family)} · ${w.family.email}` : undefined}
                      removeLabel={`Remove ${w.first_name} ${w.last_name} from the waitlist`}
                      busy={busy === `wl-${w.entry_id}`}
                      onRemove={() =>
                        run(`wl-${w.entry_id}`, () => adminApi.removeWaitlist(w.entry_id), {
                          success: `${w.first_name} ${w.last_name} was removed from the waitlist.`,
                          after: reload,
                        })
                      }
                    />
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        )}
      </dl>
    </li>
  );
}

// Search existing children (name or family email); or create a walk-in student by full name.
function StudentPicker({ classLabel, onPick, onCreate, busy, principal }) {
  const [q, setQ] = useState("");
  const debounced = useDebounced(q.trim(), 250);
  const searching = debounced.length >= 2;
  const fetcher = useMemo(() => () => adminApi.students(debounced), [debounced]);
  const results = useResource(fetcher, { interval: 0, enabled: searching });
  const listId = useId();
  const name = splitName(q);
  const list = searching ? (results.data ?? []).slice(0, 6) : [];
  const exact = name && list.some((s) => `${s.first_name} ${s.last_name}`.toLowerCase() === q.trim().toLowerCase());

  const done = () => setQ("");

  return (
    <div className="picker">
      <div className="input-group input-group--trailing">
        <Search className="input-group__icon" size={16} aria-hidden="true" />
        <input
          className="input input--sm"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Add a student — search name or family email"
          aria-label={`Add a student to ${classLabel}`}
          aria-controls={listId}
          aria-expanded={q.trim().length > 0}
          autoComplete="off"
          disabled={busy}
        />
      </div>
      {q.trim().length > 0 && (
        <ul className="picker__list" id={listId} role="listbox" aria-label="Matching students">
          {list.map((s) => (
            <li key={s.id} role="option" aria-selected="false">
              <button
                type="button"
                className="picker__option"
                disabled={busy}
                onClick={async () => {
                  if (await onPick(s)) done();
                }}
              >
                <span className="picker__name">
                  {s.first_name} {s.last_name}
                </span>
                <span className="picker__meta">
                  {s.family ? s.family.email : "Walk-in"} · {plural(s.active_enrollments, "class", "es")}
                </span>
              </button>
            </li>
          ))}
          {searching && results.loading && <li className="picker__hint">Searching…</li>}
          {searching && !results.loading && list.length === 0 && !name && <li className="picker__hint">No students match.</li>}
          {!searching && !name && <li className="picker__hint">Type at least 2 letters.</li>}
          {name && !exact && (
            <li>
              <button
                type="button"
                className="picker__option picker__option--create"
                disabled={busy}
                onClick={async () => {
                  if (await onCreate(name[0], name[1])) done();
                }}
              >
                <UserPlus size={15} aria-hidden="true" />
                <span className="picker__name">
                  Add “{name[0]} {name[1]}” as a new walk-in student
                </span>
                <span className="picker__meta">No family account{principal ? "" : " · pending approval"}</span>
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}


function Stat({ value, label }) {
  return (
    <div className="stat">
      <span className="stat__value">{value}</span>
      <span className="stat__label">{label}</span>
    </div>
  );
}
