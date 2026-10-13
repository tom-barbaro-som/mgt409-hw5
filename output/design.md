# Campus Customs Operations Desk: dashboard design

The dashboard (`frontend/`, React + Vite + TypeScript) is built for one job: let a store manager watch the agent team work and make every money decision, without reading logs or raw JSON. Every design choice below follows from three goals: **calm enough to leave open all day**, **obvious when something needs a human**, and **honest about what has and hasn't happened**.

## Layout: three columns, one question each

```
┌─────────────────────────────── Yale-blue top bar ────────────────────────────────┐
│ 🐶 Handsome Dan badge · Campus Customs · desk date            Checking · live $  │
├──────────────┬──────────────────────────────────────────────┬────────────────────┤
│ Tickets      │ Selected ticket                              │ Needs your OK  (n) │
│ #101 ✓       │ facts · status line · [Start agent work]     │ approver name      │
│ #102 …       │ LIVE lanes + feed  →  after run: summary     │ approval cards     │
│ #103 …       │                                              │ [Approve] [Reject] │
└──────────────┴──────────────────────────────────────────────┴────────────────────┘
```

- **Left: "What's on the desk?"** Every ticket appears as a small card with its number, subject, requester, type, and one status pill. Clicking a card selects it. Only one ticket is in focus at a time, which matches the rule that the agents work one ticket at a time.
- **Center: "What's happening on this ticket?"** It shows the ticket facts (item, linked invoice or lease, the request, a plain-English status line), one primary button (**Start agent work**), and then the live view or the summary.
- **Right: "What do you need from me?"** The approval queue is always visible and sticky, so a pending payment can't scroll out of sight.
- Below about 1,150 px wide, the columns stack in the same order (tickets, work, approvals).
- **Minimalism:** white cards on a warm off-white background, one accent color, no charts, and no more than one primary button on screen. Status is shown with color *plus* text (never color alone), so it stays readable for color-blind users and at a glance.

## Yale / Handsome Dan styling
- **Palette:** Yale Blue `#00356B` for the top bar, headings, and the primary button; a lighter Yale blue `#286DC0` for focus and "working" states. Green, amber, and red are used only for status.
- **Type:** headings and money figures use a serif (Georgia), which echoes Yale's collegiate typography. Body text uses the system sans-serif for readability.
- **Handsome Dan:** an original, simple bulldog badge (SVG) with a "Y" collar tag sits in the header. It is a nod to the mascot, not the official mark.
  - The **Boss agent is Handsome Dan** (🐶 avatar, "Handsome Dan · decides"), since he runs the desk.
  - Small touches: the empty approval queue shows "Nothing waiting. 🐾", the live view's first line is "Handsome Dan is reading the ticket…", and the footer says "Boola Boola". Each touch is a single line, so the theme stays light and doesn't add clutter.

## How resolved tickets show up
- **Ticket lifecycle pills:** `Open` (gray) → `Agents working` (blue, gently pulsing) → `Run complete · needs you` (amber) → `✓ Resolved` (green). Resolved cards dim their subject, so open work stands out in the list. The header count shows "n open · n resolved".
- **"Resolved when the run is complete," done honestly.** When a run ends, payments are usually still pending, and closing the ticket then would hide money decisions. So:
  - If a run finishes with **nothing awaiting approval**, the backend marks the ticket resolved immediately.
  - Otherwise the ticket shows *Run complete · needs you*. The moment the manager decides the **last** pending request for that ticket (approve or reject), the backend marks it **✓ Resolved** automatically. That decision is noted on the ticket and in the audit trail.
- The status line underneath always explains why: "waiting on 1 human approval: #1 payment $840.00", or "Resolved. All requests decided by Tom Barbaro; ticket closed."

## Live cash balance
- The checking balance sits top right in large serif numerals, labeled **Checking · live** with a pulsing green dot (it turns red if the backend can't be reached).
- It refreshes every 2 seconds from `GET /api/cash`, and immediately after any approval. It changes **only when money actually moves**: drafted or pending payments never change it.
- When the balance changes, the card briefly flashes (red for money out) and shows the delta, for example **"−$840.00 just now"**, for six seconds, so a change can't go unnoticed.
- Underneath, a quiet line shows what's queued: "$840.00 awaiting you · $2,560.00 if all approved". The manager can see the cash pressure before approving.

## Human approval before any money moves
- Agents can only draft. Every payment, purchase order, discount, draft message, and token-budget request lands in **Needs your OK** with a count badge.
- Money requests (payments and POs) have an amber edge and show:
  - the amount;
  - the exact balance impact: "Checking $3,400.00 → $2,560.00";
  - the due date or estimated arrival;
  - red warnings when the balance would go negative, or when the vendor still has an unpaid invoice (these approvals will be refused).
- **Two-step approval for money:** "Approve payment…" opens a confirmation, "Send $840.00 from checking now? **Yes, pay** / Cancel". Nothing is paid on the first click.
- **Rejecting** requires a short reason, which the agents read on their next run.
- **Signed decisions:** the manager enters their name once ("Approving as"). It is remembered in the browser and recorded as `approved_by`; agent names are refused as approvers.
- **Message drafts** open in a collapsible preview labeled "it will **not** be sent". Approving a draft marks it approved-not-sent.

## How agents give live updates (without wasting tokens)
- **No extra model calls.** The live view only displays what the agents already write to the append-only audit trail. Nothing is summarized by an LLM after the fact, so monitoring costs **zero additional tokens**.
- **Polling every ~1.2 s:** `GET /api/events?run_id=…&after=<seq>` returns only new events, with a `seq` cursor.
- **One lane per agent (5 lanes):** avatar, name, and a state with a one-line latest action:
  - *Not involved yet* (faded)
  - **Working** (blue outline)
  - **Waiting on Inventory** (amber; shown when the agent has delegated)
  - **Done**

  This makes the sequential, one-or-two-agent delegation visible: you watch control pass Boss → Inventory → Accounting and back.
- **The feed shows major steps only**, newest at the bottom, with auto-scroll:
  - each agent's one-sentence reasoning (the "why" every agent states before acting, trimmed to its first sentence);
  - delegations ("asked accounting: …");
  - anything that **changed something** ("Requested payment #1: $840.00 to Bulldog Print Co");
  - refusals (in red);
  - each agent's final line.

  Routine lookups ("checked stock", "read ticket") only update the agent's lane, so the feed stays short.
- **After the run, the summary replaces the feed.** It shows:
  - the path taken (Boss → Inventory → Accounting), tokens used, and duration;
  - the Boss's decision;
  - one small card per agent that took part: who asked it, whom it asked, what it *did* (bulleted actions), what it *checked* (gray chips), and its one-line conclusion.

  The summary is built from the audit trail, so it also works after a page reload or server restart.

## Small usability details
- A banner explains exactly how to start the backend if it isn't reachable.
- Only one run at a time: the Start button explains why it's disabled ("Agents are busy on ticket #103").
- Toasts confirm every decision ("#1 approved. Paid $840.00; checking now $2,560.00. Ticket 101 resolved.").
- **Reset demo data** sits in the footer, away from the work area, behind a confirmation dialog.
