// A family's dashboard: each child, their class requests with approval status, and their
// waitlist places. Backed by GET /me/overview (polled, so approvals show up on their own).
import { useState } from "react";
import { ArrowRight, BookOpen, Check, Hourglass, Pencil, Trash2, Users, X } from "lucide-react";
import { familyApi } from "../api/endpoints";
import { ActionButton, ConfirmStrip, CrownBadge, EmptyState, ErrorState, LoadingState, PageHeader, PeriodMedallion, StatusPill } from "../components/ui";
import { useAction, useResource } from "../lib/hooks";
import { formatDate, nextPriority, periodLabel } from "../lib/domain";
import AddChildForm from "../components/AddChildForm";

export default function ChildrenView({ notify, navigate }) {
  const overview = useResource(familyApi.overview);
  const { run, busy } = useAction(notify);

  if (overview.loading) return <LoadingState label="Loading your children…" />;
  if (!overview.data) return <ErrorState error={overview.error} onRetry={overview.reload} />;

  const students = overview.data.students;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Family"
        icon={Users}
        title="My children"
        description="Each child's classes and where they stand. Requests stay pending until the Principal approves them — you'll get an email either way."
        actions={
          <button type="button" className="btn btn--primary" onClick={() => navigate("")}>
            <BookOpen size={16} aria-hidden="true" />
            Sign-up sheet
          </button>
        }
      />

      {students.length === 0 ? (
        <EmptyState icon={Users} title="No children yet">
          Add your first child below, then pick their classes on the sign-up sheet.
        </EmptyState>
      ) : (
        <div className="child-grid">
          {students.map((s) => (
            <ChildCard key={s.id} student={s} run={run} busy={busy} reload={overview.reload} navigate={navigate} />
          ))}
        </div>
      )}

      <section className="panel add-child-panel" aria-label="Add a child">
        <h2 className="panel__title">Add a child</h2>
        <AddChildForm
          busy={busy === "add-child"}
          onSubmit={async (first, last) =>
            !!(await run("add-child", () => familyApi.addStudent(first, last), { success: `${first} was added.`, after: overview.reload }))
          }
        />
      </section>
    </div>
  );
}

function ChildCard({ student: s, run, busy, reload, navigate }) {
  const [editing, setEditing] = useState(false);
  const [first, setFirst] = useState(s.first_name);
  const [last, setLast] = useState(s.last_name);
  const [confirming, setConfirming] = useState(false);
  const hasClasses = s.enrollments.length > 0 || s.waitlist.length > 0;

  const save = () =>
    run(`rename-${s.id}`, () => familyApi.updateStudent(s.id, { first_name: first.trim(), last_name: last.trim() }), {
      success: "Name updated.",
      after: () => {
        setEditing(false);
        reload();
      },
    });

  return (
    <article className="child-card">
      <header className="child-card__head">
        <span className="child-card__avatar" aria-hidden="true">
          {s.first_name[0]}
          {s.last_name[0]}
        </span>
        {editing ? (
          <form
            className="child-card__rename"
            onSubmit={(e) => {
              e.preventDefault();
              save();
            }}
          >
            <input className="input input--sm" value={first} onChange={(e) => setFirst(e.target.value)} aria-label="First name" autoFocus />
            <input className="input input--sm" value={last} onChange={(e) => setLast(e.target.value)} aria-label="Last name" />
            <ActionButton type="submit" className="icon-btn" busy={busy === `rename-${s.id}`} disabled={!first.trim() || !last.trim()} aria-label="Save name">
              <Check size={16} />
            </ActionButton>
            <button type="button" className="icon-btn" onClick={() => setEditing(false)} aria-label="Cancel">
              <X size={16} />
            </button>
          </form>
        ) : (
          <>
            <h2 className="child-card__name">
              {s.first_name} {s.last_name}
            </h2>
            <div className="child-card__tools">
              <button type="button" className="icon-btn" onClick={() => setEditing(true)} aria-label={`Rename ${s.first_name}`}>
                <Pencil size={16} />
              </button>
              <button type="button" className="icon-btn icon-btn--danger" onClick={() => setConfirming(true)} aria-label={`Remove ${s.first_name}`}>
                <Trash2 size={16} />
              </button>
            </div>
          </>
        )}
      </header>

      {confirming && (
        <ConfirmStrip
          title={`Remove ${s.first_name} ${s.last_name}?`}
          body={hasClasses ? "This also cancels their class requests and waitlist places. This can't be undone." : "This can't be undone."}
          confirmLabel="Remove child"
          busy={busy === `remove-${s.id}`}
          onCancel={() => setConfirming(false)}
          onConfirm={() => run(`remove-${s.id}`, () => familyApi.removeStudent(s.id), { success: `${s.first_name} was removed.`, after: reload })}
        />
      )}

      {!hasClasses ? (
        <div className="child-card__empty">
          <p>No classes yet.</p>
          <button type="button" className="btn btn--link" onClick={() => navigate("")}>
            Find a class
            <ArrowRight size={14} aria-hidden="true" />
          </button>
        </div>
      ) : (
        <ul className="child-rows">
          {s.enrollments.map((e) => (
            <li key={`e${e.id}`} className="child-row">
              <PeriodMedallion period={e.period} size="sm" />
              <div className="child-row__main">
                <p className="child-row__title">{e.class_name}</p>
                <p className="child-row__meta">
                  {periodLabel(e.period)} · requested {formatDate(e.created_at)}
                  {e.decided_at && e.status !== "pending" ? ` · decided ${formatDate(e.decided_at)}` : ""}
                </p>
                {e.status === "rejected" && e.rejection_reason && <p className="child-row__reason">“{e.rejection_reason}”</p>}
              </div>
              <div className="child-row__actions">
                <StatusPill status={e.status} short />
                <ActionButton
                  className={e.status === "rejected" ? "btn btn--ghost btn--sm" : "btn btn--danger-ghost btn--sm"}
                  busy={busy === `drop-${e.id}`}
                  onClick={() =>
                    run(`drop-${e.id}`, () => familyApi.drop(e.id), {
                      success: e.status === "rejected" ? "Dismissed." : `${s.first_name} was removed from ${e.class_name}.`,
                      after: reload,
                    })
                  }
                >
                  {e.status === "rejected" ? "Dismiss" : "Drop"}
                </ActionButton>
              </div>
            </li>
          ))}
          {s.waitlist.map((w) => (
            <li key={`w${w.id}`} className="child-row child-row--waitlist">
              <PeriodMedallion period={w.period} size="sm" />
              <div className="child-row__main">
                <p className="child-row__title">{w.class_name}</p>
                <p className="child-row__meta">
                  <Hourglass size={12} aria-hidden="true" /> Waitlist · #{w.position} of {w.size} in line · {periodLabel(w.period)}
                </p>
              </div>
              <div className="child-row__actions">
                <CrownBadge
                  priority={w.priority}
                  busy={busy === `prio-${w.id}`}
                  onClick={() => run(`prio-${w.id}`, () => familyApi.setPriority(w.id, nextPriority(w.priority)), { after: reload })}
                />
                <ActionButton
                  className="btn btn--danger-ghost btn--sm"
                  busy={busy === `leave-${w.id}`}
                  onClick={() => run(`leave-${w.id}`, () => familyApi.leaveWaitlist(w.id), { success: "Left the waitlist.", after: reload })}
                >
                  Leave
                </ActionButton>
              </div>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
