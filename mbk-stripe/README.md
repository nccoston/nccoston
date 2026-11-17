# Medium Ball Knower × Stripe

Members subscribe on Substack, and Substack creates their subscriptions in the Medium Ball Knower Stripe account.
This folder works alongside that setup and doesn't replace it. Nothing here charges anyone or changes a subscription.

## 1. Sales tax monitoring (free, about 5 minutes, all in the Stripe Dashboard)

Do this in **live mode**, the account Substack is connected to:

1. Open **Settings → Tax** (dashboard.stripe.com/settings/tax).
2. **Head office address:** your business address. Stripe can't watch your thresholds until this is set.
3. **Preset product tax code:** *Digital other news or documents – viewable only – subscription – with conditional rights*
   (`txcd_10503005`). It's the closest fit for a paid newsletter. Ask your accountant whether the live shows and
   Discord access change that.
4. **Default tax behavior:** *Exclusive* (tax would be added on top of $10 / $100 / $150).
5. Leave **Registrations** empty for now. Stripe will flag a state under **Tax → Locations → Needs attention** once
   your sales there cross that state's threshold. Only then do you need to register and start collecting.

The same settings are already applied in the sandbox, except the head office address, which only you can enter.

## 2. Monthly revenue report

`revenue_report.py` prints paying members by plan, monthly recurring revenue, new and ended subscriptions, members set
to cancel, failing cards, and payments collected.

**Make a read-only key** (Dashboard → Developers → API keys → *Create a secret key* → *Building your own
integration* → *Custom permissions*), named "Revenue report", with **Read** on: Customers, Subscriptions, Products,
Prices, Charges and Refunds. Everything else: None. Done on Nov 17, 2026 (key ends `tYl7`, stored in the owner's
password manager).

**Run it** (Mac Terminal):

```bash
STRIPE_API_KEY=rk_live_your_key_here python3 revenue_report.py
```

Add a month for a past report, e.g. `python3 revenue_report.py 2026-10`. Don't save the key in this folder or commit it.

Sample output from the sandbox:

```
Medium Ball Knower — November 2026
========================================
Paying members right now:   7
  Annual ($100.00/year): 3
  Monthly ($10.00/month): 3
  Annual (Founding) ($150.00/year): 1
Monthly recurring revenue:  $67.50  (annual plans counted as 1/12 per month)
Yearly run rate:            $810.00

New subscriptions in November:   8
Subscriptions that ended:   1
Set to cancel at renewal:   1
Card failing (past due):    0

Payments collected:         $490.00 from 8 payments
```

Revenue uses list prices before discounts, and before Substack's and Stripe's fees. Plan names come from whatever
Substack named its prices in Stripe.

## Already handled by Substack, so nothing to build here

Checkout, the plan picker, cancel/upgrade/update-card, failed-payment retries and receipts. Smart Retries is
on (Settings → Billing → Subscriptions and emails → Manage failed payments → Card payments). Customer emails are
left to Substack.
