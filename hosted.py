from arcgis.gis import GIS
from arcgis.features import FeatureLayer, Feature
from datetime import datetime
import logging
import os
import traceback

# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------

PORTAL_URL = "https://arcgis-dev.virginmedia.ie/portal"
USERNAME = "portaladmin"
PASSWORD = "your_password"

TABLE_URL = (
    "https://arcgis-dev.virginmedia.ie/server/rest/services/"
    "AddressAdaption/Inventory/FeatureServer/0"
)

PAGE_SIZE = 100
BATCH_SIZE = 500

# ---------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------

LOG_FOLDER = "./logs"

if not os.path.exists(LOG_FOLDER):
    os.makedirs(LOG_FOLDER)

LOG_FILE = os.path.join(
    LOG_FOLDER,
    f"portal_inventory_{datetime.now().strftime('%Y%m%d')}.log"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# CONNECT
# ---------------------------------------------------------------------

logger.info("Connecting to Portal")

gis = GIS(
    PORTAL_URL,
    USERNAME,
    PASSWORD
)

logger.info(
    f"Connected to Portal: "
    f"{gis.properties.name}"
)

# ---------------------------------------------------------------------
# CONNECT TO HOSTED TABLE
# ---------------------------------------------------------------------

table = FeatureLayer(
    TABLE_URL,
    gis=gis
)

logger.info(
    f"Connected to Table: "
    f"{table.properties.name}"
)

# ---------------------------------------------------------------------
# EXISTING RECORD COUNT
# ---------------------------------------------------------------------

existing_count = table.query(
    where="1=1",
    return_count_only=True
)

logger.info(
    f"Existing Records: "
    f"{existing_count}"
)

# ---------------------------------------------------------------------
# DELETE EXISTING RECORDS
# ---------------------------------------------------------------------

logger.info("Deleting existing records")

delete_result = table.delete_features(
    where="1=1"
)

logger.info(
    f"Delete Result: "
    f"{delete_result}"
)

# ---------------------------------------------------------------------
# PORTAL SEARCH
# ---------------------------------------------------------------------

SEARCH_QUERY = (
    f'orgid:"{gis.properties.id}"'
)

result = gis.content.advanced_search(
    query=SEARCH_QUERY,
    max_items=1
)

logger.info(
    f"Portal Items Found: "
    f"{result['total']}"
)

# ---------------------------------------------------------------------
# BUILD FEATURES
# ---------------------------------------------------------------------

features_to_add = []

total_processed = 0
total_skipped = 0
total_errors = 0

start = 1

while True:

    logger.info(
        f"Reading page starting at {start}"
    )

    search_result = (
        gis.content.advanced_search(
            query=SEARCH_QUERY,
            start=start,
            max_items=PAGE_SIZE,
            sort_field="title",
            sort_order="asc"
        )
    )

    items = search_result["results"]

    if len(items) == 0:
        break

    for item in items:

        try:

            service_url = (
                getattr(item, "url", "")
                or ""
            )

            if (
                service_url and
                "services.arcgis.com"
                in service_url.lower()
            ):
                total_skipped += 1
                continue

            attrs = {

                "item_id":
                    (item.id or "")[:255],

                "title":
                    (item.title or "")[:255],

                "item_type":
                    (item.type or "")[:255],

                "access":
                    (item.access or "")[:255],

                "url":
                    service_url[:255],

                "tags":
                    (
                        ";".join(
                            item.tags or []
                        )
                    )[:255],

                "item_created":
                    item.created,

                "item_modified":
                    item.modified
            }

            logger.info(
                f"Prepared: "
                f"{attrs['item_id']} | "
                f"{attrs['title']}"
            )

            features_to_add.append(
                Feature(
                    attributes=attrs
                )
            )

            total_processed += 1

        except Exception:

            total_errors += 1

            logger.exception(
                f"Failed processing "
                f"{getattr(item,'id','Unknown')}"
            )

    next_start = (
        search_result.get(
            "nextStart",
            -1
        )
    )

    if next_start == -1:
        break

    start = next_start

logger.info(
    f"Prepared "
    f"{len(features_to_add)} "
    f"records"
)

# ---------------------------------------------------------------------
# INSERT
# ---------------------------------------------------------------------

total_inserted = 0

for i in range(
    0,
    len(features_to_add),
    BATCH_SIZE
):

    batch = (
        features_to_add[
            i:i + BATCH_SIZE
        ]
    )

    logger.info(
        f"Inserting batch "
        f"{i + 1} - "
        f"{i + len(batch)}"
    )

    try:

        result = (
            table.edit_features(
                adds=batch
            )
        )

        success_count = sum(
            1
            for r in result["addResults"]
            if r.get("success")
        )

        total_inserted += (
            success_count
        )

        logger.info(
            f"Inserted "
            f"{success_count} "
            f"records"
        )

    except Exception:

        logger.exception(
            "Batch insert failed"
        )

# ---------------------------------------------------------------------
# VALIDATE
# ---------------------------------------------------------------------

final_count = table.query(
    where="1=1",
    return_count_only=True
)

logger.info("=" * 60)
logger.info("INVENTORY REFRESH COMPLETE")
logger.info("=" * 60)

logger.info(
    f"Processed : "
    f"{total_processed}"
)

logger.info(
    f"Inserted : "
    f"{total_inserted}"
)

logger.info(
    f"Skipped : "
    f"{total_skipped}"
)

logger.info(
    f"Errors : "
    f"{total_errors}"
)

logger.info(
    f"Final Count : "
    f"{final_count}"
)

logger.info(
    f"Log File : "
    f"{LOG_FILE}"
)
