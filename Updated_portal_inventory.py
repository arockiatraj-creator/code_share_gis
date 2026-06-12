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

# ---------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------

def log(message, level="INFO"):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}")

def safe_text(value, max_len=None):
    if value is None:
        value = ""
    else:
        value = str(value)

    if max_len is not None:
        value = value[:max_len]

    return value

# ---------------------------------------------------------------------
# CONNECT
# ---------------------------------------------------------------------

log("Starting Portal Inventory Refresh Job")

try:
    log("Connecting to GIS portal...")
    gis = GIS(PORTAL_URL, USERNAME, PASSWORD)
    log(f"Connected to: {gis.properties.name}")
except Exception as e:
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
                    errors.append(
                        f"{field_name}: length {len(str(value))} exceeds {max_len}"
                    )

        except Exception:
            errors.append(f"{field_name}: value={value} expected={field_type}")

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
# INVENTORY
# ---------------------------------------------------------------------

SEARCH_QUERY = f'orgid:"{gis.properties.id}"'

features_to_add = []
total_processed = 0
total_skipped = 0
total_errors = 0

log("Starting inventory extraction")

start = 1

while True:

    log(f"Fetching items | start={start} | page_size={PAGE_SIZE}")

    results = gis.content.advanced_search(
        query=SEARCH_QUERY,
        start=start,
        max_items=PAGE_SIZE,
        sort_field="title",
        sort_order="asc"
    )

    items = results["results"]
    log(f"Fetched {len(items)} items")

    if not items:
        log("No more items found")
        break

    for item in items:

        try:
            service_url = getattr(item, "url", "") or ""

            if service_url and "services.arcgis.com" in service_url.lower():
                total_skipped += 1
                continue

            log(f"Processing item: {item.id} | {item.title}")

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

            for field_name, value in raw_attrs.items():
                if field_name in field_lengths:
                    attrs[field_name] = safe_text(value, field_lengths[field_name])
                else:
                    attrs[field_name] = value

            validation_errors = validate_attributes(attrs)

            if validation_errors:
                log(f"Validation failed for item: {item.id}", "ERROR")

                print("\n" + "=" * 80)
                print(f"VALIDATION FAILED: {item.id}")
                print("=" * 80)
                for err in validation_errors:
                    print(err)

                total_errors += 1
                continue

            features_to_add.append(Feature(attributes=attrs))
            total_processed += 1

        except Exception as ex:
            total_errors += 1
            log(f"ERROR processing item: {getattr(item,'id','Unknown')}", "ERROR")
            log(str(ex), "ERROR")
            traceback.print_exc()

    next_start = results.get("nextStart", -1)

    if next_start == -1:
        log("Reached last page")
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

    log(f"Inserting batch {i//INSERT_BATCH_SIZE + 1} "
        f"(records {i+1} - {i+len(batch)})")

    try:
        result = table.edit_features(adds=batch)

        success_count = 0

        for idx, r in enumerate(result.get("addResults", [])):
            if r.get("success"):
                success_count += 1
            else:
                log("INSERT FAILED", "ERROR")

                print("\n" + "=" * 80)
                print("INSERT FAILED")
                print("=" * 80)
                print(json.dumps(r, indent=4))

        total_inserted += success_count

        log(f"Batch result: {success_count}/{len(batch)} successful")

    except Exception as ex:
        log(f"FAILED inserting batch starting at {i+1}", "ERROR")
        log(str(ex), "ERROR")
        traceback.print_exc()

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
