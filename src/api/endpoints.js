// One function per backend endpoint (FastAPI, /api/v1). Grouped by audience.
import { request } from "./client";

const post = (path, body) => request(path, { method: "POST", body: body ?? {} });
const patch = (path, body) => request(path, { method: "PATCH", body });
const put = (path, body) => request(path, { method: "PUT", body });
const del = (path) => request(path, { method: "DELETE" });

export const authApi = {
  me: () => request("/auth/me"),
  login: (email, password) => post("/auth/login", { email, password }),
  logout: () => post("/auth/logout"),
  signupRequestCode: (email) => post("/auth/signup/request-code", { email }),
  signupVerifyCode: (email, code) => post("/auth/signup/verify-code", { email, code }),
  signupComplete: (fields) => post("/auth/signup/complete", fields),
  resetRequestCode: (email) => post("/auth/password-reset/request-code", { email }),
  resetVerifyCode: (email, code) => post("/auth/password-reset/verify-code", { email, code }),
  resetComplete: (completion_token, new_password) => post("/auth/password-reset/complete", { completion_token, new_password }),
  changePassword: (current_password, new_password) => post("/auth/me/password", { current_password, new_password }),
};

// Public: published classes with seat counts — never children's names.
export const catalogApi = {
  classes: () => request("/classes"),
};

// Any signed-in account can manage its own children and sign them up.
export const familyApi = {
  students: () => request("/me/students"),
  addStudent: (first_name, last_name) => post("/me/students", { first_name, last_name }),
  updateStudent: (id, fields) => patch(`/me/students/${id}`, fields),
  removeStudent: (id) => del(`/me/students/${id}`),
  overview: () => request("/me/overview"),
  enroll: (student_id, class_id) => post("/enrollments", { student_id, class_id }),
  drop: (enrollmentId) => del(`/enrollments/${enrollmentId}`),
  joinWaitlist: (student_id, class_id) => post("/waitlist", { student_id, class_id }),
  setPriority: (entryId, priority) => patch(`/waitlist/${entryId}`, { priority }),
  leaveWaitlist: (entryId) => del(`/waitlist/${entryId}`),
};

export const teacherApi = {
  classes: () => request("/teacher/classes"),
  claim: (classId) => post(`/teacher/classes/${classId}/claim`),
  dropClaim: (classId) => del(`/teacher/classes/${classId}/claim`),
};

// Management + Principal (some writes are Principal-only; the server enforces it).
export const adminApi = {
  classes: () => request("/admin/classes"),
  createClass: (fields) => post("/admin/classes", fields),
  updateClass: (id, fields) => patch(`/admin/classes/${id}`, fields),
  deleteClass: (id) => del(`/admin/classes/${id}`),
  moveClass: (id, direction) => post(`/admin/classes/${id}/move`, { direction }),
  assignTeacher: (id, teacher_id) => put(`/admin/classes/${id}/teacher`, { teacher_id }),
  unassignTeacher: (id) => del(`/admin/classes/${id}/teacher`),
  enroll: (classId, student_id) => post(`/admin/classes/${classId}/enrollments`, { student_id }),
  removeEnrollment: (enrollmentId) => del(`/admin/enrollments/${enrollmentId}`),
  removeWaitlist: (entryId) => del(`/admin/waitlist/${entryId}`),

  students: (q) => request("/admin/students", { query: { q } }),
  createStudent: (first_name, last_name, family_id = null) => post("/admin/students", { first_name, last_name, family_id }),

  users: (query) => request("/admin/users", { query }),
  createUser: (fields) => post("/admin/users", fields),
  updateUser: (id, fields) => patch(`/admin/users/${id}`, fields),

  enrollments: (query) => request("/admin/enrollments", { query }),
  approve: (id) => post(`/admin/enrollments/${id}/approve`),
  reject: (id, reason) => post(`/admin/enrollments/${id}/reject`, { reason: reason || null }),
  approveBulk: (ids) => post("/admin/enrollments/approve-bulk", { ids }),
};
