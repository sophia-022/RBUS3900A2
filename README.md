# Trading Simulation Study

A browser-based five-minute trading simulation for a two-condition experiment:

- Gamified trading platform
- Non-gamified trading platform

Every participant receives the same starting credits and is randomly assigned
to one condition. The underlying market path is generated independently of
condition so the visual treatment does not change the simulated prices.

## What it records

Participant level:
- participant ID
- participant name
- age
- investment experience
- self-rated financial knowledge
- experimental condition
- market seed
- start/end timestamps

Trade level:
- timestamp
- elapsed time
- buy/sell
- asset
- quantity
- execution price
- trade value
- cash after trade
- portfolio value after trade
- total value after trade
- risk score

Every five seconds:
- cash
- portfolio value
- total value
- percentage invested
- percentage of portfolio in high-risk assets
- cumulative turnover

## Main outcome variables

Useful participant-level outcomes include:

1. Trading activity: number of trades
2. Risk-taking: average/high-risk exposure
3. Turnover: total amount traded
4. Investment intensity: average percentage of wealth invested
5. Portfolio concentration
6. Profit/loss
7. Trade timing: time to first trade and average trade time
8. Buy/sell behaviour
9. Interaction of gamification with financial knowledge

## Run locally

Create a virtual environment and install:

    pip install -r requirements.txt

Then:

    streamlit run app.py

The app opens in a browser.

## External deployment

For a pilot, Streamlit Community Cloud can run the app from a GitHub repository.
However, SQLite is not appropriate as the long-term production database on
many cloud deployments because the filesystem may be ephemeral.

For actual external participant recruitment, replace the SQLite functions in
app.py with a hosted database such as PostgreSQL/Supabase. The participant-facing
interface does not need to change.

Also set an environment variable for the database connection and do not commit
database credentials to GitHub.

## Important research design point

Keep the market path, asset universe, starting credits, trading rules, timer,
and available information identical between conditions. Only the intended
interface manipulation should differ.

The gamified condition currently changes:
- visual styling
- positive reinforcement after trades
- celebratory animation

The non-gamified condition retains the same trading mechanics without those
reinforcement/celebration elements.

## Power analysis / G*Power

G*Power is not needed to run the simulation. It is most useful before data
collection to determine the required sample size.

For a simple two-condition primary outcome:
- independent-samples t-test and one-way ANOVA are mathematically equivalent
  when there are exactly two groups
- choose the effect size from prior literature or a justified pilot estimate
- use alpha = .05 and desired power such as .80 or .90
- plan for attrition/exclusions

Use power.py for a Python equivalent of common two-group calculations.

## Suggested statistical plan

Primary:
- Independent-samples t-test / one-way ANOVA: gamified vs non-gamified on the
  primary continuous outcome.

Regression:
- OLS regression with condition as the main predictor and financial knowledge,
  investment experience and age as covariates.
- Add condition × financial knowledge if testing moderation.

If perceived investing competence and platform loyalty are collected in a
post-simulation questionnaire, mediation/moderation analyses can be added.
The current app focuses on behavioural trading data and the initial
questionnaire specified by the study brief.

## Privacy

The current app records the participant name because the study brief requested it.
For a real external deployment, consider using a participant code instead of a
name unless the research protocol genuinely requires names. Obtain the required
ethics/consent approval and provide participants with the appropriate privacy
notice before collecting data.
