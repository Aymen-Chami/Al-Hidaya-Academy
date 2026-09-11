import { createContext, useContext } from "react";

export const AuthContext = createContext(null);

// { user, login, logout, setUser }. `user` is undefined while the session is being checked,
// null when logged out, or the MeOut object ({ id, email, first_name, last_name, role, ... }).
export function useAuth() {
  return useContext(AuthContext);
}

export const ADMIN_ROLES = ["management", "principal"];
export const isAdmin = (user) => !!user && ADMIN_ROLES.includes(user.role);
export const isPrincipal = (user) => user?.role === "principal";
export const isTeacher = (user) => user?.role === "teacher";

// Where each role lands after logging in.
export function homeRouteFor(user) {
  if (isAdmin(user)) return "manage";
  if (isTeacher(user)) return "teacher";
  return "";
}

export const ROLE_LABELS = { family: "Family", teacher: "Teacher", management: "Management", principal: "Principal" };
