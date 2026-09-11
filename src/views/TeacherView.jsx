// Teacher: see the classes you teach (with roster + waitlist), claim an unclaimed class
// (one per period), or give up a class you claimed yourself. Identity comes from the login.
import { useId, useState } from "react";
import { Armchair, ArrowRight, CircleCheck, GraduationCap, Hourglass, SearchX, Users } from "lucide-react";
import { catalogApi, teacherApi } from "../api/endpoints";
import { useAuth } from "../auth/context";
import { ActionButton, Chip, EmptyState, ErrorState, LoadingState, PageHeader, PeriodCard, PublishBadge, SearchField, StatusPill } from "../components/ui";
import { useAction, useResource } from "../lib/hooks";
import { PERIODS, periodLabel, plural, priorityText } from "../lib/domain";

export default function TeacherView({ notify }) {
  const { user } = useAuth();
  const mine = useResource(teacherApi.classes);
  const published = useResource(catalogApi.classes);
  const { run, busy } = useAction(notify);
  const [collapsed, setCollapsed] = useState({});
  const [query, setQuery] = useState("");
  const searchId = useId();

  if (mine.loading || published.loading) return <LoadingState label="Loading your classes…" />;
  if (!mine.data || !published.data) {
    return <ErrorState error={mine.error || published.error} onRetry={() => (mine.reload(), published.reload())} />;
  }

  const refresh = () => {
    mine.reload();
    published.reload();
  };
  const q = query.trim().toLowerCase();
  const matches = (c) => !q || [c.name, c.description].some((v) => v && v.toLowerCase().includes(q));

  return (
    <div className="page">
      <PageHeader
        eyebrow="Teacher"
        icon={GraduationCap}
        title={`Salaam, ${user.first_name}`}
        description="Claim one open class per period. Once you have a class, its roster and waitlist show up here and refresh on their own."
      />

      <section className="periods" aria-label="Periods">
        <div className="periods__header">
          <div>
            <h2 className="periods__title">Periods</h2>
            <p className="periods__sub">Tap a card to see its classes.</p>
          </div>
          <SearchField id={searchId} query={query} setQuery={setQuery} compact placeholder="Search unclaimed classes" label="Search unclaimed classes" />
        </div>

        <div className="period-grid">
          {PERIODS.map((p, i) => {
            const myClass = mine.data.find((c) => c.period === p);
            const unclaimed = published.data.filter((c) => c.period === p && !c.teacher);
            const shown = unclaimed.filter(matches);
            const summary = myClass ? `Teaching ${myClass.name}` : unclaimed.length ? plural(unclaimed.length, "unclaimed class", "es") : "No unclaimed classes";

            return (
              <PeriodCard
                key={p}
                index={i + 1}
                period={p}
                title={periodLabel(p)}
                summary={summary}
                empty={!myClass && unclaimed.length === 0}
                collapsed={!!collapsed[p]}
                onToggle={() => setCollapsed((prev) => ({ ...prev, [p]: !prev[p] }))}
                badges={
                  myClass && (
                    <span className="status-pill status-pill--success">
                      <CircleCheck size={12} aria-hidden="true" />
                      Claimed
                    </span>
                  )
                }
              >
                {myClass ? (
                  <MyClassCard cls={myClass} busy={busy} onDrop={() => run(`unclaim-${myClass.id}`, () => teacherApi.dropClaim(myClass.id), { success: "You gave up the class.", after: refresh })} />
                ) : unclaimed.length === 0 ? (
                  <EmptyState size="compact" icon={CircleCheck} title="No unclaimed classes this period.">
                    Every class here already has a teacher, or none have been added yet.
                  </EmptyState>
                ) : shown.length === 0 ? (
                  <EmptyState size="compact" icon={SearchX} title={`No matches for “${query.trim()}”`}>
                    Try another word, or clear the search.
                  </EmptyState>
                ) : (
                  <ul className="class-list">
                    {shown.map((c) => (
                      <li key={c.id} className="class-card">
                        <div className="class-card__main">
                          <h3 className="class-card__title">{c.name}</h3>
                          {c.description && <p className="class-card__desc">{c.description}</p>}
                          <div className="class-card__meta">
                            <span className="status-pill status-pill--neutral">Unclaimed</span>
                            <span className="meta">
                              <Armchair size={15} aria-hidden="true" />
                              {plural(c.capacity, "seat")}
                            </span>
                          </div>
                        </div>
                        <div className="class-card__actions">
                          <ActionButton
                            className="btn btn--primary"
                            busy={busy === `claim-${c.id}`}
                            onClick={() => run(`claim-${c.id}`, () => teacherApi.claim(c.id), { success: `You're teaching ${c.name}.`, after: refresh })}
                          >
                            Claim
                            <ArrowRight className="btn__arrow" size={16} aria-hidden="true" />
                          </ActionButton>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </PeriodCard>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function MyClassCard({ cls, busy, onDrop }) {
  return (
    <div className="class-card class-card--enrolled">
      <div className="class-card__main">
        <p className="class-card__kicker">
          <CircleCheck size={13} aria-hidden="true" />
          Your class{cls.teacher_locked ? " · assigned by management" : ""}
        </p>
        <h3 className="class-card__title">{cls.name}</h3>
        {cls.description && <p className="class-card__desc">{cls.description}</p>}
        {!cls.published && (
          <div>
            <PublishBadge published={false} />
          </div>
        )}
        <div className="roster">
          <div className="roster__head">
            <span className="meta">
              <Users size={14} aria-hidden="true" />
              Your roster
            </span>
            <span>
              {cls.seats_taken}/{cls.capacity}
            </span>
          </div>
          {cls.roster.length === 0 ? (
            <p className="roster__empty">No students signed up yet.</p>
          ) : (
            <ul className="chip-list">
              {cls.roster.map((r) => (
                <li key={r.student_id} className="roster__entry">
                  <Chip label={`${r.first_name} ${r.last_name}`} tone={r.status === "pending" ? "pending" : undefined} />
                  {r.status === "pending" && <StatusPill status="pending" short />}
                </li>
              ))}
            </ul>
          )}
          {cls.waitlist.length > 0 && (
            <>
              <div className="roster__head roster__head--waitlist">
                <span className="meta">
                  <Hourglass size={14} aria-hidden="true" />
                  Waitlist
                </span>
                <span>{cls.waitlist.length}</span>
              </div>
              <ul className="chip-list">
                {cls.waitlist.map((w) => (
                  <li key={w.student_id}>
                    <Chip tone="waitlist" label={`#${w.position} ${w.first_name} ${w.last_name}${w.priority ? " • " + priorityText(w.priority) : ""}`} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
      {!cls.teacher_locked && (
        <div className="class-card__actions">
          <ActionButton className="btn btn--danger-ghost btn--sm" busy={busy === `unclaim-${cls.id}`} onClick={onDrop}>
            Give up class
          </ActionButton>
        </div>
      )}
    </div>
  );
}
