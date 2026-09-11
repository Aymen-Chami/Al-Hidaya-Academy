// App shell: session, routing, role-aware navigation, and toasts. All data and business
// rules live in the FastAPI backend (see src/api/); views only reflect server state.
import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  BookOpen,
  CalendarRange,
  ChevronDown,
  ClipboardCheck,
  GraduationCap,
  LayoutGrid,
  LogIn,
  LogOut,
  ShieldAlert,
  UserPlus,
  Users,
} from "lucide-react";
import crestLogo from "./assets/crest.png";
import { adminApi } from "./api/endpoints";
import { AuthProvider } from "./auth/AuthProvider";
import { ADMIN_ROLES, ROLE_LABELS, homeRouteFor, isAdmin, isTeacher, useAuth } from "./auth/context";
import { EmptyState, LoadingState, Toast } from "./components/ui";
import { cx } from "./lib/cx";
import { useHashRoute, useResource } from "./lib/hooks";
import ApprovalsView from "./views/ApprovalsView";
import AuthView from "./views/AuthView";
import ChildrenView from "./views/ChildrenView";
import ManageView from "./views/ManageView";
import PeopleView from "./views/PeopleView";
import ScheduleView from "./views/ScheduleView";
import SignupSheetView from "./views/SignupSheetView";
import TeacherView from "./views/TeacherView";

// auth: needs a session; roles: limited to these roles; guest: only when logged out.
const ROUTES = {
  "": { view: SignupSheetView },
  schedule: { view: ScheduleView },
  login: { guest: true },
  signup: { guest: true },
  reset: { guest: true },
  children: { view: ChildrenView, auth: true },
  teacher: { view: TeacherView, roles: ["teacher"] },
  manage: { view: ManageView, roles: ADMIN_ROLES },
  approvals: { view: ApprovalsView, roles: ADMIN_ROLES },
  people: { view: PeopleView, roles: ADMIN_ROLES },
};

const fetchPending = () => adminApi.enrollments({ status: "pending" });

export default function ClassSignupApp() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}

function AppShell() {
  const { user, logout } = useAuth();
  const [rawRoute, navigate] = useHashRoute();
  const route = rawRoute in ROUTES ? rawRoute : "";
  const config = ROUTES[route];

  // One toast at a time; a new message restarts the timer so an older one can't cut it short.
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);
  const notify = useCallback((text, type = "success") => {
    clearTimeout(toastTimer.current);
    setToast({ text, type });
    toastTimer.current = setTimeout(() => setToast(null), type === "error" ? 6000 : 2800);
  }, []);
  useEffect(() => () => clearTimeout(toastTimer.current), []);

  // Pending-approval count for the nav badge (staff only).
  const pending = useResource(fetchPending, { enabled: isAdmin(user), interval: 20000 });
  const pendingCount = pending.data?.length ?? 0;

  // Logged-in users don't need the login/sign-up screens.
  useEffect(() => {
    if (user && config.guest) navigate(homeRouteFor(user));
  }, [user, config.guest, navigate]);

  let content;
  if (user === undefined) {
    content = <LoadingState label="Checking your session…" />;
  } else if (config.guest) {
    content = user ? null : <AuthView mode={route} navigate={navigate} notify={notify} />;
  } else if ((config.auth || config.roles) && !user) {
    // Log in, then come back here.
    content = <AuthView mode="login" navigate={navigate} notify={notify} next={route} notice="Please log in to continue." />;
  } else if (config.roles && !config.roles.includes(user.role)) {
    content = (
      <EmptyState
        icon={ShieldAlert}
        title="This page isn't available for your account"
        action={
          <button type="button" className="btn btn--primary" onClick={() => navigate(homeRouteFor(user))}>
            Go to my page
          </button>
        }
      >
        You're signed in as {ROLE_LABELS[user.role].toLowerCase()}. Ask the Principal if you need different access.
      </EmptyState>
    );
  } else {
    const View = config.view;
    content = <View key={route} notify={notify} navigate={navigate} onChanged={pending.reload} />;
  }

  return (
    <div className="app">
      <div className="app-panel">
        <Header user={user} route={route} navigate={navigate} pendingCount={pendingCount} onLogout={async () => {
          await logout();
          navigate("");
          notify("You're logged out.");
        }} />
        <main className="app-main">{content}</main>
      </div>
      <div className="toast-region">
        {toast && (
          <Toast tone={toast.type} onClose={toast.type === "error" ? () => setToast(null) : undefined}>
            {toast.text}
          </Toast>
        )}
      </div>
    </div>
  );
}

// Nav items per role. `menu: true` items move into the account menu on phones.
function navItems(user, pendingCount) {
  if (!user) return [{ route: "schedule", label: "Schedule", icon: CalendarRange }];
  if (isAdmin(user)) {
    return [
      { route: "manage", label: "Classes", icon: LayoutGrid },
      { route: "approvals", label: "Approvals", icon: ClipboardCheck, badge: pendingCount },
      { route: "people", label: "People", icon: Users },
      { route: "schedule", label: "Schedule", icon: CalendarRange, menu: true },
    ];
  }
  if (isTeacher(user)) {
    return [
      { route: "teacher", label: "My classes", icon: GraduationCap },
      { route: "schedule", label: "Schedule", icon: CalendarRange, menu: true },
    ];
  }
  return [
    { route: "", label: "Sign-up sheet", icon: BookOpen },
    { route: "children", label: "My children", icon: Users },
    { route: "schedule", label: "Schedule", icon: CalendarRange, menu: true },
  ];
}

function Header({ user, route, navigate, pendingCount, onLogout }) {
  const items = navItems(user, pendingCount);
  return (
    <header className="nav">
      <button type="button" className="brand" onClick={() => navigate(user ? homeRouteFor(user) : "")} title="Home">
        <img className="brand__logo" src={crestLogo} alt="Al Hidayah Academy" width="776" height="294" />
      </button>
      <nav className="nav__links" aria-label="Main">
        {items.map((item) => (
          <NavLink key={item.route || "home"} item={item} current={route === item.route} onClick={() => navigate(item.route)} />
        ))}
        {user === null && (
          <>
            <NavLink item={{ route: "login", label: "Log in", icon: LogIn }} current={route === "login"} onClick={() => navigate("login")} />
            <button type="button" className="btn btn--primary btn--sm nav__cta" onClick={() => navigate("signup")}>
              <UserPlus size={15} aria-hidden="true" />
              <span className="nav__label">Sign up</span>
            </button>
          </>
        )}
        {user && <AccountMenu user={user} items={items.filter((i) => i.menu)} navigate={navigate} onLogout={onLogout} />}
      </nav>
    </header>
  );
}

function NavLink({ item, current, onClick }) {
  const Icon = item.icon;
  return (
    <button
      type="button"
      className={cx("nav__link", current && "is-current", item.menu && "nav__link--menu")}
      onClick={onClick}
      aria-current={current ? "page" : undefined}
    >
      <Icon size={17} aria-hidden="true" />
      <span className="nav__label">{item.label}</span>
      {item.badge > 0 && (
        <span className="nav__badge" aria-label={`${item.badge} waiting`}>
          {item.badge}
        </span>
      )}
    </button>
  );
}

// Account button + popover: who you are, a few links, and log out.
function AccountMenu({ user, items, navigate, onLogout }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (e) => {
      if (!rootRef.current?.contains(e.target)) setOpen(false);
    };
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const go = (route) => {
    setOpen(false);
    navigate(route);
  };
  // Staff can have children too; their family pages live in this menu.
  const familyLinks = user.role !== "family" ? [{ route: "", label: "Sign-up sheet", icon: BookOpen }, { route: "children", label: "My children", icon: Users }] : [];

  return (
    <div className="account" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className={cx("account__trigger", open && "is-open")}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="account__avatar" aria-hidden="true">
          {user.first_name[0]}
          {user.last_name[0]}
        </span>
        <span className="account__name">{user.first_name}</span>
        <ChevronDown className="account__chevron" size={15} aria-hidden="true" />
        <span className="sr-only">Account menu</span>
      </button>
      <div id={panelId} className={cx("popover", open && "is-open")} role="group" aria-label="Account" inert={!open}>
        <div className="popover__head">
          <p className="popover__title">
            {user.first_name} {user.last_name}
          </p>
          <p className="popover__desc">{user.email}</p>
          <span className="status-pill status-pill--info">{ROLE_LABELS[user.role]}</span>
        </div>
        {[...items, ...familyLinks].length > 0 && (
          <ul className="popover__links">
            {[...items, ...familyLinks].map((item) => {
              const Icon = item.icon;
              return (
                <li key={item.route || "home"} className={item.menu ? "popover__link--mobile" : undefined}>
                  <button type="button" className="popover__link" onClick={() => go(item.route)}>
                    <Icon size={16} aria-hidden="true" />
                    {item.label}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <button type="button" className="btn btn--ghost btn--block" onClick={onLogout}>
          <LogOut size={16} aria-hidden="true" />
          Log out
        </button>
      </div>
    </div>
  );
}
