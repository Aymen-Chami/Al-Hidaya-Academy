// The approval workflow. Everyone on staff can see the queue; only the Principal decides
// (the server enforces this too). Family contact details are shown for cross-checking
// against registration/payment records.
import { useCallback, useState } from "react";
import { Check, ClipboardCheck, Inbox, Mail, Phone, ShieldAlert, X } from "lucide-react";
import { adminApi } from "../api/endpoints";
import { isPrincipal, useAuth } from "../auth/context";
import { ActionButton, EmptyState, ErrorState, LoadingState, PageHeader, PeriodMedallion, Segmented, StatusPill } from "../components/ui";
import { useAction, useResource } from "../lib/hooks";
import { formatDate, fullName, periodLabel, plural } from "../lib/domain";
import { cx } from "../lib/cx";

const FILTERS = [
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Not approved" },
  { value: "all", label: "All" },
];

const SOURCE = { family: "Requested by family", staff: "Added by staff", waitlist: "Moved up from the waitlist" };

export default function ApprovalsView({ notify, onChanged }) {
  const { user } = useAuth();
  const principal = isPrincipal(user);
  const [filter, setFilter] = useState("pending");
  const fetcher = useCallback(() => adminApi.enrollments({ status: filter === "all" ? undefined : filter }), [filter]);
  const res = useResource(fetcher, { interval: 15000 });
  const { run, busy } = useAction(notify);
  const [selected, setSelected] = useState(() => new Set());
  const [rejecting, setRejecting] = useState(null); // enrollment id with the reason box open
  const [reason, setReason] = useState("");

  const reload = () => {
    res.reload();
    onChanged?.();
  };

  const items = res.data ?? [];
  const pendingIds = items.filter((e) => e.status === "pending").map((e) => e.id);
  const selectedPending = pendingIds.filter((id) => selected.has(id));
  const toggle = (id) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const approveSelected = () =>
    run("bulk", () => adminApi.approveBulk(selectedPending), {
      success: (r) =>
        r.failed.length
          ? `${plural(r.approved.length, "request")} approved; ${r.failed.length} couldn't be: ${r.failed.map((f) => f.message).join(" ")}`
          : `${plural(r.approved.length, "request")} approved. Families are being emailed.`,
      after: () => {
        setSelected(new Set());
        reload();
      },
    });

  return (
    <div className="page">
      <PageHeader
        eyebrow="Approvals"
        icon={ClipboardCheck}
        title="Enrollment requests"
        description="Every request holds its seat while it waits. Approving confirms it; not approving frees the seat for the waitlist. Families are emailed either way."
      />

      {!principal && (
        <p className="notice">
          <ShieldAlert size={18} aria-hidden="true" />
          Only the Principal can approve or decline requests. You can see the queue here.
        </p>
      )}

      <div className="queue-toolbar">
        <Segmented
          label="Filter requests"
          options={FILTERS}
          value={filter}
          onChange={(v) => {
            setFilter(v);
            setSelected(new Set());
            setRejecting(null);
          }}
        />
        {principal && filter === "pending" && pendingIds.length > 0 && (
          <div className="queue-toolbar__bulk">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={selectedPending.length === pendingIds.length}
                ref={(el) => el && (el.indeterminate = selectedPending.length > 0 && selectedPending.length < pendingIds.length)}
                onChange={(e) => setSelected(e.target.checked ? new Set(pendingIds) : new Set())}
              />
              Select all
            </label>
            <ActionButton className="btn btn--primary btn--sm" busy={busy === "bulk"} disabled={selectedPending.length === 0} onClick={approveSelected}>
              <Check size={15} aria-hidden="true" />
              Approve selected{selectedPending.length ? ` (${selectedPending.length})` : ""}
            </ActionButton>
          </div>
        )}
      </div>

      {res.loading ? (
        <LoadingState label="Loading requests…" />
      ) : !res.data ? (
        <ErrorState error={res.error} onRetry={res.reload} />
      ) : items.length === 0 ? (
        <EmptyState icon={Inbox} title={filter === "pending" ? "All caught up" : "Nothing here"}>
          {filter === "pending" ? "No requests are waiting for a decision." : "No requests match this filter."}
        </EmptyState>
      ) : (
        <ul className="queue-list">
          {items.map((e) => (
            <li key={e.id} className={cx("queue-item", selected.has(e.id) && "is-selected")}>
              {principal && e.status === "pending" && (
                <input
                  type="checkbox"
                  className="queue-item__check"
                  checked={selected.has(e.id)}
                  onChange={() => toggle(e.id)}
                  aria-label={`Select ${fullName(e.student)} for ${e.class_name}`}
                />
              )}
              <PeriodMedallion period={e.period} size="sm" />
              <div className="queue-item__main">
                <p className="queue-item__title">
                  <strong>{fullName(e.student)}</strong> → {e.class_name}
                </p>
                <p className="queue-item__meta">
                  {periodLabel(e.period)} · {SOURCE[e.source] ?? e.source} · {formatDate(e.created_at)}
                  {e.decided_by && e.status !== "pending" ? ` · by ${e.decided_by.name}, ${formatDate(e.decided_at)}` : ""}
                </p>
                {e.family ? (
                  <p className="queue-item__contact">
                    {fullName(e.family)}
                    <a href={`mailto:${e.family.email}`}>
                      <Mail size={13} aria-hidden="true" />
                      {e.family.email}
                    </a>
                    {e.family.phone && (
                      <a href={`tel:${e.family.phone}`}>
                        <Phone size={13} aria-hidden="true" />
                        {e.family.phone}
                      </a>
                    )}
                  </p>
                ) : (
                  <p className="queue-item__contact">Walk-in — no family account</p>
                )}
                {e.status === "rejected" && e.rejection_reason && <p className="child-row__reason">“{e.rejection_reason}”</p>}

                {rejecting === e.id && (
                  <form
                    className="reject-form"
                    onSubmit={(ev) => {
                      ev.preventDefault();
                      run(`reject-${e.id}`, () => adminApi.reject(e.id, reason.trim()), {
                        success: `Declined. ${e.family ? "The family is being emailed." : ""}`,
                        after: () => {
                          setRejecting(null);
                          setReason("");
                          reload();
                        },
                      });
                    }}
                  >
                    <label className="field__label" htmlFor={`reason-${e.id}`}>
                      Reason <span className="field__optional">(optional — included in the email)</span>
                    </label>
                    <input
                      id={`reason-${e.id}`}
                      className="input input--sm"
                      value={reason}
                      onChange={(ev) => setReason(ev.target.value)}
                      maxLength={500}
                      placeholder="e.g. No registration on file"
                      autoFocus
                    />
                    <div className="reject-form__actions">
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => setRejecting(null)}>
                        Cancel
                      </button>
                      <ActionButton type="submit" className="btn btn--danger btn--sm" busy={busy === `reject-${e.id}`}>
                        Decline request
                      </ActionButton>
                    </div>
                  </form>
                )}
              </div>
              <div className="queue-item__side">
                <StatusPill status={e.status} short />
                {principal && e.status === "pending" && rejecting !== e.id && (
                  <div className="queue-item__actions">
                    <ActionButton
                      className="btn btn--primary btn--sm"
                      busy={busy === `approve-${e.id}`}
                      onClick={() =>
                        run(`approve-${e.id}`, () => adminApi.approve(e.id), {
                          success: `Approved ${fullName(e.student)} for ${e.class_name}.`,
                          after: reload,
                        })
                      }
                    >
                      <Check size={15} aria-hidden="true" />
                      Approve
                    </ActionButton>
                    <button
                      type="button"
                      className="btn btn--danger-ghost btn--sm"
                      onClick={() => {
                        setRejecting(e.id);
                        setReason("");
                      }}
                    >
                      <X size={15} aria-hidden="true" />
                      Decline
                    </button>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
