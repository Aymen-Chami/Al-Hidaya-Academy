// Thin fetch wrapper for the FastAPI backend.
// - Same-origin only: in dev Vite proxies /api to :8000, in prod nginx does. That keeps the
//   HttpOnly session cookie working without CORS.
// - Every backend error is {"error": {code, message, details}}; it's thrown as an ApiError whose
//   `message` is already written for people, so views can show it as-is.

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(status, code, message, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

// Fired when a request comes back 401, so the app can drop to the logged-out state.
export const authEvents = new EventTarget();

function parse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function request(path, { method = "GET", body, query, signal } = {}) {
  let url = BASE + path;
  if (query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") params.set(key, value);
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  let res;
  try {
    res = await fetch(url, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError(0, "NETWORK", "Can't reach the server. Check your connection and try again.");
  }

  if (res.status === 204) return null;
  const data = parse(await res.text());

  if (!res.ok) {
    const err = data?.error;
    if (res.status === 401) authEvents.dispatchEvent(new Event("unauthorized"));
    throw new ApiError(
      res.status,
      err?.code || `HTTP_${res.status}`,
      err?.message || (res.status >= 500 ? "Something went wrong on our side. Please try again." : "That didn't work. Please try again."),
      err?.details ?? null
    );
  }
  return data;
}
