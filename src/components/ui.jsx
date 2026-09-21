// Presentational building blocks shared across views. No app state or data
// access lives here — everything comes in through props.
import { cloneElement, isValidElement, useId } from "react";
import {
  BookOpen,
  CalendarDays,
  CalendarRange,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  CircleCheck,
  CloudOff,
  Crown,
  Eye,
  EyeOff,
  GraduationCap,
  Hourglass,
  Inbox,
  LoaderCircle,
  RotateCw,
  Search,
  Star,
  Sun,
  Sunrise,
  Sunset,
  Trash2,
  UserX,
  X,
} from "lucide-react";
import { cx } from "../lib/cx";
import { STATUS, priorityText } from "../lib/domain";
import PeriodArt from "./PeriodArt";

const PERIOD_ICONS = { 1: Sunrise, 2: Sun, 3: Sunset, year: CalendarRange };

export function PeriodMedallion({ period, size = "md" }) {
  const Icon = PERIOD_ICONS[period] ?? CalendarRange;
  return (
    <span className={cx("period-medallion", size !== "md" && `period-medallion--${size}`)} data-period={period} aria-hidden="true">
      <Icon size={size === "sm" ? 17 : size === "lg" ? 28 : 21} strokeWidth={2} />
    </span>
  );
}

/**
 * One period = a card (the toggle) + its class list (the panel). Both are direct
 * children of `.period-grid`: on wide screens the cards sit in one row and open
 * panels stack full-width below it; on phones each panel follows its own card.
 * `index` (1-based) pins the card's grid cell — see `.period-grid` in App.css.
 * The panel stays mounted so its height can animate, and is `inert` while closed.
 */
export function PeriodCard({ period, index, title, summary, badges, empty, collapsed, onToggle, children }) {
  const panelId = useId();
  return (
    <>
      <button
        type="button"
        className={cx("period-tile", empty && "period-tile--empty", !collapsed && "is-open")}
        data-period={period}
        data-index={index}
        aria-expanded={!collapsed}
        aria-controls={panelId}
        onClick={onToggle}
      >
        {/* Sky: gradient + line-art + legibility scrim, all decorative (see .period-tile__sky). */}
        <span className="period-tile__sky" aria-hidden="true">
          <PeriodArt period={period} />
        </span>
        {/* The text block carries its own scrim, so it always sits on a legible backdrop
            however tall the block gets (badges push the title up). */}
        <span className="period-tile__content">
          <span className="period-tile__title">{title}</span>
          {summary && <span className="period-tile__summary">{summary}</span>}
          {badges && <span className="period-tile__badges">{badges}</span>}
          <span className="period-tile__hint">
            {collapsed ? "View classes" : "Hide classes"}
            <ChevronDown className="period-tile__chevron" size={16} aria-hidden="true" />
          </span>
        </span>
      </button>
      <section
        id={panelId}
        className={cx("period-panel", collapsed && "is-collapsed")}
        data-period={period}
        aria-label={`${title} classes`}
        inert={collapsed}
      >
        <div className="period-panel__inner">
          <div className="period-panel__body">
            <header className="period-panel__header">
              <PeriodMedallion period={period} size="sm" />
              <h2 className="period-panel__title">{title}</h2>
              {summary && <span className="period-panel__summary">{summary}</span>}
              <button type="button" className="icon-btn period-panel__close" onClick={onToggle} aria-label={`Hide ${title} classes`}>
                <ChevronUp size={18} />
              </button>
            </header>
            {children}
          </div>
        </div>
      </section>
    </>
  );
}

// Abstract, non-figurative hero decoration: floating colored tiles with icons.
export function HeroArt() {
  return (
    <div className="hero-art" aria-hidden="true">
      <span className="hero-art__disc" />
      <span className="hero-art__ring" />
      <span className="hero-art__tile hero-art__tile--pink">
        <GraduationCap size={46} strokeWidth={1.8} />
      </span>
      <span className="hero-art__tile hero-art__tile--orange">
        <BookOpen size={34} strokeWidth={1.9} />
      </span>
      <span className="hero-art__tile hero-art__tile--blue">
        <CalendarDays size={30} strokeWidth={1.9} />
      </span>
      <span className="hero-art__tile hero-art__tile--indigo">
        <Star size={22} strokeWidth={2} />
      </span>
      <span className="hero-art__dot hero-art__dot--1" />
      <span className="hero-art__dot hero-art__dot--2" />
      <span className="hero-art__dot hero-art__dot--3" />
    </div>
  );
}

/**
 * The one component for "there's nothing to show here". Keep it for genuinely
 * empty results — loading and failures have their own states (LoadingState,
 * the error toast) so an API outage never masquerades as "no classes".
 */
export function EmptyState({ icon: Icon = Inbox, title, children, action, size = "default" }) {
  const compact = size === "compact";
  return (
    <div className={cx("empty-state", compact && "empty-state--compact")}>
      <span className="empty-state__icon" aria-hidden="true">
        <Icon size={compact ? 19 : 28} strokeWidth={1.75} />
      </span>
      <div className="empty-state__text">
        {title && <p className="empty-state__title">{title}</p>}
        {children && <p className="empty-state__body">{children}</p>}
      </div>
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}

// Seat availability as a small bar + label. Counts only — never names.
export function SeatMeter({ taken, capacity, waitlist = 0, compact }) {
  const full = taken >= capacity;
  const open = Math.max(0, capacity - taken);
  const ratio = capacity > 0 ? Math.min(1, taken / capacity) : 1;
  const tone = full ? "full" : ratio >= 0.75 ? "low" : "open";
  return (
    <div className={cx("seat-meter", `seat-meter--${tone}`, compact && "seat-meter--compact")}>
      <span className="seat-meter__track" aria-hidden="true">
        <span className="seat-meter__fill" style={{ "--fill": ratio }} />
      </span>
      <span className="seat-meter__label">
        {full ? `Full · ${capacity} seat${capacity === 1 ? "" : "s"}` : `${open} of ${capacity} seat${capacity === 1 ? "" : "s"} open`}
        {waitlist > 0 && <span className="seat-meter__waitlist"> · {waitlist} on waitlist</span>}
      </span>
    </div>
  );
}

export function LoadingState({ label = "Loading the sign-up sheet…" }) {
  return (
    <div className="loading-state" role="status">
      <p className="loading-state__label">
        <LoaderCircle size={18} aria-hidden="true" />
        {label}
      </p>
      <div className="skeleton skeleton--hero" aria-hidden="true" />
      <div className="loading-state__grid" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton skeleton--card" style={{ animationDelay: `${i * 120}ms` }} />
        ))}
      </div>
    </div>
  );
}

export function Toast({ tone = "success", onClose, children }) {
  const isError = tone === "error";
  return (
    <div className={cx("toast", `toast--${tone}`)} role={isError ? "alert" : "status"}>
      <span className="toast__icon" aria-hidden="true">
        {isError ? <CircleAlert size={18} /> : <CircleCheck size={18} />}
      </span>
      <span className="toast__text">{children}</span>
      {onClose && (
        <button type="button" className="icon-btn toast__close" onClick={onClose} aria-label="Dismiss">
          <X size={16} />
        </button>
      )}
    </div>
  );
}

// Label + control + optional hint. The label is tied to the control by id (not by wrapping
// it), so a <select>'s option text never leaks into its accessible name.
export function Field({ label, hint, optional, className, children }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const control = isValidElement(children)
    ? cloneElement(children, { id, "aria-describedby": hint ? hintId : undefined })
    : children;
  return (
    <div className={cx("field", className)}>
      <label className="field__label" htmlFor={id}>
        {label}
        {optional && <span className="field__optional"> (optional)</span>}
      </label>
      {control}
      {hint && (
        <span id={hintId} className="field__hint">
          {hint}
        </span>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------------
   Page furniture
   --------------------------------------------------------------------------- */

export function PageHeader({ eyebrow, icon: Icon, title, description, actions }) {
  return (
    <header className="page-header">
      <div className="page-header__text">
        {eyebrow && (
          <p className="eyebrow">
            {Icon && <Icon size={14} aria-hidden="true" />}
            {eyebrow}
          </p>
        )}
        <h1 className="page-header__title">{title}</h1>
        {description && <p className="page-header__lede">{description}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}

// Shown when data couldn't load at all (as opposed to EmptyState: loaded, but nothing there).
export function ErrorState({ error, onRetry, title = "We couldn't load this" }) {
  return (
    <div className="empty-state empty-state--error" role="alert">
      <span className="empty-state__icon" aria-hidden="true">
        <CloudOff size={28} strokeWidth={1.75} />
      </span>
      <div className="empty-state__text">
        <p className="empty-state__title">{title}</p>
        <p className="empty-state__body">{error?.message || "Something went wrong. Please try again."}</p>
      </div>
      {onRetry && (
        <div className="empty-state__action">
          <button type="button" className="btn btn--ghost" onClick={onRetry}>
            <RotateCw size={16} aria-hidden="true" />
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

// A button that shows a spinner and blocks double-submits while its request is in flight.
export function ActionButton({ busy, className, children, disabled, type = "button", ...rest }) {
  return (
    <button type={type} className={cx(className, busy && "is-busy")} disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
      {busy && <LoaderCircle className="btn__spinner" size={16} aria-hidden="true" />}
      {children}
    </button>
  );
}

export function Segmented({ label, options, value, onChange }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          className={cx("segmented__option", value === o.value && "is-active")}
          onClick={() => onChange(o.value)}
        >
          {o.label}
          {o.count != null && <span className="segmented__count">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function SearchField({ id, query, setQuery, hint, compact, label = "Find a class", placeholder = "Search by class, topic, or teacher" }) {
  return (
    <div className={cx("field", compact && "field--search")}>
      <label className={cx("field__label", compact && "sr-only")} htmlFor={id}>
        {label}
      </label>
      <div className={cx("input-group", compact && "input-group--pill", query && "input-group--trailing")}>
        <Search className="input-group__icon" size={18} aria-hidden="true" />
        <input
          id={id}
          className="input"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          autoComplete="off"
        />
        {query && (
          <button type="button" className="icon-btn input-group__clear" onClick={() => setQuery("")} aria-label="Clear search">
            <X size={16} />
          </button>
        )}
      </div>
      {hint && <span className="field__hint">{hint}</span>}
    </div>
  );
}

/* ---------------------------------------------------------------------------
   Pills, chips, badges
   --------------------------------------------------------------------------- */

export function StatusPill({ status, short }) {
  const meta = STATUS[status];
  if (!meta) return null;
  const Icon = status === "approved" ? CircleCheck : status === "pending" ? Hourglass : X;
  return (
    <span className={cx("status-pill", `status-pill--${meta.tone}`)}>
      <Icon size={12} aria-hidden="true" />
      {short ? meta.short : meta.label}
    </span>
  );
}

export function PublishBadge({ published }) {
  return published ? (
    <span className="status-pill status-pill--success">
      <Eye size={12} aria-hidden="true" />
      Published
    </span>
  ) : (
    <span className="status-pill status-pill--draft">
      <EyeOff size={12} aria-hidden="true" />
      Draft
    </span>
  );
}

export function Chip({ label, onRemove, removeLabel, tone, busy, title, className }) {
  return (
    <span className={cx("chip", !onRemove && "chip--static", tone && `chip--${tone}`, className)} title={title}>
      {label}
      {onRemove && (
        <button
          type="button"
          className="chip__remove"
          onClick={onRemove}
          disabled={busy}
          aria-label={removeLabel || `Remove ${label}`}
        >
          {busy ? <LoaderCircle className="btn__spinner" size={13} aria-hidden="true" /> : <UserX size={13} aria-hidden="true" />}
        </button>
      )}
    </span>
  );
}

export function CrownBadge({ priority, onClick, busy }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className={cx("crown-badge", priority && `crown-badge--${priority}`)}
      title={`Waitlist priority: ${priorityText(priority)} — click to change`}
      aria-label={`Waitlist priority: ${priorityText(priority)}. Click to change.`}
    >
      {/* Keyed on priority so the pop animation replays on each change. */}
      <Crown key={priority ?? "none"} className="crown-badge__icon" size={16} fill={priority ? "currentColor" : "none"} aria-hidden="true" />
      <span>{priorityText(priority)}</span>
    </button>
  );
}

// Inline "are you sure?" — focus starts on Cancel so a stray Enter can't destroy anything.
export function ConfirmStrip({ title, body, confirmLabel = "Delete", onConfirm, onCancel, busy }) {
  const titleId = useId();
  return (
    <div className="confirm-strip" role="alertdialog" aria-labelledby={titleId} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <span className="confirm-strip__icon" aria-hidden="true">
        <Trash2 size={18} />
      </span>
      <div className="confirm-strip__text">
        <p id={titleId} className="confirm-strip__title">
          {title}
        </p>
        {body && <p className="confirm-strip__body">{body}</p>}
      </div>
      <div className="confirm-strip__actions">
        <button type="button" className="btn btn--ghost btn--sm" onClick={onCancel} autoFocus>
          Cancel
        </button>
        <ActionButton className="btn btn--danger btn--sm" onClick={onConfirm} busy={busy}>
          {confirmLabel}
        </ActionButton>
      </div>
    </div>
  );
}
