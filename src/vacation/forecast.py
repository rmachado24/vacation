from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

THREE_DP = Decimal("0.001")
EIGHT_HOURS = Decimal("8.000")


@dataclass(frozen=True)
class PlannedUse:
    start_date: date
    end_date: date
    event_name: str = ""
    hours_per_day: Decimal = EIGHT_HOURS


@dataclass(frozen=True)
class PayPeriodForecast:
    period_start: date
    period_end: date
    paycheck_date: date
    service_year: int
    annual_hours: int
    accrual_hours: Decimal
    accrued_capped_out_hours: Decimal
    vacation_use_hours: Decimal
    floating_use_hours: Decimal
    vacation_balance_after: Decimal
    floating_balance_after: Decimal


def _quantize_hours(hours: Decimal) -> Decimal:
    return hours.quantize(THREE_DP, rounding=ROUND_HALF_UP)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = (date(year, month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _observed_if_weekend(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def observed_holidays(year: int) -> set[date]:
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    return {
        _observed_if_weekend(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _last_weekday(year, 5, 0),
        _observed_if_weekend(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _observed_if_weekend(date(year, 11, 11)),
        thanksgiving,
        thanksgiving + timedelta(days=1),
        _observed_if_weekend(date(year, 12, 24)),
        _observed_if_weekend(date(year, 12, 25)),
        _observed_if_weekend(date(year, 12, 31)),
    }


def service_year_on_day(hire_date: date, day: date) -> int:
    years = day.year - hire_date.year
    before_anniversary = (day.month, day.day) < (hire_date.month, hire_date.day)
    return years if before_anniversary else years + 1


def annual_accrual_for_service_year(service_year: int) -> int:
    if service_year <= 2:
        return 80
    if service_year <= 5:
        return 120
    if service_year <= 14:
        return 168
    if service_year <= 24:
        return 200
    return 224


def accrual_per_pay_period(service_year: int) -> Decimal:
    return _quantize_hours(Decimal(annual_accrual_for_service_year(service_year)) / Decimal(24))


def _period_start_for_paycheck(paycheck_date: date) -> date:
    # The first paycheck (for the prior 16th-end period) lands around the 5th.
    # It can shift a few days for weekends/holidays, so use a small cushion.
    if paycheck_date.day <= 10:
        prev_month_last = paycheck_date.replace(day=1) - timedelta(days=1)
        return prev_month_last.replace(day=16)
    return paycheck_date.replace(day=1)


def _next_pay_period(start: date) -> tuple[date, date, date]:
    if start.day == 1:
        return start.replace(day=15), start.replace(day=20), start.replace(day=16)
    period_end = (start.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    next_month = (start.replace(day=1) + timedelta(days=32)).replace(day=1)
    return period_end, next_month.replace(day=5), next_month


def _count_chargeable_days(start: date, end: date) -> int:
    days = 0
    d = start
    by_year = {}
    while d <= end:
        if d.weekday() < 5:
            if d.year not in by_year:
                by_year[d.year] = observed_holidays(d.year)
            if d not in by_year[d.year]:
                days += 1
        d += timedelta(days=1)
    return days


def _is_chargeable_day(d: date, by_year: dict[int, set[date]]) -> bool:
    if d.weekday() >= 5:
        return False
    if d.year not in by_year:
        by_year[d.year] = observed_holidays(d.year)
    return d not in by_year[d.year]


def _eligible_for_floating(hire_date: date, day: date) -> bool:
    target_year = hire_date.year + ((hire_date.month - 1 + 6) // 12)
    target_month = ((hire_date.month - 1 + 6) % 12) + 1
    target_day = min(hire_date.day, _last_day_of_month(target_year, target_month))
    eligible_on = date(target_year, target_month, target_day)
    return day >= eligible_on


def _last_day_of_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def build_forecast(
    hire_date: date,
    last_paycheck_date: date,
    balance_on_last_paycheck: Decimal,
    planned_uses: list[PlannedUse],
    periods_ahead: int = 48,
    floating_used_this_year: bool = False,
) -> list[PayPeriodForecast]:
    start = _period_start_for_paycheck(last_paycheck_date)
    _, _, start = _next_pay_period(start)

    planned = sorted(planned_uses, key=lambda p: p.start_date)
    vacation_balance = _quantize_hours(balance_on_last_paycheck)
    floating_balance = Decimal("0.000")
    floating_used_years: set[int] = set()
    if floating_used_this_year:
        floating_used_years.add(last_paycheck_date.year)
    elif _eligible_for_floating(hire_date, last_paycheck_date):
        # Carry baseline availability: if the current-year floating holiday has not
        # been marked used, treat it as available at/after the first paycheck cycle.
        if last_paycheck_date.month > 1 or (last_paycheck_date.month == 1 and last_paycheck_date.day >= 10):
            floating_balance = EIGHT_HOURS
    rows: list[PayPeriodForecast] = []

    for _ in range(periods_ahead):
        period_end, paycheck, next_start = _next_pay_period(start)
        service_year = service_year_on_day(hire_date, period_end)
        annual = annual_accrual_for_service_year(service_year)
        cap = Decimal(annual * 2)
        accrual = accrual_per_pay_period(service_year)

        raw = vacation_balance + accrual
        vacation_balance = _quantize_hours(min(raw, cap))
        capped_out = _quantize_hours(max(Decimal("0"), raw - cap))

        # Grant the annual floating holiday at the first paycheck cycle of the year
        # (the period that started Dec 16 and ends Dec 31), regardless of exact pay date shift.
        if (
            paycheck.month == 1
            and start.month == 12
            and start.day == 16
            and paycheck.year not in floating_used_years
            and _eligible_for_floating(hire_date, paycheck)
        ):
            floating_balance = EIGHT_HOURS

        vac_use = Decimal("0")
        daily_scheduled_use: dict[date, Decimal] = {}
        holiday_cache: dict[int, set[date]] = {}
        for plan in planned:
            if plan.end_date < start or plan.start_date > period_end:
                continue
            overlap_start = max(plan.start_date, start)
            overlap_end = min(plan.end_date, period_end)
            d = overlap_start
            while d <= overlap_end:
                if _is_chargeable_day(d, holiday_cache):
                    daily_scheduled_use[d] = _quantize_hours(daily_scheduled_use.get(d, Decimal("0")) + plan.hours_per_day)
                d += timedelta(days=1)

        for day_use in daily_scheduled_use.values():
            vac_use = _quantize_hours(vac_use + day_use)

        vac_use = _quantize_hours(vac_use)
        flo_use = Decimal("0.000")
        usage_year = period_end.year
        if (
            any(day_use >= EIGHT_HOURS for day_use in daily_scheduled_use.values())
            and usage_year not in floating_used_years
            and floating_balance >= EIGHT_HOURS
            and _eligible_for_floating(hire_date, period_end)
        ):
            flo_use = EIGHT_HOURS
            floating_used_years.add(usage_year)
            vac_use = _quantize_hours(vac_use - flo_use)

        vacation_balance = _quantize_hours(vacation_balance - vac_use)
        floating_balance = _quantize_hours(max(Decimal("0"), floating_balance - flo_use))

        rows.append(PayPeriodForecast(start, period_end, paycheck, service_year, annual, accrual, capped_out, vac_use, flo_use, vacation_balance, floating_balance))
        start = next_start

    return rows
