from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from vacation.forecast import PlannedUse, build_forecast, accrual_per_pay_period, service_year_on_day

DATA_PATH = Path("data/user_data.json")
FORECAST_TABLE_COLUMNS = [
    "Period Start",
    "Period End",
    "Paycheck Date",
    "Service Year",
    "Annual Accrual",
    "Accrual This Period",
    "Capped Out This Period",
    "Vacation Used",
    "Floating Used",
    "Vacation Balance",
    "Floating Balance",
]


def _default_plans_df() -> pd.DataFrame:
    return pd.DataFrame([{"include": True, "event_name": "", "start_date": None, "end_date": None, "hours_per_day": 8.0}])


def _normalize_plans_df(plans_df: pd.DataFrame) -> pd.DataFrame:
    df = plans_df.copy()
    for col in ("start_date", "end_date"):
        if col not in df.columns:
            df[col] = None
        parsed = pd.to_datetime(df[col], errors="coerce")
        df[col] = parsed.dt.date.where(parsed.notna(), None)
    if "include" not in df.columns:
        df["include"] = True
    else:
        df["include"] = df["include"].fillna(True).astype(bool)
    if "event_name" not in df.columns:
        df["event_name"] = ""
    else:
        df["event_name"] = df["event_name"].fillna("").astype(str)
    if "hours_per_day" not in df.columns:
        df["hours_per_day"] = 8.0
    else:
        df["hours_per_day"] = pd.to_numeric(df["hours_per_day"], errors="coerce").fillna(8.0)
    return df


def _load_user_data() -> tuple[date, date, float, int, bool, list[str], pd.DataFrame]:
    if not DATA_PATH.exists():
        return date(2020, 1, 1), date.today(), 80.0, 36, False, [], _default_plans_df()
    try:
        payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        hire_date = pd.to_datetime(payload.get("hire_date"), errors="coerce")
        last_paycheck = pd.to_datetime(payload.get("last_paycheck"), errors="coerce")
        balance = float(payload.get("balance_input", 80.0))
        periods = int(payload.get("periods_ahead", 36))
        floating_used_this_year = bool(payload.get("floating_used_this_year", False))
        hidden_forecast_columns_raw = payload.get("hidden_forecast_columns", [])
        hidden_forecast_columns = [c for c in hidden_forecast_columns_raw if c in FORECAST_TABLE_COLUMNS]
        plans = payload.get("plans", [])
        plans_df = _normalize_plans_df(pd.DataFrame(plans) if plans else _default_plans_df())
        hd = hire_date.date() if not pd.isna(hire_date) else date(2020, 1, 1)
        lp = last_paycheck.date() if not pd.isna(last_paycheck) else date.today()
        return hd, lp, balance, periods, floating_used_this_year, hidden_forecast_columns, plans_df
    except Exception:
        return date(2020, 1, 1), date.today(), 80.0, 36, False, [], _normalize_plans_df(_default_plans_df())


def _save_user_data(
    hire_date: date,
    last_paycheck: date,
    balance_input: float,
    periods_ahead: int,
    floating_used_this_year: bool,
    hidden_forecast_columns: list[str],
    plans_df: pd.DataFrame,
) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    serializable_plans = plans_df.copy()
    for col in ("start_date", "end_date"):
        if col in serializable_plans.columns:
            parsed = pd.to_datetime(serializable_plans[col], errors="coerce")
            serializable_plans[col] = parsed.dt.strftime("%Y-%m-%d").where(parsed.notna(), None)
    payload = {
        "hire_date": hire_date.isoformat(),
        "last_paycheck": last_paycheck.isoformat(),
        "balance_input": balance_input,
        "periods_ahead": periods_ahead,
        "floating_used_this_year": floating_used_this_year,
        "hidden_forecast_columns": [c for c in hidden_forecast_columns if c in FORECAST_TABLE_COLUMNS],
        "plans": serializable_plans.to_dict(orient="records"),
    }
    DATA_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


st.set_page_config(page_title="Vacation Hr Forecast", layout="wide", initial_sidebar_state="collapsed")
st.title("Vacation Hours Forecaster")
st.caption("Forecast vacation hours with planned or hypothetical upcoming usage.")

default_hire_date, default_last_paycheck, default_balance, default_periods, default_floating_used_this_year, default_hidden_forecast_columns, default_plans_df = _load_user_data()

with st.sidebar:
    st.header("Starting Inputs")
    hire_date = st.date_input("Hire/start date", value=default_hire_date, format="YYYY-MM-DD")
    last_paycheck = st.date_input("Date of last paycheck", value=default_last_paycheck, format="YYYY-MM-DD")
    period_accrual_rate = float(accrual_per_pay_period(service_year_on_day(hire_date, date.today())))
    balance_input = st.number_input("Vacation hours on last paycheck", min_value=0.0, value=default_balance, step=period_accrual_rate, format="%.3f")
    floating_used_this_year = st.toggle("Floating holiday already used this year", value=default_floating_used_this_year)
    periods_ahead = st.slider("Forecast pay periods", min_value=6, max_value=72, value=max(6, min(72, default_periods)))

st.subheader("Planned Time Off")
st.caption("Chargeable days automatically exclude weekends and observed holidays. Floating Holiday automatically applied to first full 8-hour day of vacation.")
plans_df = st.data_editor(
    default_plans_df,
    num_rows="dynamic",
    hide_index=True,
    column_config={
        "include": st.column_config.CheckboxColumn("Include", default=True),
        "event_name": st.column_config.TextColumn("Vacation/PTO Event Name"),
        "start_date": st.column_config.DateColumn("Start Date", format="YYYY-MM-DD"),
        "end_date": st.column_config.DateColumn("End Date", format="YYYY-MM-DD"),
        "hours_per_day": st.column_config.NumberColumn("Hours/Day", min_value=0.5, step=0.5, default=8.0, format="%.2f"),
    },
    use_container_width=True,
)

with st.sidebar:
    if st.button("Save Data", use_container_width=True):
        _save_user_data(
            hire_date,
            last_paycheck,
            float(balance_input),
            int(periods_ahead),
            bool(floating_used_this_year),
            default_hidden_forecast_columns,
            plans_df,
        )
        st.success("Saved.")
    if st.button("Reset Saved Data", use_container_width=True):
        if DATA_PATH.exists():
            DATA_PATH.unlink()
        st.success("Saved data reset. Refresh to load defaults.")

planned: list[PlannedUse] = []
for row in plans_df.to_dict(orient="records"):
    include = row.get("include")
    if include is False:
        continue
    sd_raw = row.get("start_date")
    ed_raw = row.get("end_date")
    event_name = str(row.get("event_name") or "")
    hpd = row.get("hours_per_day")
    if sd_raw is None or hpd is None:
        continue

    sd_ts = pd.to_datetime(sd_raw, errors="coerce")
    if pd.isna(sd_ts):
        continue

    sd = sd_ts.date()
    if ed_raw is None or str(ed_raw).strip() == "":
        ed = sd
    else:
        ed_ts = pd.to_datetime(ed_raw, errors="coerce")
        ed = sd if pd.isna(ed_ts) else ed_ts.date()
    if ed < sd or hpd <= 0:
        continue
    planned.append(PlannedUse(start_date=sd, end_date=ed, event_name=event_name, hours_per_day=Decimal(str(hpd))))

forecast = build_forecast(
    hire_date,
    last_paycheck,
    Decimal(str(balance_input)),
    planned,
    periods_ahead,
    floating_used_this_year=bool(floating_used_this_year),
)
if not forecast:
    st.info("No forecast rows generated.")
    st.stop()

result_df = pd.DataFrame([
    {
        "Period Start": r.period_start,
        "Period End": r.period_end,
        "Paycheck Date": r.paycheck_date,
        "Service Year": r.service_year,
        "Annual Accrual": r.annual_hours,
        "Accrual This Period": float(r.accrual_hours),
        "Capped Out This Period": float(r.accrued_capped_out_hours),
        "Vacation Used": float(r.vacation_use_hours),
        "Floating Used": float(r.floating_use_hours),
        "Vacation Balance": float(r.vacation_balance_after),
        "Floating Balance": float(r.floating_balance_after),
    }
    for r in forecast
])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Current Vacation Balance", f"{balance_input:.3f} hrs")
c2.metric("Balance at end of Forecast", f"{result_df.iloc[-1]['Vacation Balance']:.3f} hrs")
c3.metric("Total Planned Vacation Use", f"{result_df['Vacation Used'].sum():.3f} hrs")
c4.metric("Total Capped Out", f"{result_df['Capped Out This Period'].sum():.3f} hrs")

st.subheader("Forecast by Pay Period")
result_df["Cap"] = result_df["Annual Accrual"] * 2
result_df["Two-Period Accrual"] = (result_df["Annual Accrual"] / 24.0) * 2.0
result_df["Is Red"] = result_df["Vacation Balance"] < 0
result_df["Is Purple"] = result_df["Vacation Balance"] >= result_df["Cap"]
result_df["Is Yellow"] = result_df["Vacation Balance"] >= (result_df["Cap"] - result_df["Two-Period Accrual"])
result_df["Is Orange"] = result_df["Vacation Balance"] < 24
result_df["Is Blue"] = result_df["Vacation Used"] > 0.0
result_df["Is Interest"] = (
    result_df["Is Blue"]
    | (result_df["Floating Used"] > 0.0)
    | result_df["Is Orange"]
    | result_df["Is Red"]
    | result_df["Is Yellow"]
    | result_df["Is Purple"]
)

show_interest_only = st.toggle("Show rows of interest only", value=False)
display_df = result_df[result_df["Is Interest"]].copy() if show_interest_only else result_df.copy()

def _row_style(row: pd.Series) -> list[str]:
    vac_defined = (float(row["Vacation Used"]) > 0.0) or (float(row["Floating Used"]) > 0.0)
    balance = float(row["Vacation Balance"])
    annual = float(row["Annual Accrual"])
    cap = annual * 2.0
    near_cap_threshold = cap - ((annual / 24.0) * 2.0)

    color = ""
    if balance < 0:
        color = "rgba(255, 59, 48, 0.24)"  # red
    elif balance >= cap:
        color = "rgba(175, 82, 222, 0.24)"  # purple
    elif balance >= near_cap_threshold:
        color = "rgba(255, 204, 0, 0.24)"  # yellow
    elif balance < 24:
        color = "rgba(255, 149, 0, 0.24)"  # orange
    elif vac_defined:
        color = "rgba(10, 132, 255, 0.24)"  # blue

    return [f"background-color: {color}"] * len(row) if color else [""] * len(row)

table_cols = FORECAST_TABLE_COLUMNS
styled_df = (
    display_df[table_cols]
    .style.apply(_row_style, axis=1)
    .format(
        {
            "Accrual This Period": "{:.3f}",
            "Capped Out This Period": "{:.3f}",
            "Vacation Used": "{:.3f}",
            "Floating Used": "{:.3f}",
            "Vacation Balance": "{:.3f}",
            "Floating Balance": "{:.3f}",
        }
    )
)
st.dataframe(styled_df, use_container_width=True, hide_index=True)

chart_df = result_df[["Paycheck Date", "Vacation Balance", "Floating Balance"]].copy().reset_index(drop=True)
segments: list[dict[str, object]] = []
for i in range(len(chart_df) - 1):
    p1 = chart_df.iloc[i]
    p2 = chart_df.iloc[i + 1]
    floating_available = float(p1["Floating Balance"]) > 0.0
    segments.append(
        {
            "x": p1["Paycheck Date"],
            "x2": p2["Paycheck Date"],
            "y": float(p1["Vacation Balance"]),
            "y2": float(p2["Vacation Balance"]),
            "state": "Floating Holiday available" if floating_available else "Floating Holiday expended",
        }
    )

seg_df = pd.DataFrame(segments)
line_chart = (
    alt.Chart(seg_df)
    .mark_rule(strokeWidth=3)
    .encode(
        x=alt.X("x:T", title="Paycheck Date"),
        x2="x2:T",
        y=alt.Y("y:Q", title="Vacation Hours"),
        y2="y2:Q",
        color=alt.Color(
            "state:N",
            scale=alt.Scale(
                domain=["Floating Holiday expended", "Floating Holiday available"],
                range=["#1f77b4", "#2ca02c"],
            ),
            legend=alt.Legend(title=None, orient="bottom"),
        ),
    )
    .properties(height=320)
)
st.altair_chart(line_chart, use_container_width=True)
