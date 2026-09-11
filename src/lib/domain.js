// Shared vocabulary for periods, statuses and names (mirrors the backend enums).

// Backend Period values: "1" | "2" | "3" | "year" ("All Periods" is a separate, year-long bucket).
export const PERIODS = ["1", "2", "3", "year"];

export function periodLabel(p) {
  return p === "year" ? "All Periods" : `Period ${p}`;
}

// Enrollment status → label + pill tone. Pending holds the seat until the Principal decides.
export const STATUS = {
  pending: { label: "Pending approval", short: "Pending", tone: "warning" },
  approved: { label: "Approved", short: "Approved", tone: "success" },
  rejected: { label: "Not approved", short: "Not approved", tone: "draft" },
};

export const isActive = (status) => status === "pending" || status === "approved";

export function priorityText(priority) {
  return priority === 1 ? "1st choice" : priority === 2 ? "2nd choice" : priority === 3 ? "3rd choice" : "unranked";
}

// Crown cycles unranked → 1st → 2nd → 3rd → unranked (the server clears that rank elsewhere).
export function nextPriority(priority) {
  return priority == null ? 1 : priority === 1 ? 2 : priority === 2 ? 3 : null;
}

export function plural(n, word, suffix = "s") {
  return `${n} ${word}${n === 1 ? "" : suffix}`;
}

export const fullName = (p) => (p ? `${p.first_name} ${p.last_name}` : "");

// "Aisha Khan" -> ["Aisha", "Khan"]; "Mary Ann Lee" -> ["Mary Ann", "Lee"].
export function splitName(value) {
  const parts = value.trim().split(/\s+/).filter(Boolean);
  if (parts.length < 2) return null;
  return [parts.slice(0, -1).join(" "), parts[parts.length - 1]];
}

export function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
