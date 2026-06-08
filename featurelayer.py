from arcgis.gis import GIS
from arcgis.features import Feature
from datetime import datetime
import traceback
from arcgis.features import FeatureLayer

# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------

PORTAL_URL = "https://arcgis-dev.virginmedia.ie/portal"
USERNAME = "portaladmin"
PASSWORD = ""

# Hosted Table Item ID
TABLE_ITEM_ID = "b18dbce74a164c4fae8db409abdc1a0a"
TABLE_URL = r"https://arcgis-dev.virginmedia.ie/server/rest/services/AddressAdaption/Inventory/FeatureServer/0"

PAGE_SIZE = 100
INSERT_BATCH_SIZE = 500

# ---------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------

def log(message):
    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        f"{message}"
    )

# ---------------------------------------------------------------------
# CONNECT TO PORTAL
# ---------------------------------------------------------------------

try:

    log("Connecting to Portal...")

    gis = GIS(
        PORTAL_URL,
        USERNAME,
        PASSWORD
    )

    log(f"Connected to: {gis.properties.name}")
    log(f"Portal ID: {gis.properties.id}")

except Exception as ex:

    log("FAILED TO CONNECT TO PORTAL")
    raise ex

# ---------------------------------------------------------------------
# GET INVENTORY TABLE
# ---------------------------------------------------------------------

log("Locating inventory table...")

table = FeatureLayer(TABLE_URL, gis=gis)

print(f"Connected to table: {table.properties.name}")
print(f"Service URL: {TABLE_URL}")



# ---------------------------------------------------------------------
# RECORD COUNT BEFORE DELETE
# ---------------------------------------------------------------------

existing_count = table.query(
    where="1=1",
    return_count_only=True
)

log(
    f"Existing records in inventory table: "
    f"{existing_count}"
)

# ---------------------------------------------------------------------
# DELETE EXISTING RECORDS
# ---------------------------------------------------------------------

log("Deleting existing records...")

delete_result = table.delete_features(
    where="1=1"
)

log("Delete operation completed.")
print(delete_result)

remaining_count = table.query(
    where="1=1",
    return_count_only=True
)

log(
    f"Records remaining after delete: "
    f"{remaining_count}"
)

# ---------------------------------------------------------------------
# GET PORTAL ITEM COUNT
# ---------------------------------------------------------------------

SEARCH_QUERY = f'orgid:"{gis.properties.id}"'

test = gis.content.advanced_search(
    query=SEARCH_QUERY,
    max_items=1
)

log(
    f"Total portal items found: "
    f"{test['total']}"
)

# ---------------------------------------------------------------------
# COLLECT ITEMS
# ---------------------------------------------------------------------

features_to_add = []

total_processed = 0
total_skipped = 0
total_errors = 0

start = 1

log("Beginning portal inventory scan...")

while True:

    results = gis.content.advanced_search(
        query=SEARCH_QUERY,
        start=start,
        max_items=PAGE_SIZE,
        sort_field="title",
        sort_order="asc"
    )

    items = results["results"]

    log(
        f"Start={results['start']} "
        f"Num={results['num']} "
        f"NextStart={results['nextStart']}"
    )

    if len(items) == 0:
        break

    for item in items:

        try:

            service_url = getattr(item, "url", "") or ""

            # ---------------------------------------------------------
            # Skip ArcGIS Online hosted services
            # ---------------------------------------------------------

            if (
                service_url and
                "services.arcgis.com" in service_url.lower()
            ):

                total_skipped += 1

                log(
                    f"SKIPPED: {item.title} "
                    f"({item.id})"
                )

                continue

            attrs = {
                "item_id": item.id,
                "title": item.title,
                "item_type": item.type,
                "access": item.access,
                "url": "",
                "tags": "",
                "item_created": item.created,
                "item_modified": item.modified
            }

            # ---------------------------------------------------------
            # PRINT RECORD TO BE INSERTED
            # ---------------------------------------------------------

##            print("\n--------------------------------------------------")
##            print("RECORD TO BE INSERTED")
##            print("--------------------------------------------------")
##            print(f"item_id       : {attrs['item_id']}")
##            print(f"title         : {attrs['title']}")
##            print(f"item_type     : {attrs['item_type']}")
##            print(f"access        : {attrs['access']}")
##            print(f"url           : {attrs['url']}")
##            print(f"tags          : {attrs['tags']}")

            if attrs["item_created"]:
                print(
                    f"item_created  : "
                    f"{datetime.fromtimestamp(attrs['item_created']/1000)}"
                )

            if attrs["item_modified"]:
                print(
                    f"item_modified : "
                    f"{datetime.fromtimestamp(attrs['item_modified']/1000)}"
                )

            features_to_add.append(
                Feature(
                    attributes=attrs
                )
            )

            total_processed += 1

        except Exception as ex:

            total_errors += 1

            log(
                f"ERROR processing item "
                f"{getattr(item,'id','Unknown')}"
            )

            log(str(ex))

            traceback.print_exc()

    next_start = results.get(
        "nextStart",
        -1
    )

    if next_start == -1:
        break

    start = next_start

# ---------------------------------------------------------------------
# SUMMARY BEFORE INSERT
# ---------------------------------------------------------------------

log("Inventory scan completed.")

log(
    f"Records Prepared : "
    f"{len(features_to_add)}"
)

log(
    f"Records Skipped : "
    f"{total_skipped}"
)

log(
    f"Processing Errors : "
    f"{total_errors}"
)

# ---------------------------------------------------------------------
# INSERT RECORDS
# ---------------------------------------------------------------------

total_inserted = 0

log("Starting table load...")

for i in range(
    0,
    len(features_to_add),
    INSERT_BATCH_SIZE
):

    batch = features_to_add[
        i:i + INSERT_BATCH_SIZE
    ]

    log(
        f"Inserting records "
        f"{i + 1} to "
        f"{i + len(batch)}"
    )

    try:

        result = table.edit_features(
            adds=batch
        )

        success_count = 0

        for r in result["addResults"]:

            print(r)

            if r.get("success"):
                success_count += 1

        total_inserted += success_count

        log(
            f"Batch Insert Summary: "
            f"{success_count}/{len(batch)} "
            f"successful"
        )

    except Exception as ex:

        log(
            f"FAILED inserting batch "
            f"starting at {i + 1}"
        )

        log(str(ex))

        traceback.print_exc()

# ---------------------------------------------------------------------
# VALIDATE FINAL COUNT
# ---------------------------------------------------------------------

final_count = table.query(
    where="1=1",
    return_count_only=True
)

# ---------------------------------------------------------------------
# COMPLETION SUMMARY
# ---------------------------------------------------------------------

print("\n")
print("=" * 70)
print("PORTAL INVENTORY REFRESH COMPLETED")
print("=" * 70)

print(
    f"Portal Items Found      : "
    f"{test['total']}"
)

print(
    f"Records Prepared        : "
    f"{len(features_to_add)}"
)

print(
    f"Records Inserted        : "
    f"{total_inserted}"
)

print(
    f"Records Skipped         : "
    f"{total_skipped}"
)

print(
    f"Processing Errors       : "
    f"{total_errors}"
)

print(
    f"Final Table Record Count: "
    f"{final_count}"
)

print(
    f"Completed At            : "
    f"{datetime.now()}"
)

print("=" * 70)
