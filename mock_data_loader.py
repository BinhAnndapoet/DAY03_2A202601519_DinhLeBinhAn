"""
mock_data_loader.py  —  Helper nạp dữ liệu mock cho Role 2 (Tools).

Cách dùng trong src/tools.py:
    from mock_data_loader import (
        DATA, lookup_order, lookup_orders_by_email, check_inventory,
        get_return_policy,
    )

Ba tool tra cứu THUẦN (lookup_order, lookup_orders_by_email, check_inventory)
đã hiện thực đầy đủ ở đây vì chúng không có phán đoán nghiệp vụ.

Ba tool còn lại (check_return_eligibility, initiate_return, initiate_exchange)
để dạng STUB có ghi rõ quy tắc — Role 2 hiện thực phần logic (đây là phần "não"
nghiệp vụ, cũng là phần cần cho vòng suy luận ReAct).
"""

import json
import os
from datetime import date

# --- Nạp dữ liệu (single source of truth) ---
_HERE = os.path.dirname(os.path.abspath(__file__))
# Sửa đường dẫn cho khớp cấu trúc repo: config/mock_data.json
_DATA_PATH = os.path.join(_HERE, "..", "config", "mock_data.json")
if not os.path.exists(_DATA_PATH):
    _DATA_PATH = os.path.join(_HERE, "mock_data.json")  # fallback khi cùng thư mục

with open(_DATA_PATH, encoding="utf-8") as f:
    DATA = json.load(f)

ORDERS = DATA["mock_database"]
INVENTORY = DATA["mock_inventory"]
POLICY = DATA["return_policy"]
REASON_CODES = DATA["eligibility_reason_codes"]
TODAY = date.fromisoformat(DATA["meta"]["reference_today"])


def _days_since(delivery_date: str) -> int:
    """Số ngày kể từ ngày giao đến 'hôm nay' (reference_today)."""
    return (TODAY - date.fromisoformat(delivery_date)).days


# =====================================================================
#  TOOL 1 — lookup_order  (đã hiện thực đầy đủ)
# =====================================================================
def lookup_order(order_id: str) -> dict:
    order = ORDERS.get(order_id)
    if order is None:
        return {"error": "NOT_FOUND", "order_id": order_id}
    return {"order_id": order_id, **order}


# =====================================================================
#  TOOL 2 — lookup_orders_by_email  (đã hiện thực đầy đủ)
# =====================================================================
def lookup_orders_by_email(email: str) -> list:
    return [oid for oid, o in ORDERS.items()
            if o.get("customer_email") == email]


# =====================================================================
#  TOOL 3 — check_inventory  (đã hiện thực đầy đủ)
# =====================================================================
def check_inventory(product: str, size: str, color: str) -> dict:
    for row in INVENTORY:
        if (row["product"] == product
                and row["size"] == size
                and row["color"] == color):
            return {"stock": row["stock"]}
    return {"stock": 0}  # không có trong bảng kho => coi như hết


# =====================================================================
#  TOOL 4 — check_return_eligibility  (STUB — Role 2 hiện thực)
# =====================================================================
def check_return_eligibility(order_id: str, item_id: str) -> dict:
    """
    Trả về: {eligible: bool, reason_code, refund_method, days_left}

    QUY TẮC (theo POLICY, xử lý theo thứ tự ưu tiên):
      1. Đơn chưa giao (status != 'delivered')      -> NOT_DELIVERED_YET
      2. Món defective == True                       -> DEFECTIVE_FREE_RETURN (eligible)
      3. Món wrong_item_shipped == True              -> WRONG_ITEM_MERCHANT_FAULT (eligible)
      4. category ∈ final_sale_categories            -> FINAL_SALE_HYGIENE
      5. purchase_type == 'sale':
            - days > sale_window_days (14)           -> PAST_SALE_WINDOW
            - còn hạn                                -> SALE_STORE_CREDIT_ONLY (eligible, store_credit)
      6. Hàng regular:
            - window = vip_window_days nếu membership == 'VIP', ngược lại standard_window_days
            - days > window                          -> PAST_WINDOW
            - còn hạn                                -> ELIGIBLE (original_payment)

    LƯU Ý: điều kiện CONDITION_FAILED (khách đã giặt/mặc) KHÔNG kiểm ở đây —
    tool không biết. Đó là việc của Agent suy luận từ hội thoại (xem TC16).
    """
    raise NotImplementedError("Role 2: hiện thực theo QUY TẮC ở docstring.")


# =====================================================================
#  TOOL 5 — initiate_return  (STUB — Role 2 hiện thực)
# =====================================================================
def initiate_return(order_id: str, item_id: str, reason: str,
                    refund_method: str) -> dict:
    """
    Chỉ nên được gọi SAU khi check_return_eligibility trả eligible=True.
    Trả về: {ticket_id, status}. Có thể sinh ticket_id giả, ví dụ 'RET-xxxxx'.
    """
    raise NotImplementedError("Role 2: tạo ticket trả hàng giả lập.")


# =====================================================================
#  TOOL 6 — initiate_exchange  (STUB — Role 2 hiện thực)
# =====================================================================
def initiate_exchange(order_id: str, item_id: str, new_size: str,
                      new_color: str) -> dict:
    """
    Chỉ nên được gọi SAU khi eligible=True VÀ check_inventory trả stock > 0.
    Trả về: {ticket_id, status}. Ví dụ ticket_id 'EXC-xxxxx'.
    """
    raise NotImplementedError("Role 2: tạo ticket đổi hàng giả lập.")


# =====================================================================
#  TOOL 7 — get_return_policy  (đã hiện thực đầy đủ)
# =====================================================================
def get_return_policy(category: str = None) -> dict:
    return POLICY


# --- Kiểm tra nhanh khi chạy trực tiếp file ---
if __name__ == "__main__":
    print("Nạp OK:", len(ORDERS), "đơn,", len(INVENTORY), "dòng kho")
    print("lookup_order(ORD-2001):", lookup_order("ORD-2001")["status"])
    print("lookup_order(ORD-9999):", lookup_order("ORD-9999"))
    print("by_email(linh.pham@email.com):", lookup_orders_by_email("linh.pham@email.com"))
    print("inventory hoodie XL Đen:", check_inventory("Áo hoodie nỉ", "XL", "Đen"))
