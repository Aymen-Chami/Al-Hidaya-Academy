// Public full schedule: every published class with live seat counts. Counts only — the
// backend's public class list never includes children's names.
import { CalendarClock, CalendarRange, ChevronLeft } from "lucide-react";
import { catalogApi } from "../api/endpoints";
import { EmptyState, ErrorState, LoadingState, PageHeader, PeriodMedallion, SeatMeter } from "../components/ui";
import { useResource } from "../lib/hooks";
import { PERIODS, periodLabel, plural } from "../lib/domain";
import { cx } from "../lib/cx";

export default function ScheduleView({ navigate }) {
  const res = useResource(catalogApi.classes);

  if (res.loading) return <LoadingState label="Loading the schedule…" />;
  if (!res.data) return <ErrorState error={res.error} onRetry={res.reload} title="We couldn't load the schedule" />;

  const classes = res.data;
  return (
    <div className="page">
      <PageHeader
        eyebrow="At a glance"
        icon={CalendarRange}
        title="Full schedule"
        description="Every published class by period, with live seat counts. Children's names are never shown here."
      />
      {classes.length === 0 ? (
        <EmptyState
          icon={CalendarClock}
          title="No classes on the sheet yet."
          action={
            <button type="button" className="btn btn--primary" onClick={() => navigate("")}>
              <ChevronLeft size={16} aria-hidden="true" />
              Back to sign-up
            </button>
          }
        >
          The schedule fills in as classes are published. Check back soon.
        </EmptyState>
      ) : (
        <div className="schedule-grid">
          {PERIODS.map((p) => {
            const items = classes.filter((c) => c.period === p);
            return (
              <section key={p} className={cx("schedule-col", items.length === 0 && "schedule-col--empty")} data-period={p}>
                <header className="schedule-col__header">
                  <PeriodMedallion period={p} size="sm" />
                  <h2 className="schedule-col__title">{periodLabel(p)}</h2>
                  <span className="schedule-col__count" aria-label={plural(items.length, "class", "es")}>
                    {items.length}
                  </span>
                </header>
                {items.length === 0 ? (
                  <EmptyState size="compact" icon={CalendarClock} title="Nothing here yet." />
                ) : (
                  <ul className="schedule-list">
                    {items.map((c) => (
                      <li key={c.id} className="schedule-item">
                        <h3 className="schedule-item__title">{c.name}</h3>
                        <p className={cx("schedule-item__meta", !c.teacher && "schedule-item__meta--none")}>{c.teacher?.label || "No teacher yet"}</p>
                        <SeatMeter compact taken={c.seats_taken} capacity={c.capacity} waitlist={c.waitlist_count} />
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
