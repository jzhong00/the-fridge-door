import { useState } from "react";

import { AuthDialog, type AuthMode } from "@/components/AuthDialog";
import { Button } from "@/components/ui/button";
import type { Account } from "@/api/types";
import type { Credentials } from "@/hooks/useAccount";

/**
 * Who is signed in, in the header: a guest is invited to sign up (keeping
 * what they made), an account shows its email and a way out.
 */
export function AccountBar({
  account,
  onSignUp,
  onLogIn,
  onLogOut,
  loggingOut,
}: {
  account: Account | null;
  onSignUp: (credentials: Credentials) => Promise<unknown>;
  onLogIn: (credentials: Credentials) => Promise<unknown>;
  onLogOut: () => Promise<unknown>;
  loggingOut: boolean;
}) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [mode, setMode] = useState<AuthMode>("signup");

  const open = (next: AuthMode) => {
    setMode(next);
    setDialogOpen(true);
  };

  if (!account) return <div className="h-7" aria-hidden />;

  return (
    <div className="flex flex-wrap items-center justify-end gap-2 text-sm">
      {account.is_guest ? (
        <>
          <span className="text-muted-foreground">You're using a guest session.</span>
          <Button size="sm" onClick={() => open("signup")}>
            Sign up to keep your meals
          </Button>
          <Button size="sm" variant="ghost" onClick={() => open("login")}>
            Log in
          </Button>
        </>
      ) : (
        <>
          <span className="text-muted-foreground">
            Signed in as <span className="font-medium text-foreground">{account.email}</span>
          </span>
          <Button
            size="sm"
            variant="ghost"
            disabled={loggingOut}
            onClick={() => void onLogOut()}
          >
            Log out
          </Button>
        </>
      )}

      <AuthDialog
        open={dialogOpen}
        mode={mode}
        onModeChange={setMode}
        onOpenChange={setDialogOpen}
        onSubmit={(chosen, credentials) =>
          chosen === "signup" ? onSignUp(credentials) : onLogIn(credentials)
        }
      />
    </div>
  );
}
