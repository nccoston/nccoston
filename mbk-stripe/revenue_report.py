#!/usr/bin/env python3
"""Monthly membership report for Medium Ball Knower, read straight from Stripe.

Substack creates the subscriptions in your Stripe account; this script only
reads them. It never creates, changes or charges anything.

Usage:
    STRIPE_API_KEY=rk_live_... python3 revenue_report.py            # this month
    STRIPE_API_KEY=rk_live_... python3 revenue_report.py 2026-10    # a past month

Needs only Python 3 (no packages to install). Use a *restricted* key with
read-only access to Subscriptions, Customers, Products, Prices and Charges.
"""

import base64
import calendar
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.stripe.com/v1/"
LIVE_STATUSES = {"active", "trialing", "past_due"}
MONTHS_PER_INTERVAL = {"day": 12 / 365, "week": 12 / 52, "month": 1, "year": 12}


def get(path, params, key):
    url = API + path + "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Basic " + base64.b64encode((key + ":").encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        msg = json.loads(e.read() or b"{}").get("error", {}).get("message", str(e))
        sys.exit(f"Stripe said: {msg}")


def list_all(path, params, key):
    params = dict(params, limit=100)
    while True:
        page = get(path, params, key)
        yield from page["data"]
        if not page.get("has_more"):
            return
        params["starting_after"] = page["data"][-1]["id"]


def month_bounds(arg):
    today = dt.date.today()
    year, month = (int(x) for x in arg.split("-")) if arg else (today.year, today.month)
    start = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
    end = start + dt.timedelta(days=calendar.monthrange(year, month)[1])
    return start, end


def money(cents):
    return f"${cents / 100:,.2f}"


def plan_label(price, product_names):
    rec = price.get("recurring") or {}
    every = rec.get("interval_count", 1)
    interval = rec.get("interval", "?")
    per = interval if every == 1 else f"{every} {interval}s"
    name = price.get("nickname") or product_names.get(price.get("product"), "Plan")
    return f"{name} ({money(price.get('unit_amount') or 0)}/{per})"


def monthly_value(item):
    """List-price value of one subscription item, spread evenly per month."""
    price = item["price"]
    rec = price.get("recurring") or {}
    per_month = MONTHS_PER_INTERVAL.get(rec.get("interval"), 0) * rec.get("interval_count", 1)
    if not per_month:
        return 0
    return (price.get("unit_amount") or 0) * item.get("quantity", 1) / per_month


def main():
    key = os.environ.get("STRIPE_API_KEY")
    if not key:
        sys.exit("Set STRIPE_API_KEY first (a read-only restricted key is best).")
    start, end = month_bounds(sys.argv[1] if len(sys.argv) > 1 else None)
    t0, t1 = int(start.timestamp()), int(end.timestamp())

    product_names = {p["id"]: p["name"] for p in list_all("products", {}, key)}
    subs = list(list_all("subscriptions", {"status": "all", "expand[]": "data.items.data.price"}, key))

    live = [s for s in subs if s["status"] in LIVE_STATUSES]
    by_plan = {}
    mrr = 0
    for s in live:
        for item in s["items"]["data"]:
            label = plan_label(item["price"], product_names)
            by_plan[label] = by_plan.get(label, 0) + 1
            mrr += monthly_value(item)

    new = [s for s in subs if t0 <= s["created"] < t1]
    ended = [s for s in subs if s["status"] == "canceled" and t0 <= (s.get("ended_at") or 0) < t1]
    leaving = [s for s in live if s.get("cancel_at_period_end") or s.get("cancel_at")]
    past_due = [s for s in live if s["status"] == "past_due"]

    collected = refunded = 0
    payments = 0
    for c in list_all("charges", {"created[gte]": t0, "created[lt]": t1}, key):
        if c.get("paid") and c.get("status") == "succeeded":
            payments += 1
            collected += c["amount"]
            refunded += c.get("amount_refunded", 0)

    print(f"Medium Ball Knower — {start:%B %Y}")
    print("=" * 40)
    print(f"Paying members right now:   {len(live)}")
    for label, n in sorted(by_plan.items(), key=lambda kv: -kv[1]):
        print(f"  {label}: {n}")
    print(f"Monthly recurring revenue:  {money(mrr)}  (annual plans counted as 1/12 per month)")
    print(f"Yearly run rate:            {money(mrr * 12)}")
    print()
    print(f"New subscriptions in {start:%B}:   {len(new)}")
    print(f"Subscriptions that ended:   {len(ended)}")
    print(f"Set to cancel at renewal:   {len(leaving)}")
    print(f"Card failing (past due):    {len(past_due)}")
    print()
    print(f"Payments collected:         {money(collected)} from {payments} payments")
    if refunded:
        print(f"Refunded:                   {money(refunded)}")
    print()
    print("Revenue uses list prices before discounts, and before Substack's and Stripe's fees.")


if __name__ == "__main__":
    main()
