"""codebeamer adapter (stub) — same item model as ReqIF, REST transport.

Implement against your instance's REST v3 API:
  pull(tracker_id) -> list[ReqIfObject]-like records   (GET /api/v3/trackers/{id}/items)
  push(work_product_content, tracker_id)                 (POST/PUT items; `reqif_id` ↔ codebeamer item id)
Keep this module transport-only: mapping to the house grammar stays in reqif.to_work_product /
from_work_product so both adapters produce identical work products.
"""
from __future__ import annotations


class CodebeamerClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def pull(self, tracker_id: int):
        raise NotImplementedError("wire to GET /api/v3/trackers/{id}/items and map to ReqIfObject")

    def push(self, content: str, tracker_id: int):
        raise NotImplementedError("wire to POST/PUT /api/v3/items using reqif_id as the item key")
