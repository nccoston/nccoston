# Stripe setup tasks for Medium Ball Knower (for Claude in Chrome)

You're helping me finish setting up my Stripe account in my browser. I'm logged in to Stripe
(dashboard.stripe.com) and Substack. I'm not technical, so do the clicking. Stop and ask me whenever a
step needs information only I have, or whenever the screen doesn't match these instructions.

## Background

- I run **Medium Ball Knower**, a paid Substack newsletter about Michigan football: $10/month, $100/year, or
  $150/year. It includes the newsletter, live audio call-in shows and a members-only Discord.
- Members pay through **Substack's Stripe integration**. Substack creates the subscriptions in my Stripe
  account. I have no paying members yet.
- My Stripe account is named **Medium Ball Knower** and has a **live** mode and a **sandbox**.

## Ground rules

- Change **only** the settings listed below. Don't touch payouts, bank details, products, prices, customers,
  subscriptions, refunds, webhooks, Connect, or anything else.
- **Don't delete anything.**
- **Don't add tax registrations** or turn on tax *collection* anywhere. Monitoring only.
- If an API key is shown on screen, **never type it into the chat or anywhere else**. Tell me to copy it
  into my password manager myself.
- Before clicking a final **Save / Create / Roll** button, tell me in one line what you're about to save.
  Then go ahead unless I say stop.
- Stripe's layout changes. If a menu isn't where this says, use the Dashboard's search bar or look around
  nearby, and tell me what you found.

---

## Task 1: Make sure you're in live mode

Open dashboard.stripe.com. If there's a **Sandbox** or **Test mode** banner, use the account switcher (top-left)
to switch to the live **Medium Ball Knower** account. Tasks 2–5 happen in **live mode**.

## Task 2: Confirm Substack uses this Stripe account

1. In a new tab, open my Substack dashboard → **Settings** → the **Payments** section.
2. Note which Stripe account is connected (name or email), or whether none is connected.
3. Compare it with the Stripe account's name and email (click the account name, top-left, in Stripe).
4. Tell me the result:
   - **Same account:** continue.
   - **Different account:** stop and tell me.
   - **None connected:** tell me, then continue. Don't connect anything yourself.

## Task 3: Turn on free tax threshold monitoring

1. Go to **Settings → Tax** (dashboard.stripe.com/settings/tax).
2. If Stripe asks to activate or get started with Stripe Tax, choose the free/monitoring path. Don't sign up
   for anything paid.
3. **Head office address:** if it's empty or wrong, **ask me** for my business address. Don't guess.
4. **Preset product tax code:** search "newsletter" and choose
   **Digital other news or documents – viewable only – subscription – with conditional rights**
   (code `txcd_10503005`).
5. **Default tax behavior / Include tax in prices:** choose **Exclusive** (tax added on top of the price).
6. Save.
7. **Don't add any registrations.** Open **Tax → Locations** (or "Registrations") just to confirm none
   are listed, and tell me what the page shows.

## Task 4: Make sure failed payments are retried

1. Go to **Settings → Billing → Subscriptions and emails**.
2. Find the failed-payments / **Retries** section. Make sure **Smart Retries** is on, with the recommended
   default schedule.
3. **Don't change any customer email settings** on that page. Substack may already send these emails.
4. Save if you changed anything. Tell me what the setting was before and after.

## Task 5: Create a read-only key for my revenue report

1. Go to **Developers → API keys** (dashboard.stripe.com/apikeys), still in live mode.
2. Click **Create restricted key**.
3. "Choose how you'll use this key": choose **Building your own integration**.
4. "Assign permissions": choose **Custom permissions**. Don't choose either Full access option.
5. Name: `Revenue report`
6. Set exactly these to **Read** (use the search box). Leave everything else at **None**:
   - Customers
   - Subscriptions
   - Products
   - Prices
   - Charges
7. Click **Create key**. Stripe may ask me to verify (password, code). If so, hand it to me.
8. When the key (`rk_live_...`) appears, **don't read it out or copy it anywhere**. Tell me:
   "Copy the key now and save it in your password manager." Wait for me to say done.

## Task 6: Roll the sandbox secret key

That key was pasted into a chat, so it needs replacing. This one is in the **sandbox**, not live.

1. Use the account switcher to open the **sandbox** for Medium Ball Knower.
2. Go to **Developers → API keys**.
3. On the **Secret key** row (`sk_test_...`), open the **⋯** menu → **Roll key**.
4. Set the old key to expire **Now**, then confirm **Roll key**. Verify if asked.
5. Don't copy or display the new key. I don't need it right now.
6. Switch back to live mode.

The sandbox has a test product and test customers named "Test Fan 1–8". Leave them alone.

---

## When you're done

Give me a short checklist:

- [ ] Substack ↔ Stripe account: same / different / not connected
- [ ] Tax: head office set, tax code `txcd_10503005`, behavior Exclusive, no registrations
- [ ] Smart Retries: on (was: ___)
- [ ] Restricted key "Revenue report" created, and I saved it
- [ ] Sandbox secret key rolled
- Anything that didn't match these instructions
