#!/usr/bin/env python3
"""
Stripe Helpers - Payment integration
Handles checkout session creation and webhook processing
"""

import os
import stripe
from auth import upsert_subscriber

# ---------------------------------------------------------------------------
# Stripe client setup
# ---------------------------------------------------------------------------

def get_stripe_client():
    api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not api_key:
        raise EnvironmentError("STRIPE_SECRET_KEY must be set in environment variables.")
    stripe.api_key = api_key
    return stripe


# ---------------------------------------------------------------------------
# Pricing config
#
# Set these Price IDs after creating products in your Stripe dashboard:
#   https://dashboard.stripe.com/products
#
# ---------------------------------------------------------------------------

PLANS = {
    "pro": {
        "name": "Pro",
        "price_id": os.environ.get("STRIPE_PRICE_ID_PRO", ""),
        "price_display": "$9 / month",
        "features": [
            "Unlimited single script parsing",
            "Batch processing (up to 8 episodes)",
            "All export formats (JSON, CSV)",
            "Location breakdown across seasons",
            "Character analysis across episodes",
        ]
    }
}

FREE_PLAN = {
    "name": "Free",
    "price_display": "$0",
    "features": [
        "1 free script parse",
        "Scene and character breakdown",
        "Basic export (JSON, CSV)",
    ]
}


# ---------------------------------------------------------------------------
# Checkout session
# ---------------------------------------------------------------------------

def create_checkout_session(email: str, plan: str, success_url: str, cancel_url: str) -> str:
    """
    Create a Stripe Checkout session for the given plan and return the session URL.
    The user is redirected to this URL to complete payment.
    """
    stripe_client = get_stripe_client()
    
    plan_config = PLANS.get(plan)
    if not plan_config:
        raise ValueError(f"Unknown plan: {plan}")
    
    price_id = plan_config["price_id"]
    if not price_id:
        raise EnvironmentError(
            f"STRIPE_PRICE_ID_{plan.upper()} is not set. "
            "Create a product in your Stripe dashboard and set the env var."
        )
    
    session = stripe_client.checkout.Session.create(
        customer_email=email,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"plan": plan}
    )
    
    return session.url


# ---------------------------------------------------------------------------
# Webhook handler
#
# Stripe sends events to your webhook endpoint when subscriptions change.
# You need to expose a route for this. For Streamlit, the simplest approach
# is to use a lightweight companion server (see notes in .env.example).
#
# Events handled:
#   - checkout.session.completed   → new subscriber
#   - customer.subscription.updated → plan change
#   - customer.subscription.deleted → cancellation
# ---------------------------------------------------------------------------

def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Verify and process a Stripe webhook event.
    Returns a dict with 'status' and optional 'message'.
    """
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise EnvironmentError("STRIPE_WEBHOOK_SECRET must be set.")
    
    stripe_client = get_stripe_client()
    
    try:
        event = stripe_client.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        return {"status": "error", "message": "Invalid webhook signature"}
    
    event_type = event["type"]
    
    if event_type == "checkout.session.completed":
        _handle_checkout_completed(event["data"]["object"], stripe_client)
    
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(event["data"]["object"], stripe_client)
    
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(event["data"]["object"], stripe_client)
    
    return {"status": "ok"}


def _handle_checkout_completed(session, stripe_client):
    """New subscription created via checkout."""
    customer_id = session.get("customer")
    sub_id = session.get("subscription")
    email = session.get("customer_email") or session.get("customer_details", {}).get("email", "")
    plan = session.get("metadata", {}).get("plan", "pro")
    
    if email and customer_id and sub_id:
        upsert_subscriber(
            email=email,
            stripe_customer_id=customer_id,
            stripe_sub_id=sub_id,
            plan=plan,
            status="active"
        )


def _handle_subscription_updated(subscription, stripe_client):
    """Subscription changed (plan change, payment issue, etc.)."""
    customer_id = subscription.get("customer")
    sub_id = subscription.get("id")
    status = subscription.get("status")  # active, past_due, cancelled, etc.
    
    # Map Stripe statuses
    internal_status = "active" if status == "active" else status
    
    # Look up email from Stripe customer
    customer = stripe_client.Customer.retrieve(customer_id)
    email = customer.get("email", "")
    
    if email:
        # Determine plan from price ID
        items = subscription.get("items", {}).get("data", [])
        plan = _plan_from_price_id(items[0]["price"]["id"]) if items else "pro"
        
        upsert_subscriber(
            email=email,
            stripe_customer_id=customer_id,
            stripe_sub_id=sub_id,
            plan=plan,
            status=internal_status
        )


def _handle_subscription_deleted(subscription, stripe_client):
    """Subscription cancelled."""
    customer_id = subscription.get("customer")
    sub_id = subscription.get("id")
    
    customer = stripe_client.Customer.retrieve(customer_id)
    email = customer.get("email", "")
    
    if email:
        upsert_subscriber(
            email=email,
            stripe_customer_id=customer_id,
            stripe_sub_id=sub_id,
            plan="pro",
            status="cancelled"
        )


def _plan_from_price_id(price_id: str) -> str:
    """Reverse-lookup plan name from a Stripe Price ID."""
    for plan_name, plan_config in PLANS.items():
        if plan_config["price_id"] == price_id:
            return plan_name
    return "pro"
