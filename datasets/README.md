# Synthetic inventory

The active inventory is produced by `backend/scripts/generate_inventory.py` and loaded by `backend/scripts/seed_inventory.py`. Generation uses a seeded local random generator, `config/cities.yaml`, `config/airports.yaml`, and `config/inventory.yaml`. It makes no network or model calls.

Every flight and hotel row has `source = "synthetic-v1"` and `currency = "USD"`. Airline names, hotel names, districts, schedules, durations, prices, ratings and cost indices are synthetic demonstration values, not real offers or availability. Airport names, codes and coordinates are reference geography from the installed `airportsdata` package, not generated facts.

`make seed` generates and loads this inventory in a transaction. The backend container must be rebuilt after code/configuration changes, and migrations must run before seeding. The default configuration generates departures every three days over 120 days starting 2027-03-01, with ten synthetic hotels per configured city.

## Synthetic formulas

Let `d` be airport great-circle distance in kilometres, `s` the configured season multiplier, and `u` seeded uniform noise in [-0.04, 0.04]. Flight price in USD is rounded to cents:

`(80 + 0.065 * d) * s * (1 + u) + (45 if nonstop else 0)`

Duration in minutes is `round(d / 850 * 60 + 45)`, plus 120 minutes for a synthetic connecting flight. Nonstop flags are seeded draws with probability 0.65. These are fictional schedules; no actual airline service is implied.

Hotel nightly price is `city_cost_index * tier_base_usd * season_multiplier`, rounded to cents. Tiers use synthetic bases of 55, 110 and 210 USD. Each hotel is a single seasonal quote for the generation start date (spring with the default configuration), not a date-by-date availability calendar. Ratings are seeded values between 3.0 and 4.9. Synthetic district numbers do not identify real neighbourhoods.

Natural keys are `(source, flight_date, starting_airport, destination_airport, airline)` for flights and `(source, name, city, country)` for hotels. Prices are excluded so reseeding updates them. Repeating the same configuration preserves counts and IDs. Changing the configured city set, horizon or hotel names can add new keys; seeding does not delete historical rows. Migration leaves existing inventory metadata NULL rather than mislabeling old records as synthetic.

## Legacy files are not loaded

The former files now live under `legacy/datasets/`: `housing_ds.csv`, `sql-dump.csv`, `gretel/`, and `itineraries-min-*.csv`. They are retained in git for historical reference. Neither the generator nor the default seed reads them. Their provenance is not established here; none is described as synthetic.

Related MariaDB/MindsDB notebooks are archived under `legacy/notebooks/`. Other notebooks remain under `notebooks/`.

## PROVENANCE UNVERIFIED

The columns in `legacy/datasets/itineraries-min-50k.csv`, `itineraries-min-100k.csv`, and `itineraries-min-250k.csv` resemble a public flight-price dataset. This resemblance is not evidence of a particular source or license. The owner must confirm the original source, license, and permission to redistribute these files before further use. No source attribution or license is asserted for them here.
