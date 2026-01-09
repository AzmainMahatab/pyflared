from typing import Optional

from cloudflare._base_client import PageInfo
from cloudflare.pagination import AsyncV4PagePaginationArray


def _fixed_next_page_info(self) -> Optional[PageInfo]:
    current_page = self.result_info.page
    total_pages = self.result_info.total_pages

    if current_page is None:
        return None

    # THE FIX: Stop if we reached the total pages
    if total_pages is not None and current_page >= total_pages:
        return None

    return PageInfo(params={"page": current_page + 1})


# 2. Apply the Monkey Patch
AsyncV4PagePaginationArray.next_page_info = _fixed_next_page_info
