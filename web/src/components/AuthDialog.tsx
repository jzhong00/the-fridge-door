import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Credentials } from "@/hooks/useAccount";

export type AuthMode = "signup" | "login";

const COPY = {
  signup: {
    title: "Create an account",
    description:
      "Keep your meals and plans, and use them on any device. Everything you've made so far comes with you.",
    submit: "Create account",
    switchPrompt: "Already have an account?",
    switchTo: "Log in",
  },
  login: {
    title: "Log in",
    description:
      "Log in to your account. Meals made in this guest session stay behind.",
    submit: "Log in",
    switchPrompt: "New here?",
    switchTo: "Create an account",
  },
} as const;

/**
 * Sign up or log in, in one dialog: the two forms are identical but for
 * what the server does with them. The error shown is the server's own
 * sentence (a weak password, a taken email, wrong credentials, a wait).
 */
export function AuthDialog({
  open,
  mode,
  onOpenChange,
  onModeChange,
  onSubmit,
}: {
  open: boolean;
  mode: AuthMode;
  onOpenChange: (open: boolean) => void;
  onModeChange: (mode: AuthMode) => void;
  onSubmit: (mode: AuthMode, credentials: Credentials) => Promise<unknown>;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const copy = COPY[mode];

  const reset = () => {
    setPassword("");
    setError(null);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await onSubmit(mode, { email, password });
      reset();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <div className="grid gap-1.5 pr-6">
          <DialogTitle>{copy.title}</DialogTitle>
          <DialogDescription>{copy.description}</DialogDescription>
        </div>

        <form onSubmit={submit} className="grid gap-3" noValidate>
          <div className="grid gap-1.5">
            <Label htmlFor="auth-email">Email</Label>
            <Input
              id="auth-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="auth-password">Password</Label>
            <Input
              id="auth-password"
              type="password"
              // Lets password managers offer a new password at signup and
              // the saved one at login.
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby={mode === "signup" ? "auth-password-hint" : undefined}
            />
            {mode === "signup" && (
              <p id="auth-password-hint" className="text-xs text-muted-foreground">
                At least 8 characters. A few unrelated words work well.
              </p>
            )}
          </div>

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" disabled={pending || !email || !password}>
            {pending ? "Please wait…" : copy.submit}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          {copy.switchPrompt}{" "}
          <Button
            variant="link"
            className="h-auto p-0"
            onClick={() => {
              setError(null);
              onModeChange(mode === "signup" ? "login" : "signup");
            }}
          >
            {copy.switchTo}
          </Button>
        </p>
      </DialogContent>
    </Dialog>
  );
}
