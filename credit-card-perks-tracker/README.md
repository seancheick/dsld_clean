# Perks Ledger

A self-contained, single-file web app for tracking credit-card benefits: add the
cards you carry and every credit, perk, and discount they offer shows up in one
ledger — with per-period checkboxes, reset countdowns, and redemption totals.

## Features

- **Built-in database of 41 popular U.S. cards** (Amex Platinum/Gold, Chase
  Sapphire Reserve/Preferred, Ink business cards, Venture X, Delta/Hilton/
  Marriott co-brands, Citi Strata, Bilt original + Obsidian, Bank of America
  rewards cards, and more), with benefit values verified early July 2026 —
  including the 2025–26 refreshes (Amex Platinum $895, CSR $795, CSP June 2026,
  Bilt 2.0).
- **Tracking by reset cadence** — monthly, quarterly, semiannual, yearly, and
  one-time/every-4-years credits each get a checkbox keyed to the current
  period, so they reset automatically when the month/quarter/half/year rolls over.
- **"Use it or lose it"** strip surfaces unused dollar credits that reset soon.
- **Totals** — annual credits on tap, estimated redeemed so far this year,
  annual fees, and net perks-vs-fees.
- **Group and filter** by reset schedule, card, or category; search; hide
  redeemed; dollar-credits-only.
- **Custom cards and custom perks** for anything not in the database; built-in
  perks your card doesn't have can be hidden.
- **Local-only data** — state lives in `localStorage`; export/import as JSON.

## Running it

Open `index.html` in a browser, or deploy it as a Claude Artifact. The file is
written as an HTML fragment (no `<html>/<head>/<body>` wrapper) so the artifact
platform can wrap it; browsers render it fine standalone as well. Everything —
styles, script, card data, and the Fraunces display font — is inlined, so it
works offline with no external requests.

## Caveats

Issuers change benefits constantly. Amounts here were verified against issuer
pages and card guides in early July 2026 — treat the app as a checklist and
confirm in your card's app before booking. Redemption totals are estimates that
divide each perk's annual value evenly across its reset periods.
