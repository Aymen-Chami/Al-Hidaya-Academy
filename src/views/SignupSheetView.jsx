// The public sign-up sheet. Anyone can browse classes and seat counts; a signed-in account
// picks one of its children and requests seats. Every rule (capacity, one class per period,
// waitlist promotion, approval) is enforced by the server — this view only reflects state.
import { useId, useRef, useState } from "react";
import {
  ArrowRight,
  CalendarClock,
  CalendarRange,
  GraduationCap,
  Hourglass,
  Info,
  LogIn,
  Plus,
  SearchX,
} from "lucide-react";
import { catalogApi, familyApi } from "../api/endpoints";
import { useAuth } from "../auth/context";
import { EmptyState, ErrorState, HeroArt, LoadingState, PeriodCard, SeatMeter, SearchField, StatusPill, CrownBadge, ActionButton } from "../components/ui";
import { useAction, useResource } from "../lib/hooks";
import AddChildForm from "../components/AddChildForm";
import { PERIODS, isActive, nextPriority, periodLabel, plural } from "../lib/domain";
import { cx } from "../lib/cx";

const CHILD_KEY = "alh.selectedChild"; // per-browser convenience only

function readSavedChild() {
  try {
    return Number(localStorage.getItem(CHILD_KEY)) || null;
  } catch {
    return null;
  }
}

export default function SignupSheetView({ notify, navigate }) {
  const { user } = useAuth();
  const signedIn = !!user;
  const classesRes = useResource(catalogApi.classes);
  const overviewRes = useResource(familyApi.overview, { enabled: signedIn });
  const { run, busy } = useAction(notify);

  const students = overviewRes.data?.students ?? [];
  const [selectedId, setSelectedId] = useState(readSavedChild);
  const child = students.find((s) => s.id === selectedId) ?? students[0] ?? null;
  const selectChild = (id) => {
    setSelectedId(id);
    try {
      localStorage.setItem(CHILD_KEY, String(id));
    } catch {
      /* private mode — selection just won't persist */
    }
  };

  // Families land on a compact grid of period cards and open the ones they want.
  const [collapsed, setCollapsed] = useState(() => Object.fromEntries(PERIODS.map((p) => [p, true])));
  const toggleCollapsed = (p) => setCollapsed((prev) => ({ ...prev, [p]: !prev[p] }));
  const [query, setQuery] = useState("");
  const searchId = useId();
  const periodsTitleId = useId();
  const periodsRef = useRef(null);

  const refresh = () => {
    classesRes.reload();
    overviewRes.reload();
  };

  const scrollToPeriods = () => {
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    periodsRef.current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  };

  if (classesRes.loading) return <LoadingState />;
  if (!classesRes.data) return <ErrorState error={classesRes.error} onRetry={classesRes.reload} title="We couldn't load the classes" />;

  const classes = classesRes.data;
  // Only classes with a teacher take sign-ups (the server refuses the rest).
  const open = classes.filter((c) => c.teacher);
  const q = query.trim().toLowerCase();
  const matches = (c) => !q || [c.name, c.description, c.teacher?.label].some((v) => v && v.toLowerCase().includes(q));

  // The selected child's current state, keyed by class.
  const enrollmentByClass = new Map((child?.enrollments ?? []).map((e) => [e.class_id, e]));
  const waitlistByClass = new Map((child?.waitlist ?? []).map((w) => [w.class_id, w]));
  const activeInPeriod = (p) => (child?.enrollments ?? []).some((e) => e.period === p && isActive(e.status));

  const actions = {
    signUp: (c) =>
      run(`enroll-${c.id}`, () => familyApi.enroll(child.id, c.id), {
        success: `Request sent — ${child.first_name} is pending approval for ${c.name}.`,
        after: refresh,
      }),
    drop: (c, e) =>
      run(`drop-${e.id}`, () => familyApi.drop(e.id), {
        success: e.status === "rejected" ? "Dismissed." : `${child.first_name} was removed from ${c.name}.`,
        after: refresh,
      }),
    joinWaitlist: (c) =>
      run(`wl-${c.id}`, () => familyApi.joinWaitlist(child.id, c.id), {
        success: `${child.first_name} joined the waitlist for ${c.name}.`,
        after: refresh,
      }),
    leaveWaitlist: (w) =>
      run(`leave-${w.id}`, () => familyApi.leaveWaitlist(w.id), { success: "Left the waitlist.", after: refresh }),
    cyclePriority: (w) => run(`prio-${w.id}`, () => familyApi.setPriority(w.id, nextPriority(w.priority)), { after: refresh }),
  };

  return (
    <div className="page">
      <section className="hero">
        <div className="hero__copy">
          <p className="hero__eyebrow">Al Hidayah Academy</p>
          <h1 className="hero__title">
            <span>Sunday School</span> <span>Sign-up</span>
          </h1>
          <p className="hero__lede">
            Pick one class in each period for your child. Seats are first come, first served — full classes have a
            waitlist, and every request is confirmed by the Principal.
          </p>
          {user === undefined ? null : signedIn ? (
            <ChildPicker
              students={students}
              loading={overviewRes.loading}
              child={child}
              onSelect={selectChild}
              onFind={scrollToPeriods}
              onAdd={async (first, last) => {
                const created = await run("add-child", () => familyApi.addStudent(first, last), {
                  success: `${first} was added.`,
                  after: overviewRes.reload,
                });
                if (created) selectChild(created.id);
                return !!created;
              }}
              adding={busy === "add-child"}
            />
          ) : (
            <div className="hero__form">
              <div className="hero__row hero__row--actions">
                <button type="button" className="btn btn--cta" onClick={() => navigate("signup")}>
                  Create an account
                  <ArrowRight className="btn__arrow" size={18} aria-hidden="true" />
                </button>
                <button type="button" className="btn btn--ghost btn--lg" onClick={() => navigate("login")}>
                  <LogIn size={17} aria-hidden="true" />
                  Log in
                </button>
              </div>
              <p className="hero__hint">Browse every class below. You'll need an account to request a seat.</p>
            </div>
          )}
        </div>
        <HeroArt />
      </section>

      <section className="periods" ref={periodsRef} aria-labelledby={periodsTitleId}>
        <div className="periods__header">
          <div>
            <h2 id={periodsTitleId} className="periods__title">
              Choose a period
            </h2>
            <p className="periods__sub">
              {child ? (
                <>
                  Signing up <strong>{child.first_name}</strong>. Tap a card to see its classes and open seats.
                </>
              ) : (
                "Tap a card to see its classes and open seats."
              )}
            </p>
          </div>
          <SearchField id={searchId} query={query} setQuery={setQuery} compact />
        </div>

        {open.length === 0 ? (
          <EmptyState
            icon={CalendarClock}
            title="Sign-up opens soon"
            action={
              <button type="button" className="btn btn--ghost" onClick={() => navigate("schedule")}>
                <CalendarRange size={16} aria-hidden="true" />
                See full schedule
              </button>
            }
          >
            No classes have a teacher assigned yet. Check back soon — they'll appear here by period.
          </EmptyState>
        ) : (
          <div className="period-grid">
            {PERIODS.map((p, i) => {
              const inPeriod = open.filter((c) => c.period === p);
              const shown = inPeriod.filter(matches);
              const seatsOpen = inPeriod.reduce((n, c) => n + c.seats_available, 0);
              const empty = inPeriod.length === 0;
              const summary = empty
                ? "No open classes yet"
                : `${plural(inPeriod.length, "class", "es")} · ${seatsOpen === 0 ? "all seats taken" : `${plural(seatsOpen, "seat")} open`}`;

              const periodEnrollment = (child?.enrollments ?? []).find((e) => e.period === p && isActive(e.status));
              const waitlisted = (child?.waitlist ?? []).some((w) => w.period === p);
              const matchCount = q ? shown.length : null;

              return (
                <PeriodCard
                  key={p}
                  index={i + 1}
                  period={p}
                  title={periodLabel(p)}
                  summary={summary}
                  empty={empty}
                  collapsed={!!collapsed[p]}
                  onToggle={() => toggleCollapsed(p)}
                  badges={
                    (periodEnrollment || waitlisted || q) && (
                      <>
                        {periodEnrollment && <StatusPill status={periodEnrollment.status} short />}
                        {waitlisted && (
                          <span className="status-pill status-pill--warning">
                            <Hourglass size={12} aria-hidden="true" />
                            Waitlisted
                          </span>
                        )}
                        {q && (
                          <span className={cx("status-pill", matchCount ? "status-pill--info" : "status-pill--neutral")}>
                            {matchCount ? plural(matchCount, "match", "es") : "No matches"}
                          </span>
                        )}
                      </>
                    )
                  }
                >
                  {empty ? (
                    <EmptyState
                      size="compact"
                      icon={CalendarClock}
                      title="Classes are still being arranged"
                      action={
                        <button type="button" className="btn btn--link" onClick={() => navigate("schedule")}>
                          See full schedule
                          <ArrowRight size={14} aria-hidden="true" />
                        </button>
                      }
                    >
                      They'll show up here once a teacher is assigned. Check back soon.
                    </EmptyState>
                  ) : shown.length === 0 ? (
                    <EmptyState
                      size="compact"
                      icon={SearchX}
                      title={`No matches for “${query.trim()}”`}
                      action={
                        <button type="button" className="btn btn--link" onClick={() => setQuery("")}>
                          Clear search
                        </button>
                      }
                    >
                      Try another word, or clear the search.
                    </EmptyState>
                  ) : (
                    <ul className="class-list">
                      {shown.map((c) => (
                        <ClassCard
                          key={c.id}
                          cls={c}
                          signedIn={signedIn}
                          child={child}
                          enrollment={enrollmentByClass.get(c.id)}
                          waitlistEntry={waitlistByClass.get(c.id)}
                          busyInPeriod={activeInPeriod(p)}
                          busy={busy}
                          actions={actions}
                          navigate={navigate}
                        />
                      ))}
                    </ul>
                  )}
                </PeriodCard>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

function ClassCard({ cls: c, signedIn, child, enrollment, waitlistEntry, busyInPeriod, busy, actions, navigate }) {
  const active = enrollment && isActive(enrollment.status);
  const rejected = enrollment?.status === "rejected";
  const full = c.is_full;

  let body;
  if (!signedIn) {
    body = (
      <button type="button" className="btn btn--ghost btn--sm" onClick={() => navigate("login")}>
        <LogIn size={14} aria-hidden="true" />
        Log in to sign up
      </button>
    );
  } else if (!child) {
    body = (
      <span className="class-card__note class-card__note--muted">
        <Info size={14} aria-hidden="true" />
        Add a child above to sign up
      </span>
    );
  } else if (active) {
    body = (
      <>
        <StatusPill status={enrollment.status} />
        <ActionButton className="btn btn--danger-ghost btn--sm" busy={busy === `drop-${enrollment.id}`} onClick={() => actions.drop(c, enrollment)}>
          Drop
        </ActionButton>
      </>
    );
  } else if (waitlistEntry) {
    body = (
      <>
        <CrownBadge priority={waitlistEntry.priority} busy={busy === `prio-${waitlistEntry.id}`} onClick={() => actions.cyclePriority(waitlistEntry)} />
        <span className="class-card__note">
          #{waitlistEntry.position} of {waitlistEntry.size} in line
        </span>
        <ActionButton className="btn btn--danger-ghost btn--sm" busy={busy === `leave-${waitlistEntry.id}`} onClick={() => actions.leaveWaitlist(waitlistEntry)}>
          Leave waitlist
        </ActionButton>
      </>
    );
  } else if (full) {
    body = (
      <ActionButton className="btn btn--gold" busy={busy === `wl-${c.id}`} onClick={() => actions.joinWaitlist(c)}>
        <Hourglass size={16} aria-hidden="true" />
        Join waitlist
      </ActionButton>
    );
  } else if (busyInPeriod) {
    body = (
      <span className="class-card__note class-card__note--muted">
        <Info size={14} aria-hidden="true" />
        Already has a class this period
      </span>
    );
  } else {
    body = (
      <ActionButton className="btn btn--primary" busy={busy === `enroll-${c.id}`} onClick={() => actions.signUp(c)}>
        {rejected ? "Request again" : "Sign up"}
        <ArrowRight className="btn__arrow" size={16} aria-hidden="true" />
      </ActionButton>
    );
  }

  return (
    <li
      className={cx(
        "class-card",
        active && enrollment.status === "approved" && "class-card--enrolled",
        active && enrollment.status === "pending" && "class-card--pending",
        waitlistEntry && "class-card--waitlisted"
      )}
    >
      <div className="class-card__main">
        <h3 className="class-card__title">{c.name}</h3>
        {c.description && <p className="class-card__desc">{c.description}</p>}
        <div className="class-card__meta">
          <span className="meta">
            <GraduationCap size={15} aria-hidden="true" />
            {c.teacher.label}
          </span>
        </div>
        <SeatMeter taken={c.seats_taken} capacity={c.capacity} waitlist={c.waitlist_count} />
        {rejected && (
          <p className="class-card__reason">
            <strong>Not approved</strong>
            {enrollment.rejection_reason ? ` — ${enrollment.rejection_reason}` : "."}{" "}
            <button type="button" className="btn btn--link" onClick={() => actions.drop(c, enrollment)}>
              Dismiss
            </button>
          </p>
        )}
      </div>
      <div className="class-card__actions">{body}</div>
    </li>
  );
}

// Signed-in hero: choose which child you're signing up, or add one.
function ChildPicker({ students, loading, child, onSelect, onAdd, adding, onFind }) {
  const [formOpen, setFormOpen] = useState(false);
  const showForm = formOpen || (!loading && students.length === 0);
  const groupId = useId();

  return (
    <div className="hero__form">
      {students.length > 0 && (
        <>
          <p className="hero__label" id={groupId}>
            Signing up
          </p>
          <div className="child-picker" role="radiogroup" aria-labelledby={groupId}>
            {students.map((s) => (
              <button
                key={s.id}
                type="button"
                role="radio"
                aria-checked={child?.id === s.id}
                className={cx("child-chip", child?.id === s.id && "is-selected")}
                onClick={() => onSelect(s.id)}
              >
                <span className="child-chip__avatar" aria-hidden="true">
                  {s.first_name[0]}
                </span>
                {s.first_name} {s.last_name}
              </button>
            ))}
            {!showForm && (
              <button type="button" className="child-chip child-chip--add" onClick={() => setFormOpen(true)}>
                <Plus size={16} aria-hidden="true" />
                Add a child
              </button>
            )}
          </div>
        </>
      )}

      {showForm ? (
        <AddChildForm
          intro={students.length === 0 ? "Add your child to get started." : null}
          busy={adding}
          onCancel={students.length > 0 ? () => setFormOpen(false) : null}
          onSubmit={async (first, last) => {
            const ok = await onAdd(first, last);
            if (ok) setFormOpen(false);
            return ok;
          }}
        />
      ) : (
        child && (
          <div className="hero__row">
            <button type="button" className="btn btn--cta" onClick={onFind}>
              Find a class for {child.first_name}
              <ArrowRight className="btn__arrow" size={18} aria-hidden="true" />
            </button>
          </div>
        )
      )}
    </div>
  );
}
