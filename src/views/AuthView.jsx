// Log in, create an account (email → 6-digit code → details), and reset a password
// (email → code → new password). Codes are emailed by the backend; in development they
// land in Mailpit. Server error messages are shown inline, as written by the API.
import { useEffect, useId, useState } from "react";
import { ArrowLeft, ArrowRight, KeyRound, LogIn, MailCheck, ShieldCheck, UserPlus } from "lucide-react";
import { authApi } from "../api/endpoints";
import { homeRouteFor, useAuth } from "../auth/context";
import { ActionButton } from "../components/ui";
import { cx } from "../lib/cx";

const TITLES = {
  login: { icon: LogIn, title: "Welcome back", sub: "Log in to sign your children up for classes." },
  signup: { icon: UserPlus, title: "Create your account", sub: "One account for your family — add each child after you sign up." },
  reset: { icon: KeyRound, title: "Reset your password", sub: "We'll email you a 6-digit code." },
};

export default function AuthView({ mode, navigate, notify, next, notice }) {
  const { icon: Icon, title, sub } = TITLES[mode] ?? TITLES.login;
  return (
    <div className="page auth">
      <div className="auth-card">
        <span className="auth-card__icon" aria-hidden="true">
          <Icon size={24} />
        </span>
        <h1 className="auth-card__title">{title}</h1>
        <p className="auth-card__sub">{notice || sub}</p>
        {mode === "signup" ? (
          <CodeFlow key="signup" kind="signup" navigate={navigate} notify={notify} />
        ) : mode === "reset" ? (
          <CodeFlow key="reset" kind="reset" navigate={navigate} notify={notify} />
        ) : (
          <LoginForm navigate={navigate} next={next} />
        )}
      </div>
      {import.meta.env.DEV && mode !== "login" && (
        <p className="dev-hint">
          <MailCheck size={14} aria-hidden="true" />
          Development: codes are delivered to Mailpit at{" "}
          <a href="http://localhost:8025" target="_blank" rel="noreferrer">
            localhost:8025
          </a>
        </p>
      )}
    </div>
  );
}

function LoginForm({ navigate, next }) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const errorId = useId();

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const me = await login(email, password);
      navigate(next ?? homeRouteFor(me));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <form className="auth-form" onSubmit={submit} noValidate>
      <TextField label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" invalid={!!error} describedBy={error ? errorId : undefined} autoFocus />
      <TextField label="Password" type="password" value={password} onChange={setPassword} autoComplete="current-password" invalid={!!error} describedBy={error ? errorId : undefined} />
      {error && <FormError id={errorId}>{error}</FormError>}
      <ActionButton type="submit" className="btn btn--cta btn--block" busy={busy} disabled={!email || !password}>
        Log in
        <ArrowRight className="btn__arrow" size={18} aria-hidden="true" />
      </ActionButton>
      <div className="auth-links">
        <button type="button" className="btn btn--link" onClick={() => navigate("reset")}>
          Forgot your password?
        </button>
        <span>
          New here?{" "}
          <button type="button" className="btn btn--link" onClick={() => navigate("signup")}>
            Create an account
          </button>
        </span>
      </div>
    </form>
  );
}

// Shared 3-step flow for sign-up and password reset.
function CodeFlow({ kind, navigate, notify }) {
  const { setUser } = useAuth();
  const isSignup = kind === "signup";
  const [step, setStep] = useState("email"); // email | code | finish
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [token, setToken] = useState("");
  const [fields, setFields] = useState({ first_name: "", last_name: "", phone: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const errorId = useId();

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const attempt = async (fn) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(err.message);
      if (err.code === "RATE_LIMITED" && err.details?.retry_after) setCooldown(err.details.retry_after);
    } finally {
      setBusy(false);
    }
  };

  const requestCode = () =>
    attempt(async () => {
      await (isSignup ? authApi.signupRequestCode(email) : authApi.resetRequestCode(email));
      setStep("code");
      setCode("");
      setCooldown(60);
    });

  const verifyCode = () =>
    attempt(async () => {
      const res = await (isSignup ? authApi.signupVerifyCode(email, code) : authApi.resetVerifyCode(email, code));
      setToken(res.completion_token);
      setStep("finish");
    });

  const finish = () =>
    attempt(async () => {
      const me = isSignup
        ? await authApi.signupComplete({
            completion_token: token,
            first_name: fields.first_name,
            last_name: fields.last_name,
            password: fields.password,
            phone: fields.phone || null,
          })
        : await authApi.resetComplete(token, fields.password);
      setUser(me);
      notify(isSignup ? `Welcome, ${me.first_name}! Add your child to get started.` : "Password updated — you're logged in.");
      navigate(homeRouteFor(me));
    });

  const set = (key) => (value) => setFields((f) => ({ ...f, [key]: value }));
  const describedBy = error ? errorId : undefined;
  const steps = isSignup ? ["Email", "Code", "Details"] : ["Email", "Code", "New password"];
  const stepIndex = { email: 0, code: 1, finish: 2 }[step];

  return (
    <>
      <ol className="steps" aria-label="Progress">
        {steps.map((label, i) => (
          <li key={label} className={cx("steps__item", i < stepIndex && "is-done", i === stepIndex && "is-current")} aria-current={i === stepIndex ? "step" : undefined}>
            <span className="steps__dot" aria-hidden="true">
              {i + 1}
            </span>
            {label}
          </li>
        ))}
      </ol>

      {step === "email" && (
        <form className="auth-form" noValidate onSubmit={(e) => (e.preventDefault(), requestCode())}>
          <TextField label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" invalid={!!error} describedBy={describedBy} autoFocus />
          {error && <FormError id={errorId}>{error}</FormError>}
          <ActionButton type="submit" className="btn btn--cta btn--block" busy={busy} disabled={!email || cooldown > 0}>
            {cooldown > 0 ? `Try again in ${cooldown}s` : "Email me a code"}
            <ArrowRight className="btn__arrow" size={18} aria-hidden="true" />
          </ActionButton>
          <AuthFooter navigate={navigate} isSignup={isSignup} />
        </form>
      )}

      {step === "code" && (
        <form className="auth-form" noValidate onSubmit={(e) => (e.preventDefault(), verifyCode())}>
          <p className="auth-form__note">
            If <strong>{email}</strong> can receive email, a 6-digit code is on its way. It expires in 15 minutes.
          </p>
          <TextField
            label="6-digit code"
            value={code}
            onChange={(v) => setCode(v.replace(/\D/g, "").slice(0, 6))}
            inputMode="numeric"
            autoComplete="one-time-code"
            className="input--code"
            invalid={!!error}
            describedBy={describedBy}
            autoFocus
          />
          {error && <FormError id={errorId}>{error}</FormError>}
          <ActionButton type="submit" className="btn btn--cta btn--block" busy={busy} disabled={code.length !== 6}>
            Verify code
            <ArrowRight className="btn__arrow" size={18} aria-hidden="true" />
          </ActionButton>
          <div className="auth-links">
            <button type="button" className="btn btn--link" onClick={() => (setStep("email"), setError(""))}>
              <ArrowLeft size={14} aria-hidden="true" />
              Use a different email
            </button>
            <button type="button" className="btn btn--link" disabled={cooldown > 0 || busy} onClick={requestCode}>
              {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
            </button>
          </div>
        </form>
      )}

      {step === "finish" && (
        <form className="auth-form" noValidate onSubmit={(e) => (e.preventDefault(), finish())}>
          {isSignup && (
            <div className="auth-form__row">
              <TextField label="First name" value={fields.first_name} onChange={set("first_name")} autoComplete="given-name" autoFocus />
              <TextField label="Last name" value={fields.last_name} onChange={set("last_name")} autoComplete="family-name" />
            </div>
          )}
          {isSignup && <TextField label="Phone" optional type="tel" value={fields.phone} onChange={set("phone")} autoComplete="tel" />}
          <TextField
            label={isSignup ? "Password" : "New password"}
            type="password"
            value={fields.password}
            onChange={set("password")}
            autoComplete="new-password"
            hint="At least 8 characters."
            invalid={!!error}
            describedBy={describedBy}
            autoFocus={!isSignup}
          />
          {error && <FormError id={errorId}>{error}</FormError>}
          <ActionButton
            type="submit"
            className="btn btn--cta btn--block"
            busy={busy}
            disabled={fields.password.length < 8 || (isSignup && (!fields.first_name.trim() || !fields.last_name.trim()))}
          >
            {isSignup ? "Create account" : "Set password & log in"}
            <ShieldCheck size={18} aria-hidden="true" />
          </ActionButton>
        </form>
      )}
    </>
  );
}

function AuthFooter({ navigate, isSignup }) {
  return (
    <div className="auth-links">
      <span>
        {isSignup ? "Already have an account?" : "Remembered it?"}{" "}
        <button type="button" className="btn btn--link" onClick={() => navigate("login")}>
          Log in
        </button>
      </span>
    </div>
  );
}

function TextField({ label, value, onChange, type = "text", hint, optional, invalid, describedBy, className, ...rest }) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
        {optional && <span className="field__optional"> (optional)</span>}
      </label>
      <input
        id={id}
        className={cx("input", className)}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={invalid || undefined}
        aria-describedby={[hint && hintId, describedBy].filter(Boolean).join(" ") || undefined}
        {...rest}
      />
      {hint && (
        <span id={hintId} className="field__hint">
          {hint}
        </span>
      )}
    </div>
  );
}

function FormError({ id, children }) {
  return (
    <p id={id} className="field-error" role="alert">
      {children}
    </p>
  );
}
