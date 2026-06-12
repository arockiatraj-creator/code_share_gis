from arcgis.gis import GIS
from arcgis.features import Feature, FeatureLayer
from datetime import datetime
import json
import traceback

# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------

PORTAL_URL = "https://arcgis-dev.virginmedia.ie/portal"
USERNAME = "portaladmin"
PASSWORD = "Jk1R9Id7"

TABLE_URL = r"https://arcgis-dev.virginmedia.ie/server/rest/services/AddressAdaption/Inventory/FeatureServer/0"

PAGE_SIZE = 100
INSERT_BATCH_SIZE = 500
MAX_PAGES = 1000   # ✅ Safety limit for pagination

# ---------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------

def log(message, level="INFO"):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}")

def safe_text(value, max_len=None):
    value = "" if value is None else str(value)
    return value[:max_len] if max_len else value

# ---------------------------------------------------------------------
# CONNECT
# ---------------------------------------------------------------------

log("Starting Portal Inventory Refresh Job")

try:
    log("Connecting to GIS portal...")
    gis = GIS(PORTAL_URL, USERNAME, PASSWORD)
    log(f"Connected to: {gis.properties.name}")
except Exception:
    log("Failed to connect to GIS portal", "ERROR")
    raise

log(f"Target table URL: {TABLE_URL}")
table = FeatureLayer(TABLE_URL, gis=gis)

# ---------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------

log("Loading table schema...")

field_lookup = {}
field_lengths = {}

for fld in table.properties.fields:
    field_lookup[fld["name"]] = {
        "type": fld["type"],
        "length": fld.get("length")
    }

    if str(fld["type"]).lower().endswith("string"):
        field_lengths[fld["name"]] = fld.get("length", 255)

log(f"Loaded {len(field_lookup)} fields")
log(f"String fields with limits: {len(field_lengths)}")

# ---------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------

def validate_attributes(attrs):

    errors = []

    for field_name, value in attrs.items():

        if field_name not in field_lookup:
            errors.append(f"Field not found: {field_name}")
            continue

        field_type = str(field_lookup[field_name]["type"]).lower()

        try:
            if value is None:
                continue

            if "integer" in field_type:
                int(value)

            elif "double" in field_type:
                float(value)

            elif "date" in field_type:
                if not isinstance(value, (int, float)):
                    raise ValueError("Expected epoch milliseconds")

            elif "string" in field_type:
                max_len = field_lookup[field_name]["length"]
                if max_len and len(str(value)) > max_len:
                    errors.append(f"{field_name}: exceeds max length")

        except Exception:
            errors.append(f"{field_name}: invalid type")

    return errors

# ---------------------------------------------------------------------
# CLEAR TABLE
# ---------------------------------------------------------------------

log("Checking existing records...")
existing_count = table.query(where="1=1", return_count_only=True)
log(f"Existing records: {existing_count}")

log("Deleting existing records...")
table.delete_features(where="1=1")
log("Table cleared successfully")

# ---------------------------------------------------------------------
# INVENTORY EXTRACTION (FIXED)
# ---------------------------------------------------------------------

SEARCH_QUERY = f'orgid:"{gis.properties.id}"'

features_to_add = []
total_processed = 0
total_skipped = 0
total_errors = 0

seen_starts = set()
page_counter = 0
seen_item_ids = set()   # ✅ prevents duplicate items

log("Starting inventory extraction")

start = 1

while True:

    # ✅ LOOP PROTECTION
    if start in seen_starts:
        log(f"Pagination loop detected at start={start}", "ERROR")
        break

    seen_starts.add(start)

    page_counter += 1
    if page_counter > MAX_PAGES:
        log("Max page limit reached. Stopping.", "ERROR")
        break

    log(f"Fetching items | start={start}")

    try:
        results = gis.content.advanced_search(
            query=SEARCH_QUERY,
            start=start,
            max_items=PAGE_SIZE,
            sort_field="title",
            sort_order="asc"
        )
    except Exception as ex:
        log("Search failed", "ERROR")
        log(str(ex), "ERROR")
        break

    items = results.get("results", [])
    log(f"Fetched {len(items)} items")

    if not items:
        log("No more items found")
        break

    for item in items:
        try:
            # ✅ DUPLICATE PROTECTION
            if item.id in seen_item_ids:
                continue
            seen_item_ids.add(item.id)

            service_url = getattr(item, "url", "") or ""

            if service_url and "services.arcgis.com" in service_url.lower():
                total_skipped += 1
                continue

            # (keep log minimal to reduce noise)
            # log(f"Processing: {item.id}")

            raw_attrs = {
                "id": safe_text(item.id),
                "title": safe_text(item.title),
                "name": safe_text(getattr(item, "name", "")),
                "item_type": safe_text(item.type),
                "typekeywords": ", ".join(getattr(item, "typeKeywords", []) or []),
                "url": safe_text(service_url),
                "owner": safe_text(item.owner),
                "ownerfolder": safe_text(getattr(item, "ownerFolder", "")),
                "description": safe_text(getattr(item, "description", "")),
                "snippet": safe_text(getattr(item, "snippet", "")),
                "tags": ", ".join(getattr(item, "tags", []) or []),
                "extent": json.dumps(getattr(item, "extent", []) or []),
                "spatialreference": json.dumps(getattr(item, "spatialReference", {})),
                "categories": json.dumps(getattr(item, "categories", [])),
                "accessinformation": safe_text(getattr(item, "accessInformation", "")),
                "licenseinfo": safe_text(getattr(item, "licenseInfo", "")),
                "culture": safe_text(getattr(item, "culture", "")),
                "item_access": safe_text(item.access),
                "protected": float(1 if getattr(item, "protected", False) else 0),
                "numviews": int(getattr(item, "numViews", 0) or 0),
                "numcomments": int(getattr(item, "numComments", 0) or 0),
                "numratings": int(getattr(item, "numRatings", 0) or 0),
                "avgrating": int(getattr(item, "avgRating", 0) or 0),
                "item_size": int(getattr(item, "size", 0) or 0),
                "listed": "True" if getattr(item, "listed", False) else "False",
                "industries": json.dumps(getattr(item, "industries", [])),
                "languages": json.dumps(getattr(item, "languages", [])),
                "appcategories": json.dumps(getattr(item, "appCategories", [])),
                "groupdesignations": json.dumps(getattr(item, "groupDesignations", [])),
                "contentstatus": safe_text(getattr(item, "contentStatus", "")),
                "documentation": safe_text(getattr(item, "documentation", "")),
                "item_guid": safe_text(getattr(item, "guid", "")),
                "homepage": safe_text(getattr(item, "homepage", "")),
                "banner": safe_text(getattr(item, "banner", "")),
                "thumbnail": safe_text(getattr(item, "thumbnail", "")),
                "largethumbnail": safe_text(getattr(item, "largeThumbnail", "")),
                "properties": json.dumps(getattr(item, "properties", {})),
                "created": item.created,
                "modified": item.modified
            }

            attrs = {}
            for k, v in raw_attrs.items():
                attrs[k] = safe_text(v, field_lengths[k]) if k in field_lengths else v

            validation_errors = validate_attributes(attrs)

            if validation_errors:
                log(f"Validation failed: {item.id}", "ERROR")
                total_errors += 1
                continue

            features_to_add.append(Feature(attributes=attrs))
            total_processed += 1

        except Exception as ex:
            total_errors += 1
            log(f"Error processing item {item.id}", "ERROR")
            log(str(ex), "ERROR")

    next_start = results.get("nextStart", -1)

    # ✅ SAFE EXIT CONDITIONS
    if next_start == -1 or next_start == start:
        log(f"Stopping pagination (nextStart={next_start})")
        break

    log(f"Moving to next page: {next_start}")
    start = next_start

# ---------------------------------------------------------------------
# INSERT
# ---------------------------------------------------------------------

log(f"Starting insert of {len(features_to_add)} records")

total_inserted = 0

for i in range(0, len(features_to_add), INSERT_BATCH_SIZE):

    batch = features_to_add[i:i + INSERT_BATCH_SIZE]

    log(f"Inserting batch {i//INSERT_BATCH_SIZE + 1}")

    try:
        result = table.edit_features(adds=batch)

        success_count = sum(1 for r in result.get("addResults", []) if r.get("success"))
        total_inserted += success_count

        log(f"Batch result: {success_count}/{len(batch)}")

    except Exception as ex:
        log("Batch insert failed", "ERROR")
        log(str(ex), "ERROR")

# ---------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------

log("Fetching final count...")
final_count = table.query(where="1=1", return_count_only=True)

print("\n" + "=" * 70)
print("PORTAL INVENTORY REFRESH COMPLETED")
print("=" * 70)
print(f"Records Prepared : {len(features_to_add)}")
print(f"Records Inserted : {total_inserted}")
print(f"Records Skipped  : {total_skipped}")
print(f"Processing Errors: {total_errors}")
print(f"Final Count      : {final_count}")
print("=" * 70)

log("Job completed successfully")
