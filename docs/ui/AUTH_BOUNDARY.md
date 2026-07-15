# Trade Desk authentication boundary

The shell now has a single operator/account slot so authentication can be introduced without threading auth conditionals through every visual component.

## Clerk integration plan

The app does not currently have Clerk installed or user-scoped persistence. Before enabling a live deployment:

1. Add `@clerk/nextjs` and configure `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` plus `CLERK_SECRET_KEY` in the deployment environment.
2. Wrap `DeskShell` with `ClerkProvider` in `src/app/layout.tsx`.
3. Add `src/middleware.ts` with `clerkMiddleware()` for application and API request context.
4. Add a server-only `src/lib/auth.ts` helper and call it at each API boundary, especially trade, positions, portfolio, live-plan, live-adapt, evolve, and backtest routes.
5. Replace the shell's static operator slot with Clerk's `UserButton` / sign-in entry point.
6. Pass the authenticated `userId` through the data boundary before enabling multiple accounts. Current ledgers, run artifacts, and scan state are repository-shared.

Do not treat middleware alone as authorization. Mutating API routes must enforce identity near the resource they access, and state must be partitioned by user before exposing this to multiple operators.
