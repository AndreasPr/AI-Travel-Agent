# Synthetic inventory data

This repository includes synthetic travel inventory used for local experimentation and demo flows. The flight and hotel records are not production pricing feeds and should be treated as demo data only.

## Flight data

The flight inventory is derived from synthetic flight records generated with Gretel and stored under `datasets/gretel/` and the sample CSV exports in the root `datasets/` folder.

Relevant files:
- `datasets/gretel/tabular-actgan-67db43cc641d963488489eda-data_preview.csv`
- `datasets/gretel/tabular-actgan-67db47547c54e7516f73d9be-data.csv`
- `datasets/sql-dump.csv`
- `datasets/itineraries-min-50k.csv`
- `datasets/itineraries-min-100k.csv`
- `datasets/itineraries-min-250k.csv`

Common columns:
- `flightDate`
- `startingAirport`
- `destinationAirport`
- `isBasicEconomy`
- `isRefundable`
- `isNonStop`
- `segmentsAirlineName`
- `totalFare`

The larger itinerary files add fields such as `legId`, `searchDate`, `fareBasisCode`, `travelDuration`, `seatsRemaining`, and route metadata.

## Hotel / lodging data

The repository does not contain a dedicated real hotel dataset. The available housing sample under `datasets/housing_ds.csv` is a local synthetic dataset used as a placeholder inventory source for demo hotel-like pricing and location metadata.

Relevant file:
- `datasets/housing_ds.csv`

Columns:
- `saledate`
- `MA`
- `type`
- `bedrooms`

## Notebook references

The generation and loading work is associated with the project notebooks under `notebooks/`, especially:
- `notebooks/Generate and Load Airports in MariaDB.ipynb`
- `notebooks/Load Flight Price Data to MariaDB via Pandas.ipynb`
- `notebooks/Load House Data to MariaDB via Pandas.ipynb`
- `notebooks/Train Flight Predictor via MindsDB API Calls.ipynb`

Those notebooks document the loading and synthetic-data workflow used in the project.
