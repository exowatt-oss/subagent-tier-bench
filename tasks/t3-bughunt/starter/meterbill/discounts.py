"""Coupon discounts."""

from .money import plain, round_money


def describe_coupon(coupon):
    """``Coupon WELCOME10 (10% off)`` or ``Coupon SAVE20 (20.00 off)``."""
    if coupon.kind == "percent":
        return "Coupon %s (%s%% off)" % (coupon.code, plain(coupon.value))
    return "Coupon %s (%s off)" % (coupon.code, coupon.value)


def _discount(coupon, running):
    if coupon.kind == "percent":
        return round_money(running * coupon.value / 100)
    return min(coupon.value, running)


def apply_coupons(subtotal, coupons):
    """Apply an account's coupons to ``subtotal`` (DESIGN.md, "Coupons").

    Returns ``[(coupon, discount), ...]`` in application order, where each
    discount is a positive amount. Coupons that end up giving nothing are left
    out.
    """
    running = subtotal
    applied = []
    for coupon in coupons:
        if running <= 0:
            break
        amount = _discount(coupon, running)
        if amount <= 0:
            continue
        running -= amount
        applied.append((coupon, amount))
    return applied
