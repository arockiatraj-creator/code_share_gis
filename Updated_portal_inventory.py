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

def log(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

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

gis = GIS(PORTAL_URL, USERNAME, PASSWORD)
log(f"Connected to: {gis.properties.name}")

table = FeatureLayer(TABLE_URL, gis=gis)

# ---------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------

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
            errors.append(
                f"{field_name}: value={value} expected={field_type}"
            )

    return errors

# ---------------------------------------------------------------------
# CLEAR TABLE
# ---------------------------------------------------------------------

existing_count = table.query(where="1=1", return_count_only=True)
log(f"Existing records: {existing_count}")

table.delete_features(where="1=1")

# ---------------------------------------------------------------------
# INVENTORY
# ---------------------------------------------------------------------

SEARCH_QUERY = f'orgid:"{gis.properties.id}"'

features_to_add = []
total_processed = 0
total_skipped = 0
total_errors = 0

start = 1

while True:

    results = gis.content.advanced_search(
        query=SEARCH_QUERY,
        start=start,
        max_items=PAGE_SIZE,
        sort_field="title",
        sort_order="asc"
    )

    items = results["results"]

    if not items:
        break

    for item in items:

        try:

            service_url = getattr(item, "url", "") or ""

            if service_url and "services.arcgis.com" in service_url.lower():
                total_skipped += 1
                continue

            raw_attrs = {
                "id": safe_text(item.id),
                "title": safe_text(item.title),
                "name": safe_text(getattr(item, "name", "")),
                "item_type": safe_text(item.type),
                "typeKeywords": ", ".join(getattr(item, "typeKeywords", []) or []),
                "url": safe_text(service_url),
                "owner": safe_text(item.owner),
                "ownerFolder": safe_text(getattr(item, "ownerFolder", "")),
                "description": safe_text(getattr(item, "description", "")),
                "snippet": safe_text(getattr(item, "snippet", "")),
                "tags": ", ".join(getattr(item, "tags", []) or []),
                "extent": json.dumps(getattr(item, "extent", []) or []),
                "spatialReference": json.dumps(getattr(item, "spatialReference", {})),
                "categories": json.dumps(getattr(item, "categories", [])),
                "accessInformation": safe_text(getattr(item, "accessInformation", "")),
                "licenseInfo": safe_text(getattr(item, "licenseInfo", "")),
                "culture": safe_text(getattr(item, "culture", "")),
                "item_access": safe_text(item.access),
                "protected": float(1 if getattr(item, "protected", False) else 0),
                "numViews": int(getattr(item, "numViews", 0) or 0),
                "numComments": int(getattr(item, "numComments", 0) or 0),
                "numRatings": int(getattr(item, "numRatings", 0) or 0),
                "avgRating": int(getattr(item, "avgRating", 0) or 0),
                "item_size": int(getattr(item, "size", 0) or 0),
                "listed": "True" if getattr(item, "listed", False) else "False",
                "industries": json.dumps(getattr(item, "industries", [])),
                "languages": json.dumps(getattr(item, "languages", [])),
                "appCategories": json.dumps(getattr(item, "appCategories", [])),
                "groupDesignations": json.dumps(getattr(item, "groupDesignations", [])),
                "contentStatus": safe_text(getattr(item, "contentStatus", "")),
                "documentation": safe_text(getattr(item, "documentation", "")),
                "item_guid": safe_text(getattr(item, "guid", "")),
                "homepage": safe_text(getattr(item, "homepage", "")),
                "banner": safe_text(getattr(item, "banner", "")),
                "thumbnail": safe_text(getattr(item, "thumbnail", "")),
                "largeThumbnail": safe_text(getattr(item, "largeThumbnail", "")),
                "properties": json.dumps(getattr(item, "properties", {})),
                "created": item.created,
                "modified": item.modified
            }

            attrs = {}

            for field_name, value in raw_attrs.items():

                if field_name in field_lengths:
                    attrs[field_name] = safe_text(
                        value,
                        field_lengths[field_name]
                    )
                else:
                    attrs[field_name] = value

            validation_errors = validate_attributes(attrs)

            if validation_errors:

                print("\\n" + "=" * 80)
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
            log(f"ERROR processing {getattr(item,'id','Unknown')}")
            log(str(ex))
            traceback.print_exc()

    next_start = results.get("nextStart", -1)

    if next_start == -1:
        break

    start = next_start

# ---------------------------------------------------------------------
# INSERT
# ---------------------------------------------------------------------

total_inserted = 0

for i in range(0, len(features_to_add), INSERT_BATCH_SIZE):

    batch = features_to_add[i:i + INSERT_BATCH_SIZE]

    try:

        result = table.edit_features(adds=batch)

        success_count = 0

        for idx, r in enumerate(result.get("addResults", [])):

            if r.get("success"):
                success_count += 1
            else:

                print("\\n" + "=" * 80)
                print("INSERT FAILED")
                print("=" * 80)
                print(json.dumps(r, indent=4))

                try:
                    failed_feature = batch[idx]

                    for k, v in failed_feature.attributes.items():
                        print(f"{k:<30} {str(v)[:200]}")
                except Exception:
                    pass

        total_inserted += success_count

    except Exception as ex:

        log(f"FAILED inserting batch starting at {i+1}")
        log(str(ex))
        traceback.print_exc()

# ---------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------

final_count = table.query(where="1=1", return_count_only=True)

print("\\n" + "=" * 70)
print("PORTAL INVENTORY REFRESH COMPLETED")
print("=" * 70)
print(f"Records Prepared : {len(features_to_add)}")
print(f"Records Inserted : {total_inserted}")
print(f"Records Skipped  : {total_skipped}")
print(f"Processing Errors: {total_errors}")
print(f"Final Count      : {final_count}")
print("=" * 70)
