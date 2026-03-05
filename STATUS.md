# Melbourne Indian Food Intelligence — Project Status

## What This Project Does

An interactive map dashboard showing Indian restaurant distribution across Greater Melbourne, overlaid with Indian-born population demographics from the ABS Census. It identifies "opportunity zones" — suburbs with high Indian populations but few Indian restaurants.

**Two files power it:**
- `melbourne-indian-food-intel.html` — single-file dashboard (MapLibre GL JS, dark theme, choropleth + dot map)
- `prepare_data.py` — data pipeline that fetches real data from government APIs and outputs `data/dashboard_data.js`

## Current State (March 2026)

### What Works

**Data pipeline (`prepare_data.py`):**
- **ABS SA2 boundaries**: Fetches 361 Greater Melbourne SA2 polygons from the ArcGIS REST API at `geo.abs.gov.au`, with shapefile fallback. Geometries simplified for web.
- **ABS Census 2021**: Downloads the Victoria SA2 DataPack ZIP (~13 MB). Extracts:
  - `P_India_Tot` from G09G — total India-born persons per SA2
  - `Tot_P_P` from G01 — total population (both sexes)
  - `Median_tot_hhd_inc_weekly` from G02 — median household income (converted to annual)
- **CLUE restaurants**: Pulls from Melbourne Open Data's OpenDataSoft API (`cafes-and-restaurants-with-seating-capacity`). Filters by Indian-related trading name keywords. Currently yields ~35 restaurants.
- **Google Places** (optional): Works if `GOOGLE_PLACES_API_KEY` is set. Searches 30 suburbs.
- **Foursquare**: Code exists but doesn't work (see issues below).
- **Output**: Generates `data/dashboard_data.js` with `window.sa2GeoJSON`, `window.restaurantGeoJSON`, `window.labelGeoJSON`, `window.suburbs`, `window.restaurants`.

**Dashboard (`melbourne-indian-food-intel.html`):**
- Loads `data/dashboard_data.js` and auto-detects real vs synthetic data
- Choropleth layer: SA2 polygons colored by Indian-born population %
- Restaurant dots: colored by cuisine type (South Indian, North Indian, Sri Lankan, Nepalese, Bangladeshi, General)
- Side panel: opportunity zones, suburb detail on click (demographics, cuisine breakdown, restaurant table)
- Filter panel: cuisine type checkboxes, rating/review sliders
- Tooltips on hover for both suburbs and restaurants

### Data Quality

| Source | Records | Coverage | Notes |
|--------|---------|----------|-------|
| SA2 boundaries | 361 areas | All Greater Melbourne | Real ABS 2021 ASGS polygons |
| Census demographics | 361 areas | All Greater Melbourne | Real 2021 Census data |
| Indian-born % | Top: Tarneit North 40% | Accurate | Uses P_India_Tot / Tot_P_P |
| Median income | $54k–$364k/year | 358 of 361 suburbs | Weekly * 52 conversion |
| CLUE restaurants | 35 | CBD + inner suburbs only | City of Melbourne jurisdiction only |
| Foursquare | 0 | None | HuggingFace API returns 401 |
| Google Places | 0 | None | Needs API key |

### Key Limitation

Restaurant data only covers the City of Melbourne council area (CBD, Carlton, Docklands, North Melbourne, Southbank, East Melbourne). **Outer suburbs like Tarneit, Truganina, Dandenong — where the Indian population is highest — have zero restaurant data.** This is the single biggest gap.

## Bugs Fixed During Setup

1. **Census G09 column**: Was using `M_India_0_4` (males aged 0-4) from G09A. Fixed to use `P_India_Tot` (total persons) from G09G.
2. **Total population column**: Was picking `Tot_P_M` (males only). Fixed to use `Tot_P_P` (all persons).
3. **Income column matching**: Search pattern `"income"` didn't match ABS column `Median_tot_hhd_inc_weekly` (uses `inc` not `income`). Added `"hhd"` to match.
4. **Income not annual**: ABS reports weekly. Added `* 52` conversion.
5. **Pandas iterrows float promotion**: `str(row['SA2_CODE_2021'])` produces `"201011001.0"` for G02/G01 but `"201011001"` for G09G (due to NaN in other columns promoting int to float). Fixed with `str(int(val))`.
6. **CLUE API endpoint**: Melbourne migrated from Socrata to OpenDataSoft. Old `/resource/xt2y-qn3c.json` returns 404. Updated to `/api/explore/v2.1/catalog/datasets/cafes-and-restaurants-with-seating-capacity/records`.
7. **CLUE year filter**: `census_year` is a date type in ODS, not a string. Changed filter to `census_year>=date'2023-01-01'` syntax.
8. **JS variable scope**: `const sa2GeoJSON` in an external script doesn't attach to `window`. Changed to `window.sa2GeoJSON = ...`.
9. **SA2 property aliases**: Real data used `sa2_name`, `restaurant_count`, `median_income` but HTML expected `name`, `restaurants`, `income`, `gap_class`, `lng`, `lat`. Added alias properties in the JS output.

## Improvements to Make

### High Priority — More Restaurant Data

1. **Google Places API**: Set `GOOGLE_PLACES_API_KEY` env var and re-run. This is the easiest way to get outer-suburb coverage. The code already searches 30 key suburbs and captures ratings + review counts.

2. **Foursquare Open Source Places**: The HuggingFace API returns 401 (needs authentication). Fix options:
   - Install `pip install datasets` and set a HuggingFace token (`huggingface-cli login`)
   - Or download the dataset manually from https://huggingface.co/datasets/foursquare/fsq-os-places
   - The streaming code in `fetch_foursquare_restaurants()` works — it just needs auth

3. **Overpass API (OpenStreetMap)**: Not currently implemented. Could query for `cuisine=indian` within Melbourne bbox. Free, no API key needed. Would add significant coverage.

4. **Yelp Fusion API**: Not implemented. Would provide ratings and reviews for outer suburbs.

### Medium Priority — Data Enrichment

5. **Census 2026**: When ABS releases 2026 Census data, update the DataPack URL and field names. The pipeline should mostly work with minor column name adjustments.

6. **CLUE data is CBD-only**: The City of Melbourne CLUE dataset only covers the municipality of Melbourne (CBD + immediate surrounds). For outer councils (Wyndham, Casey, Hume, Monash, etc.), each council may have their own open data portals. Consider querying:
   - Wyndham: covers Tarneit, Truganina, Werribee, Point Cook
   - Casey: covers Cranbourne, Berwick, Narre Warren
   - Hume: covers Craigieburn, Roxburgh Park
   - Greater Dandenong: covers Dandenong, Springvale
   - Monash: covers Clayton, Glen Waverley

7. **Rating/review data for CLUE restaurants**: CLUE data has no ratings. Could cross-reference with Google Places API by name + address to enrich existing records.

### Low Priority — Dashboard Enhancements

8. **Gap score tuning**: Current formula weights Indian population % (40%), income (20%), and supply gap (40%). May need tuning with real restaurant data — currently most suburbs show as "Underserved" because restaurant count is 0.

9. **Time series**: CLUE data goes back to 2002. Could show restaurant growth over time.

10. **Mobile responsiveness**: Basic responsive CSS exists but the side panel takes full width on mobile — could be improved.

11. **Search**: No suburb search functionality. Could add a search bar to quickly find and fly to a suburb.

12. **Export**: No way to export the opportunity analysis. Could add CSV/PDF export of top opportunity zones.

## File Structure

```
food/
├── melbourne-indian-food-intel.html   # Dashboard (single HTML file)
├── prepare_data.py                     # Data pipeline
├── STATUS.md                           # This file
└── data/                               # Generated output (gitignored)
    ├── dashboard_data.js               # JS file loaded by the HTML (~736 KB)
    ├── melbourne_sa2.geojson           # SA2 boundaries + demographics
    ├── melbourne_indian_restaurants.json # Merged restaurant list
    ├── census_sa2_vic.zip              # Cached ABS Census DataPack
    └── sa2_boundaries.zip              # Cached shapefile (if API fallback used)
```

## How to Re-run the Pipeline

```bash
# Install dependencies
pip install pandas geopandas requests pyarrow shapely

# Optional: for Foursquare data
pip install datasets
huggingface-cli login

# Optional: for Google Places data
export GOOGLE_PLACES_API_KEY=your_key_here

# Run
python prepare_data.py

# Open dashboard
open melbourne-indian-food-intel.html
```

## Dependencies

- Python 3.9+
- pandas, geopandas, requests, pyarrow, shapely
- Optional: `datasets` (HuggingFace), Google Places API key
