# Vacation Hours Forecaster

A Streamlit app for forecasting vacation balance over future pay periods using your hire date, current balance, accrual policy, and planned time off.

This tool is designed for practical planning: "If I take these days off, what will my balance look like over time?"

## What It Does

- Forecasts vacation balance by pay period
- Applies accrual rates based on service year
- Enforces accrual cap logic
- Calculates chargeable vacation usage from planned date ranges
- Excludes weekends and observed holidays from chargeable usage
- Applies floating holiday rules automatically
- Highlights important forecast rows (low balance, near cap, capped, usage events)
- Displays an interactive chart of projected balance across paychecks
- Supports local save/load of user inputs

## App Screens / Core Flow

1. Enter starting inputs in the sidebar:
- Hire/start date
- Date of last paycheck
- Vacation balance on last paycheck
- Whether floating holiday is already used this year
- Number of forecast pay periods

2. Enter planned time off in the table:
- Include toggle
- Event name
- Start/end dates
- Hours/day

3. Review outputs:
- Summary metrics
- Forecast table (with visual row highlighting)
- Interactive line chart

## Project Structure

```text
Vacation/
  data/
    user_data.json            # local personal data (ignored by git)
  src/
    vacation/
      app.py                  # Streamlit app entrypoint
      forecast.py             # forecasting rules and calculations
      __init__.py
  pyproject.toml
  uv.lock
  .gitignore
  README.md
```

## Tech Stack

- Python 3.13+
- Streamlit
- pandas
- Altair
- uv (project/dependency management)

## Local Development

### 1) Create environment and install deps

```powershell
uv sync
```

### 2) Run the app

```powershell
uv run streamlit run src/vacation/app.py
```

### 3) Open in browser

Streamlit will print a local URL (usually `http://localhost:8501`).

## Data and Privacy

This project intentionally keeps personal data local.

- Your saved inputs live in `data/user_data.json`
- `data/` is git-ignored
- `user_data.json` should never be committed or pushed

Quick safety check before committing:

```powershell
git ls-files | Select-String "user_data.json"
```

Expected result: no output.

## Git Workflow (Recommended)

```powershell
git status
git add src/vacation/app.py src/vacation/forecast.py README.md
git diff --cached
git commit -m "Describe your change"
git push origin main
```

## Deploy to Streamlit Community Cloud

1. Push repository to GitHub
2. In Streamlit Community Cloud, create a new app from your repo
3. Set:
- Branch: `main`
- Main file path: `src/vacation/app.py`
4. Deploy

If updates do not appear immediately, use **Reboot app** in Streamlit.

## Forecast Rules (High Level)

- Accrual is computed per pay period using service-year tier
- Vacation balance is capped at `2 x annual accrual`
- Planned usage is charged only on valid chargeable days
- Floating holiday is granted/consumed according to eligibility and yearly usage logic
