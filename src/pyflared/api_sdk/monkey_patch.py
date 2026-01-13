from cloudflare._base_client import PageInfo
from cloudflare.pagination import AsyncV4PagePaginationArray, SyncV4PagePaginationArray, V4PagePaginationArrayResultInfo
from loguru import logger

# --- 1. Patch the Data Model (so Pydantic reads 'total_pages') ---
# We add the missing type annotations and rebuild the model.
V4PagePaginationArrayResultInfo.__annotations__["total_pages"] = int | None
V4PagePaginationArrayResultInfo.__annotations__["total_count"] = int | None
V4PagePaginationArrayResultInfo.__annotations__["count"] = int | None

# Force Pydantic to re-compile the model with the new fields
# (This works for Pydantic v2, which the SDK uses)
try:
    V4PagePaginationArrayResultInfo.model_rebuild(force=True)
    logger.debug("✅ Patched V4PagePaginationArrayResultInfo model.")
except AttributeError:
    # Fallback for older Pydantic v1 (less likely, but safe to have)
    V4PagePaginationArrayResultInfo.update_forward_refs()


# --- 2. Define the Fixed Logic ---
def _fixed_next_page_info(self) -> PageInfo | None:
    current_page = self.result_info.page
    total_pages = getattr(self.result_info, "total_pages", None)  # Safe access

    if current_page is None:
        return None

    # THE FIX: Stop if we reached the total pages
    if total_pages is not None and current_page >= total_pages:
        return None

    return PageInfo(params={"page": current_page + 1})


# --- 3. Apply the Logic Patch ---
SyncV4PagePaginationArray.next_page_info = _fixed_next_page_info
AsyncV4PagePaginationArray.next_page_info = _fixed_next_page_info
logger.debug("✅ Patched Pagination Logic (Infinite Loop Fix).")
