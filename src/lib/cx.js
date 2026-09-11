// Join class names, skipping falsy values: cx("a", cond && "b") -> "a b" | "a".
export function cx(...names) {
  return names.filter(Boolean).join(" ");
}
