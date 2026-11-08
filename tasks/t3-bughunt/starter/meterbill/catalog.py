"""Price plans and the price book that serves tier tables to the rating engine."""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .errors import InputError
from .money import ZERO, parse_decimal, parse_money
from .units import is_unit

PRICING_MODELS = ("graduated", "volume")


@dataclass(frozen=True)
class MetricPrice:
    metric: str
    label: str
    unit: str
    pricing: str
    included: Decimal
    tiers: tuple


@dataclass(frozen=True)
class Plan:
    plan_id: str
    name: str
    base_fee: Decimal
    minimum_commit: Decimal
    metrics: tuple

    def metric(self, metric_id):
        for item in self.metrics:
            if item.metric == metric_id:
                return item
        return None


def _parse_metric(data, where):
    if not isinstance(data, dict):
        raise InputError("%s: expected an object" % where)
    metric = str(data.get("metric") or "").strip()
    if not metric:
        raise InputError("%s: missing metric" % where)
    where = "%s (%s)" % (where, metric)
    unit = data.get("unit")
    if not is_unit(unit):
        raise InputError("%s: unknown unit %r" % (where, unit))
    pricing = data.get("pricing", "graduated")
    if pricing not in PRICING_MODELS:
        raise InputError("%s: pricing must be graduated or volume" % where)
    included = parse_decimal(data.get("included", 0), "%s included" % where)
    if included < 0:
        raise InputError("%s: included must not be negative" % where)
    raw_tiers = data.get("tiers")
    if not isinstance(raw_tiers, list) or not raw_tiers:
        raise InputError("%s: at least one tier is required" % where)
    tiers = []
    for index, tier in enumerate(raw_tiers):
        if not isinstance(tier, dict):
            raise InputError("%s: tier %d must be an object" % (where, index + 1))
        up_to = tier.get("up_to")
        up_to = None if up_to is None else parse_decimal(up_to, "%s tier %d up_to" % (where, index + 1))
        price = parse_decimal(tier.get("unit_price"), "%s tier %d unit_price" % (where, index + 1))
        tiers.append((up_to, price))
    return MetricPrice(
        metric=metric,
        label=str(data.get("label") or metric),
        unit=unit,
        pricing=pricing,
        included=included,
        tiers=tuple(tiers),
    )


def parse_plan(data, where="plan"):
    """Build a ``Plan`` from its JSON object."""
    if not isinstance(data, dict):
        raise InputError("%s: expected an object" % where)
    plan_id = str(data.get("id") or "").strip()
    if not plan_id:
        raise InputError("%s: missing id" % where)
    where = "plan %s" % plan_id
    metrics = []
    seen = set()
    for index, item in enumerate(data.get("metrics") or []):
        metric = _parse_metric(item, "%s metric %d" % (where, index + 1))
        if metric.metric in seen:
            raise InputError("%s: duplicate metric %s" % (where, metric.metric))
        seen.add(metric.metric)
        metrics.append(metric)
    return Plan(
        plan_id=plan_id,
        name=str(data.get("name") or plan_id),
        base_fee=parse_money(data.get("base_fee", "0"), "%s base_fee" % where),
        minimum_commit=parse_money(data.get("minimum_commit", "0"), "%s minimum_commit" % where),
        metrics=tuple(metrics),
    )


def compile_tiers(metric_price):
    """Validate a metric's tiers and return them as ``((up_to, unit_price), ...)``.

    ``up_to`` values must be positive and strictly increasing; only the last tier
    may (and must) be unbounded (``None``); unit prices must not be negative.
    """
    compiled = []
    previous = ZERO
    count = len(metric_price.tiers)
    for index, (up_to, price) in enumerate(metric_price.tiers):
        label = "metric %s tier %d" % (metric_price.metric, index + 1)
        if price < 0:
            raise InputError("%s: unit_price must not be negative" % label)
        last = index == count - 1
        if up_to is None:
            if not last:
                raise InputError("%s: only the last tier may be unbounded" % label)
        else:
            if last:
                raise InputError("%s: the last tier must be unbounded (up_to: null)" % label)
            if up_to <= previous:
                raise InputError("%s: up_to must increase" % label)
            previous = up_to
        compiled.append((up_to, price))
    return tuple(compiled)


def _read_json(path, what):
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle, parse_float=Decimal)
    except FileNotFoundError:
        raise InputError("%s not found: %s" % (what, path)) from None
    except ValueError as exc:
        raise InputError("%s: invalid JSON (%s)" % (path.name, exc)) from None


def _plan_list(data, path):
    items = data.get("plans") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise InputError("%s: expected {\"plans\": [...]}" % Path(path).name)
    return items


class PriceBook:
    """All known plans plus a per-(plan, metric) cache of compiled tier tables."""

    def __init__(self, plans=()):
        self._plans = {}
        self._compiled = {}
        for plan in plans:
            if plan.plan_id in self._plans:
                raise InputError("duplicate plan %s" % plan.plan_id)
            self._plans[plan.plan_id] = plan

    @classmethod
    def from_dict(cls, data):
        items = data.get("plans") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise InputError("expected {\"plans\": [...]}")
        return cls(parse_plan(item, "plans[%d]" % index) for index, item in enumerate(items))

    @classmethod
    def load(cls, path):
        data = _read_json(path, "plans file")
        items = _plan_list(data, path)
        return cls(parse_plan(item, "plans[%d]" % index) for index, item in enumerate(items))

    def __contains__(self, plan_id):
        return plan_id in self._plans

    def plan_ids(self):
        return sorted(self._plans)

    def plan(self, plan_id):
        try:
            return self._plans[plan_id]
        except KeyError:
            raise InputError("unknown plan %r" % (plan_id,)) from None

    def tiers(self, plan_id, metric):
        """Compiled tiers of one metric of one plan (cached)."""
        key = (plan_id, metric)
        compiled = self._compiled.get(key)
        if compiled is None:
            metric_price = self.plan(plan_id).metric(metric)
            if metric_price is None:
                raise InputError("plan %s has no metric %r" % (plan_id, metric))
            compiled = compile_tiers(metric_price)
            self._compiled[key] = compiled
        return compiled

    def validate(self):
        """Compile every tier table once so that bad plans fail early."""
        for plan_id in self.plan_ids():
            for metric_price in self._plans[plan_id].metrics:
                self.tiers(plan_id, metric_price.metric)

    def update_plan(self, plan):
        """Add a plan or replace the plan with the same id (takes effect immediately)."""
        if isinstance(plan, dict):
            plan = parse_plan(plan)
        for metric_price in plan.metrics:
            compile_tiers(metric_price)
        self._plans[plan.plan_id] = plan

    def apply_overrides(self, path):
        """Apply a price-overrides file: every plan in it replaces or adds a plan."""
        data = _read_json(path, "price overrides file")
        for index, item in enumerate(_plan_list(data, path)):
            self.update_plan(parse_plan(item, "overrides plans[%d]" % index))
