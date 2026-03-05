#!/usr/bin/env python3
"""
Melbourne Indian Food Intelligence — Data Pipeline
====================================================
Run this script on your local machine (not in a sandbox) to fetch real data
from all four sources and generate the JSON/GeoJSON files the dashboard needs.

Prerequisites:
    pip install pandas geopandas requests pyarrow shapely

Optional (for Google Places):
    Set GOOGLE_PLACES_API_KEY environment variable

Usage:
    python prepare_data.py

Output files (saved to ./data/):
    - melbourne_sa2.geojson         SA2 polygons + Indian population + income
    - melbourne_indian_restaurants.json  Merged restaurant data
    - dashboard_data.js             Single JS file you can paste into the HTML
"""

import json
import math
import os
import sys
import time
import warnings
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import geopandas as gpd
import requests
from shapely.geometry import shape

warnings.filterwarnings("ignore")

OUTPUT_DIR = Path("./data")
OUTPUT_DIR.mkdir(exist_ok=True)

# Melbourne bounding box (generous)
MELB_BBOX = {
    "west": 144.3,
    "south": -38.5,
    "east": 146.0,
    "north": -37.3,
}


# ═══════════════════════════════════════════════════════════════════
# STEP 1: ABS SA2 Boundaries + Census Data
# ═══════════════════════════════════════════════════════════════════

def fetch_sa2_boundaries():
    """
    Download SA2 boundaries from ABS ArcGIS REST service.
    Falls back to shapefile download if the API doesn't work.
    """
    print("\n[1/5] Fetching ABS SA2 boundaries for Greater Melbourne...")

    # Approach 1: ABS ArcGIS REST API (GeoJSON query)
    base_url = "https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/SA2/MapServer/0/query"

    # First, discover field names
    schema_url = "https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/SA2/MapServer/0?f=json"
    try:
        r = requests.get(schema_url, timeout=30)
        r.raise_for_status()
        schema = r.json()
        fields = [f["name"] for f in schema.get("fields", [])]
        print(f"  API available. Fields: {fields[:10]}...")
    except Exception as e:
        print(f"  Schema query failed: {e}")
        fields = []

    # Determine the right field names
    gccsa_field = None
    sa2_code_field = None
    sa2_name_field = None
    for f in fields:
        fl = f.lower()
        if "gccsa" in fl and "name" in fl:
            gccsa_field = f
        if "gccsa" in fl and "code" in fl and not gccsa_field:
            pass
        if "sa2" in fl and "code" in fl:
            sa2_code_field = f
        if "sa2" in fl and "name" in fl:
            sa2_name_field = f

    # Default field names if schema query failed
    if not gccsa_field:
        gccsa_field = "GCC_NAME21"
    if not sa2_code_field:
        sa2_code_field = "SA2_CODE21"
    if not sa2_name_field:
        sa2_name_field = "SA2_NAME21"

    # Try API query with pagination
    all_features = []
    offset = 0
    batch_size = 500

    for attempt_where in [
        f"{gccsa_field}='Greater Melbourne'",
        "GCC_NAME21='Greater Melbourne'",
        "GCCSA_NAME_2021='Greater Melbourne'",
        "STE_NAME21='Victoria'",
        "STATE_NAME_2021='Victoria'",
    ]:
        offset = 0
        all_features = []
        try:
            while True:
                params = {
                    "where": attempt_where,
                    "outFields": "*",
                    "f": "geojson",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "resultOffset": offset,
                    "resultRecordCount": batch_size,
                }
                r = requests.get(base_url, params=params, timeout=60)
                r.raise_for_status()
                data = r.json()

                features = data.get("features", [])
                if not features:
                    break

                all_features.extend(features)
                print(f"    Fetched {len(all_features)} features (offset={offset})...")
                offset += batch_size

                # Check if we have all records
                if len(features) < batch_size:
                    break

            if all_features:
                print(f"  Success with where='{attempt_where}': {len(all_features)} SA2 areas")
                break
        except Exception as e:
            print(f"  Query with '{attempt_where}' failed: {e}")
            continue

    if all_features:
        geojson = {"type": "FeatureCollection", "features": all_features}
        gdf = gpd.GeoDataFrame.from_features(geojson, crs="EPSG:4326")

        # Filter to Melbourne bbox if we got Victoria-wide data
        gdf = gdf.cx[MELB_BBOX["west"]:MELB_BBOX["east"],
                      MELB_BBOX["south"]:MELB_BBOX["north"]]

        print(f"  After bbox filter: {len(gdf)} SA2 areas")
    else:
        # Approach 2: Download the official shapefile
        print("  API queries failed. Downloading official shapefile...")
        shp_url = "https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/digital-boundary-files/SA2_2021_AUST_GDA2020.zip"
        try:
            r = requests.get(shp_url, timeout=120, stream=True)
            r.raise_for_status()
            zip_path = OUTPUT_DIR / "sa2_boundaries.zip"
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"  Downloaded {zip_path.stat().st_size / 1e6:.1f} MB")

            gdf = gpd.read_file(f"zip://{zip_path}")
            # Filter to Greater Melbourne
            gccsa_col = [c for c in gdf.columns if "gccsa" in c.lower() and "name" in c.lower()]
            gcc_col = [c for c in gdf.columns if "gcc" in c.lower() and "name" in c.lower()]
            filter_col = gccsa_col[0] if gccsa_col else gcc_col[0] if gcc_col else None

            if filter_col:
                gdf = gdf[gdf[filter_col].str.contains("Melbourne", case=False, na=False)]
            else:
                # Bbox filter fallback
                gdf = gdf.cx[MELB_BBOX["west"]:MELB_BBOX["east"],
                              MELB_BBOX["south"]:MELB_BBOX["north"]]

            print(f"  Filtered to {len(gdf)} Greater Melbourne SA2 areas")
        except Exception as e:
            print(f"  ERROR: Could not download shapefile: {e}")
            print("  Please download SA2_2021_AUST_GDA2020.zip manually from:")
            print("  https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/digital-boundary-files")
            sys.exit(1)

    # Simplify geometry for web display (~100m tolerance)
    gdf["geometry"] = gdf["geometry"].simplify(0.001, preserve_topology=True)

    # Standardise column names
    col_map = {}
    for c in gdf.columns:
        cl = c.lower()
        if "sa2" in cl and "code" in cl:
            col_map[c] = "sa2_code"
        elif "sa2" in cl and "name" in cl:
            col_map[c] = "sa2_name"
        elif "areasqkm" in cl or "area_sqkm" in cl:
            col_map[c] = "area_sqkm"
    gdf = gdf.rename(columns=col_map)

    # Keep only needed columns
    keep = [c for c in ["sa2_code", "sa2_name", "area_sqkm", "geometry"] if c in gdf.columns]
    gdf = gdf[keep]

    print(f"  SA2 boundaries: {len(gdf)} areas, columns: {list(gdf.columns)}")
    return gdf


# ═══════════════════════════════════════════════════════════════════
# STEP 2: ABS Census — Indian-Born Population by SA2
# ═══════════════════════════════════════════════════════════════════

def fetch_census_data(sa2_gdf):
    """
    Fetch Indian-born population and income data from ABS.
    Uses the ABS Data API (stat.data.abs.gov.au) or Data by Region.
    """
    print("\n[2/5] Fetching ABS Census 2021 data (Indian-born population)...")

    # ABS Data API — Country of Birth by SA2
    # Dataset: ABS_C21_T09_SA2 (Census 2021, Country of Birth, SA2)
    # India country code in ABS: 7103

    census_data = {}

    # Try ABS .Stat Data API
    api_url = "https://api.data.abs.gov.au/data/ABS,C21_G09_SA2,1.0.0"
    try:
        # This endpoint returns country of birth data by SA2
        # Filter for India (BPLP=7103) and total (all sexes)
        params = {
            "dimensionAtObservation": "AllDimensions",
            "detail": "dataonly",
        }
        print("  Trying ABS .Stat Data API...")
        r = requests.get(api_url, params=params, timeout=60, headers={"Accept": "application/json"})
        if r.status_code == 200:
            data = r.json()
            print("  Got Census data from ABS API")
            # Parse SDMX-JSON format... (complex, try simpler approach first)
    except Exception as e:
        print(f"  ABS .Stat API failed: {e}")

    # Try ABS Data by Region API
    dbr_url = "https://dbr.abs.gov.au/region.html"
    try:
        print("  Trying ABS Data by Region...")
        # This is actually a web app, not a REST API. Try the underlying API.
        # The TableBuilder data can be accessed via DataPacks
        pass
    except Exception:
        pass

    # Try the ABS Census DataPacks (CSV download)
    # General Community Profile (GCP) Table G09 — Country of Birth by SA2
    datapack_url = "https://www.abs.gov.au/census/find-census-data/datapacks/download/2021_GCP_SA2_for_VIC_short-header.zip"
    try:
        print("  Trying Census DataPack download (VIC, SA2)...")
        r = requests.get(datapack_url, timeout=120, stream=True)
        r.raise_for_status()
        zip_path = OUTPUT_DIR / "census_sa2_vic.zip"
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  Downloaded {zip_path.stat().st_size / 1e6:.1f} MB")

        import zipfile
        with zipfile.ZipFile(zip_path) as zf:
            # Look for G09 (Country of Birth) table
            csv_files = [n for n in zf.namelist() if n.endswith(".csv")]
            g09_files = [n for n in csv_files if "G09" in n.upper() or "g09" in n.lower()]
            print(f"  Found CSV files: {len(csv_files)}, G09 files: {g09_files[:5]}")

            if g09_files:
                # Prefer G09G which has P_India_Tot (total persons India-born)
                g09_files_sorted = sorted(g09_files, key=lambda f: ('G09G' in f.upper(), 'P_India_Tot' in f), reverse=True)
                for g09_file in g09_files_sorted:
                    df = pd.read_csv(zf.open(g09_file))
                    # Look for total India-born column (P_India_Tot preferred)
                    india_cols = [c for c in df.columns if "india" in c.lower()]
                    india_tot_cols = [c for c in india_cols if "tot" in c.lower() and c.startswith("P_")]
                    sa2_cols = [c for c in df.columns if "sa2" in c.lower() and "code" in c.lower()]
                    print(f"    {g09_file}: india_tot={india_tot_cols}, sa2={sa2_cols[:2]}")

                    if india_tot_cols and sa2_cols:
                        sa2_col = sa2_cols[0]
                        india_col = india_tot_cols[0]  # P_India_Tot
                        for _, row in df.iterrows():
                            sa2 = str(int(row[sa2_col])) if pd.notna(row[sa2_col]) else ""
                            count = row[india_col]
                            if pd.notna(count):
                                census_data[sa2] = {"india_born": int(count)}
                        print(f"  Parsed {len(census_data)} SA2 records with India-born counts (using {india_col})")
                        break

            # Also look for G02 (income) or G33 (household income)
            income_files = [n for n in csv_files if "G02" in n.upper() or "g02" in n.lower()]
            if income_files:
                df_inc = pd.read_csv(zf.open(income_files[0]))
                income_cols = [c for c in df_inc.columns if "median" in c.lower() and ("hhd" in c.lower() or "hhold" in c.lower() or "income" in c.lower())]
                sa2_cols = [c for c in df_inc.columns if "sa2" in c.lower() or "code" in c.lower()]
                if income_cols and sa2_cols:
                    # Income is weekly in ABS Census — convert to annual
                    for _, row in df_inc.iterrows():
                        sa2 = str(int(row[sa2_cols[0]])) if pd.notna(row[sa2_cols[0]]) else ""
                        income = row[income_cols[0]]
                        if sa2 in census_data and pd.notna(income):
                            census_data[sa2]["median_income"] = int(income * 52)

            # Get total population from G01
            g01_files = [n for n in csv_files if "G01" in n.upper() or "g01" in n.lower()]
            if g01_files:
                df_pop = pd.read_csv(zf.open(g01_files[0]))
                # Use Tot_P_P (Total Persons - both sexes), not Tot_P_M (males only)
                pop_col = None
                for c in df_pop.columns:
                    if c == "Tot_P_P":
                        pop_col = c
                        break
                if not pop_col:
                    # Fallback: look for total persons column
                    pop_cols = [c for c in df_pop.columns if c.lower() == "tot_p_p" or
                                (c.lower().endswith("_p") and "tot_p" in c.lower())]
                    if pop_cols:
                        pop_col = pop_cols[0]
                sa2_cols = [c for c in df_pop.columns if "sa2" in c.lower() and "code" in c.lower()]
                if pop_col and sa2_cols:
                    print(f"  Using total population column: {pop_col}")
                    for _, row in df_pop.iterrows():
                        sa2 = str(int(row[sa2_cols[0]])) if pd.notna(row[sa2_cols[0]]) else ""
                        pop = row[pop_col]
                        if sa2 in census_data and pd.notna(pop):
                            census_data[sa2]["total_pop"] = int(pop)

    except Exception as e:
        print(f"  Census DataPack download failed: {e}")
        print("  You can manually download from: https://www.abs.gov.au/census/find-census-data/datapacks")

    # Merge census data into SA2 GeoDataFrame
    if census_data:
        sa2_gdf["india_born"] = sa2_gdf["sa2_code"].astype(str).map(
            lambda x: census_data.get(x, {}).get("india_born", 0)
        )
        sa2_gdf["total_pop"] = sa2_gdf["sa2_code"].astype(str).map(
            lambda x: census_data.get(x, {}).get("total_pop", 0)
        )
        sa2_gdf["median_income"] = sa2_gdf["sa2_code"].astype(str).map(
            lambda x: census_data.get(x, {}).get("median_income", 0)
        )
        sa2_gdf["india_pct"] = (
            sa2_gdf["india_born"] / sa2_gdf["total_pop"].replace(0, 1) * 100
        ).round(1)
        print(f"  Merged census data. Max india_pct: {sa2_gdf['india_pct'].max():.1f}%")
    else:
        print("  WARNING: No census data retrieved. SA2 will have empty demographic fields.")
        sa2_gdf["india_born"] = 0
        sa2_gdf["total_pop"] = 0
        sa2_gdf["median_income"] = 0
        sa2_gdf["india_pct"] = 0.0

    return sa2_gdf


# ═══════════════════════════════════════════════════════════════════
# STEP 3: Foursquare Open Source Places
# ═══════════════════════════════════════════════════════════════════

def fetch_foursquare_restaurants():
    """
    Download Indian restaurant data from Foursquare Open Source Places on HuggingFace.
    Downloads only the Australian Parquet partitions (files 98-99) and filters locally.
    """
    print("\n[3/5] Fetching Foursquare Open Source Places (Indian restaurants)...")

    restaurants = []
    hf_token = os.environ.get("HUGGINGFACE_TOKEN")
    if not hf_token:
        print("  HUGGINGFACE_TOKEN not set. Skipping Foursquare.")
        return []

    # Check for cached Foursquare data
    cache_path = OUTPUT_DIR / "foursquare_indian.json"
    if cache_path.exists():
        try:
            with open(cache_path) as f:
                restaurants = json.load(f)
            print(f"  Loaded {len(restaurants)} cached Foursquare restaurants from {cache_path}")
            return restaurants
        except Exception:
            pass

    try:
        import pyarrow.parquet as pq
        import io

        headers = {"Authorization": f"Bearer {hf_token}"}
        base = "https://huggingface.co/api/datasets/foursquare/fsq-os-places/parquet/places/train"

        # Australian data lives in Parquet files 98 and 99
        AU_FILES = [98, 99]

        INDIAN_KEYWORDS = [
            "indian", "curry", "dosa", "tandoori", "biryani", "masala",
            "sri lanka", "nepal", "bengal", "punjab", "kerala", "mughal",
            "naan", "tikka", "roti", "chai", "dhaba", "thali",
            "bombay", "mumbai", "delhi", "madras", "chennai", "hyderabad",
            "kolkata", "lucknow", "jaipur", "himalaya", "everest", "gurkha",
            "colombo", "jaffna", "ceylon", "momo", "samosa", "chutney",
        ]
        FOOD_SIGNALS = [
            "restaurant", "kitchen", "eatery", "cafe", "diner", "bistro",
            "bar & grill", "curry", "dosa", "tandoori", "biryani", "masala",
            "naan", "tikka", "roti", "thali", "dhaba", "kebab", "chutney",
            "samosa", "momo", "hopper", "hut", "palace", "house", "corner",
            "express", "garden", "village", "flame", "grill", "dining",
            "foods", "takeaway", "take away", "sweets",
        ]
        EXCLUDE_NAMES = [
            "cab", "taxi", "grocery", "superstore", "cooking class",
            "hospice", "foundation", "dental", "pharmacy", "real estate",
            "hair", "salon", "clothing", "jewel", "mobile", "travel",
            "insurance", "accounting", "plumb", "electric", "gym",
            "fitness", "laund", "clean", "repair", "mechanic", "auto",
            "tyres", "storage", "removals", "courier", "printing",
        ]
        EXCLUDE_CATS = {
            "4bf58dd8d48988d117951735",  # Candy Store
            "4bf58dd8d48988d130951735",  # Taxi
            "4bf58dd8d48988d118951735",  # Grocery Store
            "4d4b7105d754a06378d81259",  # Retail
            "4bf58dd8d48988d1f6941735",  # Department Store
            "63be6904847c3692a84b9bf0",  # Meat Store
        }

        all_indian = []
        for idx in AU_FILES:
            url = f"{base}/{idx}.parquet"
            print(f"  Downloading file {idx} (~120 MB)...")
            r = requests.get(url, headers=headers, timeout=180)
            r.raise_for_status()
            data = io.BytesIO(r.content)
            print(f"    Downloaded {len(r.content) / 1e6:.1f} MB")

            table = pq.read_table(
                data,
                columns=["name", "latitude", "longitude", "locality", "postcode",
                          "address", "fsq_category_ids", "fsq_category_labels"],
            )
            df = table.to_pandas()

            # Filter to Melbourne bbox
            melb = df[
                (df["latitude"] >= MELB_BBOX["south"]) & (df["latitude"] <= MELB_BBOX["north"]) &
                (df["longitude"] >= MELB_BBOX["west"]) & (df["longitude"] <= MELB_BBOX["east"])
            ].copy()
            print(f"    Melbourne places: {len(melb)}")

            def has_indian_name(name):
                if not isinstance(name, str):
                    return False
                nl = name.lower()
                return any(kw in nl for kw in INDIAN_KEYWORDS)

            indian = melb[melb["name"].apply(has_indian_name)].copy()
            print(f"    Indian keyword matches: {len(indian)}")
            all_indian.append(indian)

        combined = pd.concat(all_indian).drop_duplicates(subset=["name", "latitude", "longitude"])

        for _, row in combined.iterrows():
            name_lower = str(row["name"]).lower()
            cats = row["fsq_category_ids"] if isinstance(row["fsq_category_ids"], list) else []
            cat_strs = {str(c) for c in cats}

            if cat_strs & EXCLUDE_CATS:
                continue
            if any(kw in name_lower for kw in EXCLUDE_NAMES):
                continue
            has_food = any(kw in name_lower for kw in FOOD_SIGNALS)
            if not has_food and "indian" not in name_lower:
                continue

            restaurants.append({
                "name": row["name"],
                "cuisine": classify_cuisine(row["name"]),
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "address": row.get("address", "") or "",
                "locality": row.get("locality", "") or "",
                "postcode": row.get("postcode", "") or "",
                "chain": False,
                "source": "foursquare",
            })

        # Cache for next run
        with open(cache_path, "w") as f:
            json.dump(restaurants, f, indent=2)

        print(f"  Found {len(restaurants)} Indian restaurants from Foursquare")

    except Exception as e:
        print(f"  Foursquare fetch failed: {e}")

    if not restaurants:
        print("  No Foursquare data retrieved. Will rely on Google Places / CLUE data.")

    return restaurants


# ═══════════════════════════════════════════════════════════════════
# STEP 4: CLUE Restaurant Data (Melbourne Open Data)
# ═══════════════════════════════════════════════════════════════════

def fetch_clue_data():
    """
    Fetch Café, Restaurant, Bistro seats data from Melbourne Open Data portal.
    Uses the OpenDataSoft (ODS) Explore API v2.1 (Melbourne migrated from Socrata).
    """
    print("\n[4/5] Fetching CLUE restaurant data from Melbourne Open Data...")

    restaurants = []

    # OpenDataSoft API endpoint for CLUE cafe/restaurant dataset
    api_url = "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/cafes-and-restaurants-with-seating-capacity/records"

    indian_keywords = [
        "indian", "curry", "dosa", "tandoori", "biryani", "masala",
        "sri lanka", "nepal", "bengal", "punjab", "kerala", "mughal",
        "naan", "tikka", "roti", "chai", "spice", "dhaba", "thali",
        "bombay", "mumbai", "delhi", "madras", "chennai", "hyderabad",
        "kolkata", "lucknow", "jaipur", "himalaya", "everest", "gurkha",
        "colombo", "jaffna", "ceylon", "momo", "samosa", "chutney",
    ]

    # Fetch the most recent census year with pagination
    seen_names = set()
    offset = 0
    batch_size = 100
    total_fetched = 0

    try:
        # First get the latest census year
        r = requests.get(api_url, params={
            "select": "census_year",
            "group_by": "census_year",
            "order_by": "census_year desc",
            "limit": 1,
        }, timeout=30)
        latest_year = None
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            if results:
                latest_year = str(results[0].get("census_year", ""))[:4]
                print(f"  Latest census year: {latest_year}")

        while True:
            params = {
                "limit": batch_size,
                "offset": offset,
            }
            if latest_year:
                params["where"] = f"census_year>=date'{latest_year}-01-01' AND census_year<date'{int(latest_year)+1}-01-01'"

            r = requests.get(api_url, params=params, timeout=30)
            if r.status_code != 200:
                print(f"  API returned {r.status_code}")
                break

            data = r.json()
            results = data.get("results", [])
            if not results:
                break

            total_fetched += len(results)

            for row in results:
                name = str(row.get("trading_name", "")).lower()
                if any(kw in name for kw in indian_keywords):
                    # Deduplicate by trading name + address
                    dedup_key = (name, str(row.get("business_address", "")).lower())
                    if dedup_key in seen_names:
                        continue
                    seen_names.add(dedup_key)

                    lat = row.get("latitude")
                    lng = row.get("longitude")
                    # Try location field if lat/lng not available
                    if not lat or not lng:
                        loc = row.get("location", {})
                        if isinstance(loc, dict):
                            lat = loc.get("lat")
                            lng = loc.get("lon")

                    if lat and lng:
                        seats = row.get("number_of_seats", 0) or 0
                        restaurants.append({
                            "name": row.get("trading_name", "Unknown"),
                            "cuisine": classify_cuisine(row.get("trading_name", "")),
                            "latitude": float(lat),
                            "longitude": float(lng),
                            "address": row.get("business_address", "") or row.get("building_address", ""),
                            "locality": row.get("clue_small_area", "Melbourne CBD"),
                            "rating": 0,
                            "reviews": 0,
                            "chain": False,
                            "indoor_seats": seats if row.get("seating_type") == "Indoor" else 0,
                            "census_year": row.get("census_year", ""),
                            "source": "clue",
                        })

            offset += batch_size
            if len(results) < batch_size:
                break

            # Safety limit
            if total_fetched >= 10000:
                break

        print(f"  Scanned {total_fetched} CLUE records")

    except Exception as e:
        print(f"  CLUE API failed: {e}")

    print(f"  Found {len(restaurants)} Indian restaurants from CLUE")
    return restaurants


def classify_cuisine(name):
    """Classify an Indian restaurant's sub-cuisine from its name."""
    name_lower = name.lower()
    if any(w in name_lower for w in ["dosa", "south", "kerala", "chettinad", "udupi", "madras", "idli", "appam", "malabar"]):
        return "south_indian"
    elif any(w in name_lower for w in ["sri lanka", "colombo", "jaffna", "ceylon", "hopper"]):
        return "sri_lankan"
    elif any(w in name_lower for w in ["nepal", "gurkha", "himalaya", "everest", "momo", "sherpa", "kathmandu"]):
        return "nepalese"
    elif any(w in name_lower for w in ["bangla", "dhaka", "bengal", "sylhet"]):
        return "bangladeshi"
    elif any(w in name_lower for w in ["tandoori", "punjab", "mughal", "nawab", "delhi", "lucknow", "biryani", "naan", "tikka", "butter chicken", "roti"]):
        return "north_indian"
    else:
        return "general"


# ═══════════════════════════════════════════════════════════════════
# STEP 5: Google Places API (Optional)
# ═══════════════════════════════════════════════════════════════════

def fetch_google_places():
    """
    Fetch Indian restaurant data from Google Places API.
    Requires GOOGLE_PLACES_API_KEY environment variable.
    """
    print("\n[5/5] Fetching Google Places data...")

    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print("  GOOGLE_PLACES_API_KEY not set. Skipping Google Places.")
        print("  To use: export GOOGLE_PLACES_API_KEY=your_key_here")
        return []

    restaurants = []

    # Key Melbourne suburbs to search
    search_suburbs = [
        "Dandenong", "Clayton", "Truganina", "Tarneit", "Point Cook",
        "Glen Waverley", "Craigieburn", "Werribee", "Springvale", "Footscray",
        "Melbourne CBD", "Epping", "Berwick", "St Albans", "Caroline Springs",
        "Hoppers Crossing", "Deer Park", "Sunshine", "Narre Warren", "Cranbourne",
        "Pakenham", "Box Hill", "Preston", "Reservoir", "Melton",
        "Richmond", "South Yarra", "Roxburgh Park", "Wyndham Vale", "Williams Landing",
    ]

    # Google Places API (New) endpoint
    base_url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.priceLevel,places.id",
    }

    for suburb in search_suburbs:
        try:
            body = {
                "textQuery": f"Indian restaurant {suburb} Melbourne Australia",
                "maxResultCount": 20,
                "locationBias": {
                    "rectangle": {
                        "low": {"latitude": MELB_BBOX["south"], "longitude": MELB_BBOX["west"]},
                        "high": {"latitude": MELB_BBOX["north"], "longitude": MELB_BBOX["east"]},
                    }
                },
            }
            r = requests.post(base_url, json=body, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()

            results = data.get("places", [])
            for place in results:
                loc = place.get("location", {})
                lat = loc.get("latitude", 0)
                lng = loc.get("longitude", 0)

                # Verify it's in Melbourne bbox
                if not (MELB_BBOX["south"] <= lat <= MELB_BBOX["north"] and
                        MELB_BBOX["west"] <= lng <= MELB_BBOX["east"]):
                    continue

                restaurants.append({
                    "name": place.get("displayName", {}).get("text", "Unknown"),
                    "cuisine": classify_cuisine(place.get("displayName", {}).get("text", "")),
                    "latitude": lat,
                    "longitude": lng,
                    "address": place.get("formattedAddress", ""),
                    "locality": suburb,
                    "rating": place.get("rating", 0),
                    "reviews": place.get("userRatingCount", 0),
                    "price_level": {"PRICE_LEVEL_FREE": 0, "PRICE_LEVEL_INEXPENSIVE": 1, "PRICE_LEVEL_MODERATE": 2, "PRICE_LEVEL_EXPENSIVE": 3, "PRICE_LEVEL_VERY_EXPENSIVE": 4}.get(place.get("priceLevel", ""), 0),
                    "place_id": place.get("id", ""),
                    "chain": False,
                    "source": "google_places",
                })

            print(f"  {suburb}: {len(results)} results")
            time.sleep(0.3)  # Rate limiting

        except Exception as e:
            print(f"  {suburb} failed: {e}")

    # Deduplicate by name + rough location
    seen = set()
    unique = []
    for r in restaurants:
        key = (r["name"].lower(), round(r["latitude"], 3), round(r["longitude"], 3))
        if key not in seen:
            seen.add(key)
            unique.append(r)

    print(f"  Found {len(unique)} unique Indian restaurants from Google Places")
    return unique


# ═══════════════════════════════════════════════════════════════════
# MERGE & OUTPUT
# ═══════════════════════════════════════════════════════════════════

def merge_and_output(sa2_gdf, fsq_restaurants, clue_restaurants, google_restaurants):
    """Merge all data sources and output final files for the dashboard."""
    print("\n[MERGE] Combining all data sources...")

    # ── Merge restaurants ──
    all_restaurants = fsq_restaurants + clue_restaurants + google_restaurants

    # Deduplicate across sources (prefer Google > Foursquare > CLUE for rating data)
    seen = set()
    unique = []
    # Sort so Google comes first (has ratings), then Foursquare, then CLUE
    all_restaurants.sort(key=lambda r: {"google_places": 0, "foursquare": 1, "clue": 2}.get(r.get("source", ""), 3))

    for r in all_restaurants:
        key = (r["name"].lower().strip(), round(r["latitude"], 3), round(r["longitude"], 3))
        if key not in seen:
            seen.add(key)
            unique.append(r)

    print(f"  Total unique restaurants: {len(unique)}")
    print(f"  By source: Foursquare={sum(1 for r in unique if r.get('source')=='foursquare')}, "
          f"CLUE={sum(1 for r in unique if r.get('source')=='clue')}, "
          f"Google={sum(1 for r in unique if r.get('source')=='google_places')}")

    # Assign suburb from SA2 boundaries using spatial join
    if len(unique) > 0 and len(sa2_gdf) > 0:
        resto_gdf = gpd.GeoDataFrame(
            unique,
            geometry=gpd.points_from_xy(
                [r["longitude"] for r in unique],
                [r["latitude"] for r in unique]
            ),
            crs="EPSG:4326"
        )
        joined = gpd.sjoin(resto_gdf, sa2_gdf[["sa2_name", "geometry"]], how="left", predicate="within")
        for i, row in joined.iterrows():
            if pd.notna(row.get("sa2_name")):
                unique[i]["suburb"] = row["sa2_name"]
            elif not unique[i].get("locality"):
                unique[i]["suburb"] = "Unknown"
            else:
                unique[i]["suburb"] = unique[i]["locality"]

    # ── Count restaurants per SA2 ──
    suburb_counts = {}
    for r in unique:
        suburb = r.get("suburb", r.get("locality", "Unknown"))
        suburb_counts[suburb] = suburb_counts.get(suburb, 0) + 1

    if "sa2_name" in sa2_gdf.columns:
        sa2_gdf["restaurant_count"] = sa2_gdf["sa2_name"].map(lambda x: suburb_counts.get(x, 0))
    else:
        sa2_gdf["restaurant_count"] = 0

    # ── Compute gap score ──
    if "india_pct" in sa2_gdf.columns:
        max_pct = max(sa2_gdf["india_pct"].max(), 1)
        max_income = max(sa2_gdf["median_income"].max(), 1)
        sa2_gdf["supply_per_10k"] = sa2_gdf.apply(
            lambda row: row["restaurant_count"] / max(row["india_born"] / 10000, 0.1)
            if row.get("india_born", 0) > 0 else 0,
            axis=1
        )
        max_supply = max(sa2_gdf["supply_per_10k"].max(), 1)
        sa2_gdf["gap_score"] = (
            (sa2_gdf["india_pct"] / max_pct) * 0.4 +
            (sa2_gdf["median_income"] / max_income) * 0.2 +
            ((1 - sa2_gdf["supply_per_10k"] / max_supply) * 0.4)
        ).round(3)

        sa2_gdf["gap_label"] = sa2_gdf["supply_per_10k"].apply(
            lambda x: "Underserved" if x < 4 else "Balanced" if x < 8 else "Well-served"
        )

    # ── Save SA2 GeoJSON ──
    sa2_path = OUTPUT_DIR / "melbourne_sa2.geojson"
    sa2_gdf.to_file(sa2_path, driver="GeoJSON")
    print(f"  Saved: {sa2_path} ({sa2_path.stat().st_size / 1024:.0f} KB)")

    # ── Save restaurant JSON ──
    resto_path = OUTPUT_DIR / "melbourne_indian_restaurants.json"
    # Clean up for JSON serialization
    for r in unique:
        r.pop("geometry", None)
        # Ensure demand_score
        rating = r.get("rating", 0) or 0
        reviews = r.get("reviews", 0) or 0
        r["demand_score"] = round(rating * math.log10(reviews + 1), 2) if rating else 0

    with open(resto_path, "w") as f:
        json.dump(unique, f, indent=2)
    print(f"  Saved: {resto_path} ({resto_path.stat().st_size / 1024:.0f} KB)")

    # ── Generate dashboard_data.js ──
    # This is a JS file you can include in the HTML to replace the synthetic data
    js_path = OUTPUT_DIR / "dashboard_data.js"
    with open(js_path, "w") as f:
        f.write("// Auto-generated by prepare_data.py\n")
        f.write("// Replace the synthetic data in the HTML dashboard with this file\n\n")

        # SA2 GeoJSON (use window. so HTML can detect via window.sa2GeoJSON)
        # Add alias properties the HTML dashboard expects
        sa2_json = json.loads(sa2_gdf.to_json())
        for feat in sa2_json.get("features", []):
            props = feat.get("properties", {})
            centroid = shape(feat["geometry"]).centroid
            props["name"] = props.get("sa2_name", "")
            props["restaurants"] = props.get("restaurant_count", 0)
            props["income"] = props.get("median_income", 0)
            props["lng"] = round(centroid.x, 5)
            props["lat"] = round(centroid.y, 5)
            gap_label = props.get("gap_label", "Balanced")
            props["gap_class"] = gap_label.lower().replace("-", "").replace(" ", "")
        f.write(f"window.sa2GeoJSON = {json.dumps(sa2_json)};\n\n")

        # Restaurant GeoJSON
        resto_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {k: v for k, v in r.items() if k not in ("latitude", "longitude")},
                    "geometry": {
                        "type": "Point",
                        "coordinates": [r["longitude"], r["latitude"]]
                    }
                }
                for r in unique
            ]
        }
        f.write(f"window.restaurantGeoJSON = {json.dumps(resto_geojson)};\n\n")

        # Suburb label points
        label_features = []
        for _, row in sa2_gdf.iterrows():
            centroid = row.geometry.centroid
            label_features.append({
                "type": "Feature",
                "properties": {"name": row.get("sa2_name", ""), "india_pct": row.get("india_pct", 0)},
                "geometry": {"type": "Point", "coordinates": [centroid.x, centroid.y]}
            })
        label_geojson = {"type": "FeatureCollection", "features": label_features}
        f.write(f"window.labelGeoJSON = {json.dumps(label_geojson)};\n\n")

        # Suburbs array for panel logic
        suburbs_arr = []
        for _, row in sa2_gdf.iterrows():
            centroid = row.geometry.centroid
            suburbs_arr.append({
                "name": row.get("sa2_name", ""),
                "lng": round(centroid.x, 5),
                "lat": round(centroid.y, 5),
                "india_pct": row.get("india_pct", 0),
                "total_pop": int(row.get("total_pop", 0)),
                "india_born": int(row.get("india_born", 0)),
                "restaurants": int(row.get("restaurant_count", 0)),
                "income": int(row.get("median_income", 0)),
                "gap_score": float(row.get("gap_score", 0)),
                "gap_label": row.get("gap_label", "Balanced"),
                "gap_class": row.get("gap_label", "Balanced").lower().replace("-", ""),
            })
        f.write(f"window.suburbs = {json.dumps(suburbs_arr)};\n\n")

        # Restaurants flat array for panel logic
        f.write(f"window.restaurants = {json.dumps(unique)};\n")

    print(f"  Saved: {js_path} ({js_path.stat().st_size / 1024:.0f} KB)")
    print("\n✅ Done! Files saved to ./data/")
    print("\nTo use in the dashboard:")
    print('  1. Add <script src="data/dashboard_data.js"></script> to the HTML')
    print("  2. Remove the inline synthetic data generation code")
    print("  3. Open the HTML file in your browser")

    return sa2_gdf, unique


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Melbourne Indian Food Intelligence — Data Pipeline")
    print("=" * 60)

    sa2_gdf = fetch_sa2_boundaries()
    sa2_gdf = fetch_census_data(sa2_gdf)
    fsq_restaurants = fetch_foursquare_restaurants()
    clue_restaurants = fetch_clue_data()
    google_restaurants = fetch_google_places()
    merge_and_output(sa2_gdf, fsq_restaurants, clue_restaurants, google_restaurants)
