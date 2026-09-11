import { useId, useState } from "react";
import { Plus, UserPlus, UserRound } from "lucide-react";
import { ActionButton } from "./ui";

// First + last name for a new child. `onSubmit` resolves truthy on success (then it clears).
export default function AddChildForm({ intro, onSubmit, onCancel, busy }) {
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const firstId = useId();
  const lastId = useId();
  const valid = first.trim() && last.trim();

  return (
    <form
      className="add-child"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!valid) return;
        const ok = await onSubmit(first.trim(), last.trim());
        if (ok) {
          setFirst("");
          setLast("");
        }
      }}
    >
      {intro && (
        <p className="add-child__intro">
          <UserPlus size={18} aria-hidden="true" />
          {intro}
        </p>
      )}
      <div className="add-child__row">
        <div className="input-group input-group--hero">
          <UserRound className="input-group__icon" size={20} aria-hidden="true" />
          <label className="sr-only" htmlFor={firstId}>
            Child's first name
          </label>
          <input id={firstId} className="input" value={first} onChange={(e) => setFirst(e.target.value)} placeholder="First name" autoComplete="off" />
        </div>
        <div className="input-group input-group--hero input-group--plain">
          <label className="sr-only" htmlFor={lastId}>
            Child's last name
          </label>
          <input id={lastId} className="input" value={last} onChange={(e) => setLast(e.target.value)} placeholder="Last name" autoComplete="off" />
        </div>
        <ActionButton type="submit" className="btn btn--cta" busy={busy} disabled={!valid}>
          <Plus size={18} aria-hidden="true" />
          Add child
        </ActionButton>
      </div>
      {onCancel && (
        <button type="button" className="btn btn--link add-child__cancel" onClick={onCancel}>
          Cancel
        </button>
      )}
    </form>
  );
}
