import { LogOut } from "lucide-react";
import { useState } from "react";

import { AuthDialog, type AuthMode } from "@/components/AuthDialog";
import { Button } from "@/components/ui/button";
import type { Account } from "@/api/types";
import type { Credentials } from "@/hooks/useAccount";

/**
 * Who is signed in, at the foot of the sidebar: a guest is invited to sign
 * up (keeping what they made), an account shows its email and a way out.
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

  // A row in a phone's top bar; a stack at the foot of the sidebar. The
  // explanatory text only fits, and only helps, in the sidebar.
  return (
    <div className="flex min-w-0 items-center gap-1.5 text-sm lg:flex-col lg:items-stretch lg:gap-2">
      {account.is_guest ? (
        <>
          <p className="hidden text-muted-foreground lg:block">You're using a guest session.</p>
          <Button
            size="sm"
            aria-label="Sign up to keep your meals"
            onClick={() => open("signup")}
          >
            <span className="lg:hidden">Sign up</span>
            <span className="hidden lg:inline">Sign up to keep your meals</span>
          </Button>
          <Button size="sm" variant="ghost" onClick={() => open("login")}>
            Log in
          </Button>
        </>
      ) : (
        <>
          <p className="hidden min-w-0 text-muted-foreground lg:block">
            Signed in as{" "}
            <span className="block truncate font-medium text-foreground" title={account.email ?? undefined}>
              {account.email}
            </span>
          </p>
          <Button
            size="sm"
            variant="ghost"
            disabled={loggingOut}
            onClick={() => void onLogOut()}
            className="lg:justify-start"
          >
            <LogOut aria-hidden />
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
