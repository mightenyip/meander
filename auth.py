#!/usr/bin/env python3
"""
Auth & Usage Tracking - Supabase integration
Handles free tier usage limits and paid subscription checks
"""

import os
import re
from datetime import datetime, timezone
from supabase import create_client, Client

# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------

def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment variables."
        )
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Free tier usage tracking
#
# Supabase table required:
#
#   CREATE TABLE free_usage (
#     id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
#     email       text NOT NULL UNIQUE,
#     used_at     timestamptz NOT NULL DEFAULT now(),
#     script_name text
#   );
#
# ---------------------------------------------------------------------------

FREE_TIER_LIMIT = 1  # number of free parses allowed per email


def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def get_free_usage(email: str) -> int:
    """Return how many free parses this email has used (0 if none)."""
    client = get_supabase_client()
    result = (
        client.table("free_usage")
        .select("id")
        .eq("email", email.lower().strip())
        .execute()
    )
    return len(result.data)


def record_free_usage(email: str, script_name: str = "") -> None:
    """Record a free parse use for this email."""
    client = get_supabase_client()
    client.table("free_usage").insert({
        "email": email.lower().strip(),
        "used_at": datetime.now(timezone.utc).isoformat(),
        "script_name": script_name
    }).execute()


def has_free_uses_remaining(email: str) -> bool:
    """Return True if this email still has free parses left."""
    return get_free_usage(email) < FREE_TIER_LIMIT


# ---------------------------------------------------------------------------
# Subscription checks (paid tier)
#
# Supabase table required:
#
#   CREATE TABLE subscribers (
#     id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
#     email               text NOT NULL UNIQUE,
#     stripe_customer_id  text,
#     stripe_sub_id       text,
#     plan                text NOT NULL DEFAULT 'pro',  -- 'pro' | 'team'
#     status              text NOT NULL DEFAULT 'active',  -- 'active' | 'cancelled' | 'past_due'
#     created_at          timestamptz NOT NULL DEFAULT now(),
#     updated_at          timestamptz NOT NULL DEFAULT now()
#   );
#
# ---------------------------------------------------------------------------

def get_subscription(email: str) -> dict | None:
    """
    Return the subscriber row for this email, or None if not subscribed.
    Only returns rows where status = 'active'.
    """
    client = get_supabase_client()
    result = (
        client.table("subscribers")
        .select("*")
        .eq("email", email.lower().strip())
        .eq("status", "active")
        .execute()
    )
    return result.data[0] if result.data else None


def is_subscribed(email: str) -> bool:
    """Return True if this email has an active paid subscription."""
    return get_subscription(email) is not None


def get_plan(email: str) -> str | None:
    """
    Return the plan name for this email ('pro', 'team'), or None if not subscribed.
    """
    sub = get_subscription(email)
    return sub["plan"] if sub else None


def upsert_subscriber(
    email: str,
    stripe_customer_id: str,
    stripe_sub_id: str,
    plan: str,
    status: str
) -> None:
    """
    Insert or update a subscriber row. Called from the Stripe webhook handler
    when a subscription is created, updated, or cancelled.
    """
    client = get_supabase_client()
    client.table("subscribers").upsert({
        "email": email.lower().strip(),
        "stripe_customer_id": stripe_customer_id,
        "stripe_sub_id": stripe_sub_id,
        "plan": plan,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }, on_conflict="email").execute()


# ---------------------------------------------------------------------------
# Combined access check helpers for the UI
# ---------------------------------------------------------------------------

class AccessLevel:
    NONE = "none"          # No email provided
    FREE_REMAINING = "free_remaining"  # Has free uses left
    FREE_EXHAUSTED = "free_exhausted"  # Used up free tier, not subscribed
    PRO = "pro"            # Active Pro subscription
    TEAM = "team"          # Active Team subscription


def get_access_level(email: str) -> str:
    """
    Given an email, return the user's current access level.
    This is the main function the UI should call.
    """
    if not email or not is_valid_email(email):
        return AccessLevel.NONE
    
    # Check paid subscription first
    plan = get_plan(email)
    if plan == "team":
        return AccessLevel.TEAM
    if plan == "pro":
        return AccessLevel.PRO
    
    # Check free tier
    if has_free_uses_remaining(email):
        return AccessLevel.FREE_REMAINING
    
    return AccessLevel.FREE_EXHAUSTED


def can_use_single_script(access: str) -> bool:
    return access in (AccessLevel.FREE_REMAINING, AccessLevel.PRO, AccessLevel.TEAM)


def can_use_batch(access: str) -> bool:
    """Batch processing is a paid-only feature."""
    return access in (AccessLevel.PRO, AccessLevel.TEAM)
