"""
Tool registry cho đề tài 5: Trợ lý tra cứu đơn hàng và xử lý đổi/trả.

Mốc 1:
    Khai báo các tool phù hợp với đề tài và đồng bộ tên với tool contract.
Mốc 2:
    Chuẩn hóa docstring, tham số, kiểu trả về và mô tả sử dụng.
Mốc 3:
    Cài đặt logic trên dữ liệu mock; mọi lỗi được chuyển thành kết quả có
    ``error`` và ``message`` thay vì làm ứng dụng bị crash.
"""

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


ToolResult = Dict[str, Any]
EmailLookupResult = Union[List[str], ToolResult]

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "mock_data.json"

# Trạng thái tạo ticket được giữ trong bộ nhớ cho phiên demo hiện tại.
# Dictionary giúp lời gọi lặp lại có tính idempotent, không tạo ticket trùng.
_RETURN_REQUESTS: Dict[tuple[str, str], ToolResult] = {}
_EXCHANGE_REQUESTS: Dict[tuple[str, str], ToolResult] = {}
_RESERVED_INVENTORY: Dict[tuple[str, str, str], int] = {}


def _error(code: str, message: str, **details: Any) -> ToolResult:
    """Tạo kết quả lỗi thống nhất để public tool không ném exception."""
    result: ToolResult = {"error": code, "message": message}
    result.update(details)
    return result


def _load_lab_config() -> ToolResult:
    """Đọc dữ liệu mock và chính sách do Role 1 định nghĩa."""
    with _CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    required_sections = {"meta", "mock_database", "mock_inventory"}
    missing_sections = required_sections.difference(config)
    if missing_sections:
        missing = ", ".join(sorted(missing_sections))
        raise ValueError(f"Thiếu dữ liệu cấu hình: {missing}.")
    return config


def _required_text(value: Any, field_name: str) -> str:
    """Chuẩn hóa một tham số chuỗi bắt buộc hoặc báo ValueError."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Tham số '{field_name}' không được để trống.")
    return value.strip()


def _normalize_order_id(order_id: Any) -> str:
    """Chuẩn hóa mã đơn về chữ hoa."""
    return _required_text(order_id, "order_id").upper()


def _normalize_item_id(item_id: Any) -> str:
    """Chuẩn hóa mã sản phẩm trong đơn về chữ hoa."""
    return _required_text(item_id, "item_id").upper()


def _normalize_key(value: Any, field_name: str) -> str:
    """Chuẩn hóa chuỗi dùng khi so khớp không phân biệt hoa thường."""
    return _required_text(value, field_name).casefold()


def _find_item(order: ToolResult, item_id: str) -> Optional[ToolResult]:
    """Tìm một item trong dữ liệu đơn hàng."""
    for item in order.get("items", []):
        if str(item.get("item_id", "")).upper() == item_id:
            return item
    return None


def _reference_today(config: ToolResult) -> date:
    """Lấy ngày tham chiếu cố định để kết quả demo có thể lặp lại."""
    raw_date = config["meta"].get("reference_today")
    if not raw_date:
        return date.today()
    return date.fromisoformat(str(raw_date))


def _reason_message(config: ToolResult, reason_code: str) -> str:
    """Lấy mô tả tiếng Việt cho một eligibility reason code."""
    messages = config["meta"].get("eligibility_reason_codes", {})
    return str(messages.get(reason_code, reason_code))


def lookup_order(order_id: str) -> ToolResult:
    """
    Tra cứu chi tiết một đơn hàng theo mã đơn.

    Chỉ gọi tool này khi người dùng đã cung cấp một mã đơn cụ thể. Kết quả
    được dùng để xác định trạng thái giao hàng, ngày giao, ETA và các sản
    phẩm trong đơn trước khi thực hiện luồng đổi/trả.

    Args:
        order_id: Mã đơn hàng, ví dụ ``"ORD-2001"``.

    Returns:
        Dictionary có một trong hai cấu trúc:

        - Thành công: ``{"order_id": str, "status": str,
          "delivery_date": str | None, "eta": str | None, "items": list,
          "customer_email": str, "is_gift": bool, "membership": str}``.
        - Thất bại: ``{"error": str, "message": str}``.

    Notes:
        Tool chỉ tra cứu dữ liệu, không thay đổi trạng thái đơn hàng.
        Không tự suy đoán dữ liệu khi mã đơn không tồn tại.
    """
    try:
        normalized_id = _normalize_order_id(order_id)
        config = _load_lab_config()
        order = config["mock_database"].get(normalized_id)
        if order is None:
            return _error(
                "NOT_FOUND",
                f"Không tìm thấy đơn hàng '{normalized_id}'.",
            )

        result = deepcopy(order)
        result["order_id"] = normalized_id
        result.setdefault("delivery_date", None)
        result.setdefault("eta", None)
        result.setdefault("items", [])
        result.setdefault("is_gift", False)
        result.setdefault("membership", "none")
        return result
    except (TypeError, ValueError) as exc:
        return _error("INVALID_INPUT", str(exc))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        return _error(
            "DATA_SOURCE_ERROR",
            "Không thể đọc dữ liệu đơn hàng lúc này.",
            detail=str(exc),
        )
    except Exception as exc:
        return _error(
            "INTERNAL_TOOL_ERROR",
            "Không thể tra cứu đơn hàng lúc này.",
            detail=str(exc),
        )


def lookup_orders_by_email(email: str) -> EmailLookupResult:
    """
    Tìm các mã đơn hàng liên kết với email khách hàng.

    Dùng khi khách hàng quên mã đơn. Nếu tìm thấy nhiều đơn, Agent phải
    hiển thị danh sách và yêu cầu người dùng chọn một đơn trước khi tiếp
    tục kiểm tra đổi/trả.

    Args:
        email: Email khách hàng, ví dụ ``"linh.pham@email.com"``.

    Returns:
        Danh sách mã đơn hàng khi tra cứu thành công. Khi đầu vào hoặc
        nguồn dữ liệu có lỗi, trả ``{"error": str, "message": str}``.

    Notes:
        Tool không tự chọn đơn thay cho người dùng khi có nhiều kết quả.
    """
    try:
        normalized_email = _normalize_key(email, "email")
        if "@" not in normalized_email or normalized_email.startswith("@"):
            return _error(
                "INVALID_EMAIL",
                "Email không đúng định dạng.",
            )

        config = _load_lab_config()
        order_ids = [
            order_id
            for order_id, order in config["mock_database"].items()
            if str(order.get("customer_email", "")).casefold()
            == normalized_email
        ]
        return sorted(order_ids)
    except (TypeError, ValueError) as exc:
        return _error("INVALID_INPUT", str(exc))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        return _error(
            "DATA_SOURCE_ERROR",
            "Không thể đọc dữ liệu đơn hàng lúc này.",
            detail=str(exc),
        )
    except Exception as exc:
        return _error(
            "INTERNAL_TOOL_ERROR",
            "Không thể tra cứu đơn hàng theo email lúc này.",
            detail=str(exc),
        )


def check_return_eligibility(order_id: str, item_id: str) -> ToolResult:
    """
    Kiểm tra một sản phẩm có đủ điều kiện đổi/trả hay không.

    Tool đối chiếu trạng thái giao hàng, ngày giao, loại mua hàng
    (thường/sale/final sale), danh mục sản phẩm, quyền lợi VIP và các
    trường hợp hàng lỗi hoặc giao sai.

    Args:
        order_id: Mã đơn chứa sản phẩm, ví dụ ``"ORD-2001"``.
        item_id: Mã sản phẩm trong đơn, ví dụ ``"ORD-2001-A"``.

    Returns:
        Dictionary dạng ``{"eligible": bool, "reason_code": str,
        "refund_method": str | None, "days_left": int | None}``.
        Nếu dữ liệu đầu vào hoặc nguồn dữ liệu có lỗi, kết quả chứa
        ``error`` và ``message``.

    Notes:
        Tool chỉ đánh giá theo dữ liệu hệ thống. Điều kiện như sản phẩm đã
        giặt, đã mặc hoặc mất tag phải được Agent làm rõ từ hội thoại.
        Tool không tự tạo yêu cầu đổi/trả.
    """
    try:
        normalized_order_id = _normalize_order_id(order_id)
        normalized_item_id = _normalize_item_id(item_id)
        config = _load_lab_config()
        order = config["mock_database"].get(normalized_order_id)
        if order is None:
            return _error(
                "ORDER_NOT_FOUND",
                f"Không tìm thấy đơn hàng '{normalized_order_id}'.",
            )

        item = _find_item(order, normalized_item_id)
        if item is None:
            return _error(
                "ITEM_NOT_FOUND",
                (
                    f"Không tìm thấy sản phẩm '{normalized_item_id}' "
                    f"trong đơn '{normalized_order_id}'."
                ),
            )

        if order.get("status") != "delivered":
            code = "NOT_DELIVERED_YET"
            return {
                "eligible": False,
                "reason_code": code,
                "reason": _reason_message(config, code),
                "refund_method": None,
                "days_left": None,
            }

        # Hàng lỗi hoặc giao sai là lỗi cửa hàng và được ưu tiên xử lý,
        # không bị giới hạn bởi cửa sổ đổi/trả thông thường.
        if item.get("defective"):
            code = "DEFECTIVE_FREE_RETURN"
            return {
                "eligible": True,
                "reason_code": code,
                "reason": _reason_message(config, code),
                "refund_method": "original_payment",
                "days_left": None,
                "free_return_shipping": True,
            }

        if item.get("wrong_item_shipped"):
            code = "WRONG_ITEM_MERCHANT_FAULT"
            return {
                "eligible": True,
                "reason_code": code,
                "reason": _reason_message(config, code),
                "refund_method": "original_payment",
                "days_left": None,
                "free_return_shipping": True,
            }

        policy = config["meta"]["return_policy"]
        category = str(item.get("category", "")).casefold()
        final_sale_categories = {
            str(value).casefold()
            for value in policy.get("final_sale_categories", [])
        }
        purchase_type = str(item.get("purchase_type", "regular")).casefold()

        if (
            category in final_sale_categories
            or purchase_type == "final_sale"
        ):
            code = "FINAL_SALE_HYGIENE"
            return {
                "eligible": False,
                "reason_code": code,
                "reason": _reason_message(config, code),
                "refund_method": None,
                "days_left": None,
            }

        delivery_date_value = order.get("delivery_date")
        if not delivery_date_value:
            return _error(
                "MISSING_DELIVERY_DATE",
                "Đơn đã giao nhưng thiếu ngày giao hàng.",
            )

        delivered_on = date.fromisoformat(str(delivery_date_value))
        elapsed_days = (_reference_today(config) - delivered_on).days
        if elapsed_days < 0:
            return _error(
                "INVALID_DELIVERY_DATE",
                "Ngày giao hàng nằm sau ngày tham chiếu.",
            )

        is_sale = purchase_type in {"sale", "clearance"}
        is_vip = str(order.get("membership", "")).casefold() == "vip"
        is_gift = bool(order.get("is_gift"))

        if is_sale:
            window_days = int(policy["sale_window_days"])
            refund_method = str(policy["sale_refund_method"])
            expired_code = "PAST_SALE_WINDOW"
            eligible_code = "SALE_STORE_CREDIT_ONLY"
        elif is_vip:
            window_days = int(policy["vip_window_days"])
            refund_method = str(policy["regular_refund_method"])
            expired_code = "PAST_WINDOW"
            eligible_code = "ELIGIBLE"
        else:
            window_days = int(policy["standard_window_days"])
            refund_method = str(policy["regular_refund_method"])
            expired_code = "PAST_WINDOW"
            eligible_code = "ELIGIBLE"

        # Quà tặng không hoàn tiền về người mua; người nhận nhận store credit.
        if is_gift:
            refund_method = "store_credit"

        days_left = window_days - elapsed_days
        if days_left < 0:
            return {
                "eligible": False,
                "reason_code": expired_code,
                "reason": _reason_message(config, expired_code),
                "refund_method": None,
                "days_left": 0,
                "policy_window_days": window_days,
            }

        return {
            "eligible": True,
            "reason_code": eligible_code,
            "reason": _reason_message(config, eligible_code),
            "refund_method": refund_method,
            "days_left": days_left,
            "policy_window_days": window_days,
            "gift_return": is_gift,
        }
    except (TypeError, ValueError) as exc:
        return _error("INVALID_INPUT", str(exc))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        return _error(
            "DATA_SOURCE_ERROR",
            "Không thể đọc dữ liệu chính sách đổi/trả lúc này.",
            detail=str(exc),
        )
    except Exception as exc:
        return _error(
            "INTERNAL_TOOL_ERROR",
            "Không thể kiểm tra điều kiện đổi/trả lúc này.",
            detail=str(exc),
        )


def check_inventory(product: str, size: str, color: str) -> ToolResult:
    """
    Kiểm tra tồn kho của một biến thể sản phẩm trước khi đổi size/màu.

    Args:
        product: Tên sản phẩm, ví dụ ``"Áo hoodie nỉ"``.
        size: Kích thước mong muốn, ví dụ ``"XL"``.
        color: Màu mong muốn, ví dụ ``"Đen"``.

    Returns:
        Dictionary dạng ``{"stock": int}``. Giá trị ``0`` có nghĩa là
        biến thể hiện hết hàng. Nếu đầu vào, biến thể hoặc nguồn dữ liệu
        có lỗi, kết quả chứa ``error`` và ``message``.

    Notes:
        Bắt buộc gọi tool này trước ``initiate_exchange_request``. Không được hứa
        đổi thành công nếu tồn kho bằng 0.
    """
    try:
        product_key = _normalize_key(product, "product")
        size_key = _normalize_key(size, "size")
        color_key = _normalize_key(color, "color")
        config = _load_lab_config()

        for inventory_item in config["mock_inventory"]:
            inventory_key = (
                str(inventory_item.get("product", "")).casefold(),
                str(inventory_item.get("size", "")).casefold(),
                str(inventory_item.get("color", "")).casefold(),
            )
            if inventory_key == (product_key, size_key, color_key):
                base_stock = int(inventory_item.get("stock", 0))
                reserved = _RESERVED_INVENTORY.get(inventory_key, 0)
                return {
                    "product": inventory_item.get("product"),
                    "size": inventory_item.get("size"),
                    "color": inventory_item.get("color"),
                    "stock": max(0, base_stock - reserved),
                }

        return _error(
            "INVENTORY_VARIANT_NOT_FOUND",
            "Không tìm thấy biến thể sản phẩm trong kho.",
            product=product.strip(),
            size=size.strip(),
            color=color.strip(),
        )
    except (TypeError, ValueError) as exc:
        return _error("INVALID_INPUT", str(exc))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        return _error(
            "DATA_SOURCE_ERROR",
            "Không thể đọc dữ liệu tồn kho lúc này.",
            detail=str(exc),
        )
    except Exception as exc:
        return _error(
            "INTERNAL_TOOL_ERROR",
            "Không thể kiểm tra tồn kho lúc này.",
            detail=str(exc),
        )


def initiate_return_request(
    order_id: str,
    item_id: str,
    reason: str,
    refund_method: str,
) -> ToolResult:
    """
    Khởi tạo yêu cầu trả hàng cho một sản phẩm đủ điều kiện.

    Chỉ gọi sau khi ``check_return_eligibility`` trả về đủ điều kiện và
    người dùng đã xác nhận muốn trả hàng cũng như phương thức hoàn tiền.

    Args:
        order_id: Mã đơn chứa sản phẩm cần trả.
        item_id: Mã sản phẩm cần trả.
        reason: Lý do trả hàng do người dùng cung cấp.
        refund_method: ``"original_payment"`` hoặc ``"store_credit"``.

    Returns:
        Dictionary dạng ``{"ticket_id": str, "status": str}`` khi tạo
        thành công. Mọi thất bại trả ``{"error": str, "message": str}``.

    Notes:
        Đây là tool làm thay đổi trạng thái. Agent không được gọi khi
        người dùng chưa xác nhận hoặc khi sản phẩm không đủ điều kiện.
        Lời gọi lặp cho cùng đơn và item trả lại ticket đã tạo.
    """
    try:
        normalized_order_id = _normalize_order_id(order_id)
        normalized_item_id = _normalize_item_id(item_id)
        normalized_reason = _required_text(reason, "reason")
        normalized_refund = _normalize_key(refund_method, "refund_method")
        request_key = (normalized_order_id, normalized_item_id)

        existing_request = _RETURN_REQUESTS.get(request_key)
        if existing_request is not None:
            result = deepcopy(existing_request)
            result["duplicate"] = True
            return result

        if request_key in _EXCHANGE_REQUESTS:
            return _error(
                "EXCHANGE_ALREADY_REQUESTED",
                "Sản phẩm đã có yêu cầu đổi hàng.",
            )

        eligibility = check_return_eligibility(
            normalized_order_id,
            normalized_item_id,
        )
        if "error" in eligibility:
            return eligibility
        if not eligibility.get("eligible"):
            reason_code = str(
                eligibility.get("reason_code", "NOT_ELIGIBLE")
            )
            return _error(
                reason_code,
                str(
                    eligibility.get(
                        "reason",
                        "Sản phẩm không đủ điều kiện trả hàng.",
                    )
                ),
            )

        allowed_refund_methods = {"original_payment", "store_credit"}
        if normalized_refund not in allowed_refund_methods:
            return _error(
                "INVALID_REFUND_METHOD",
                (
                    "Phương thức hoàn tiền phải là 'original_payment' "
                    "hoặc 'store_credit'."
                ),
            )

        required_refund = eligibility.get("refund_method")
        if required_refund and normalized_refund != required_refund:
            return _error(
                "REFUND_METHOD_NOT_ALLOWED",
                (
                    "Chính sách của sản phẩm yêu cầu phương thức hoàn tiền "
                    f"'{required_refund}'."
                ),
                required_refund_method=required_refund,
            )

        ticket = {
            "ticket_id": f"RET-{len(_RETURN_REQUESTS) + 1:04d}",
            "status": "created",
            "order_id": normalized_order_id,
            "item_id": normalized_item_id,
            "reason": normalized_reason,
            "refund_method": normalized_refund,
            "free_return_shipping": bool(
                eligibility.get("free_return_shipping", False)
            ),
        }
        _RETURN_REQUESTS[request_key] = deepcopy(ticket)
        return ticket
    except (TypeError, ValueError) as exc:
        return _error("INVALID_INPUT", str(exc))
    except Exception as exc:
        return _error(
            "INTERNAL_TOOL_ERROR",
            "Không thể tạo yêu cầu trả hàng lúc này.",
            detail=str(exc),
        )


def initiate_exchange_request(
    order_id: str,
    item_id: str,
    new_size: str,
    new_color: str,
) -> ToolResult:
    """
    Khởi tạo yêu cầu đổi size hoặc màu cho một sản phẩm đủ điều kiện.

    Chỉ gọi sau khi đã kiểm tra điều kiện đổi/trả, kiểm tra tồn kho biến
    thể đích và nhận được xác nhận rõ ràng từ người dùng.

    Args:
        order_id: Mã đơn chứa sản phẩm cần đổi.
        item_id: Mã sản phẩm cần đổi.
        new_size: Size người dùng muốn đổi sang.
        new_color: Màu người dùng muốn đổi sang.

    Returns:
        Dictionary dạng ``{"ticket_id": str, "status": str}`` khi tạo
        thành công. Mọi thất bại trả ``{"error": str, "message": str}``.

    Notes:
        Đây là tool làm thay đổi trạng thái. Không gọi nếu biến thể đích
        hết hàng hoặc người dùng chưa xác nhận. Lời gọi lặp cho cùng đơn
        và item trả lại ticket đã tạo.
    """
    try:
        normalized_order_id = _normalize_order_id(order_id)
        normalized_item_id = _normalize_item_id(item_id)
        normalized_size = _required_text(new_size, "new_size")
        normalized_color = _required_text(new_color, "new_color")
        request_key = (normalized_order_id, normalized_item_id)

        existing_request = _EXCHANGE_REQUESTS.get(request_key)
        if existing_request is not None:
            result = deepcopy(existing_request)
            result["duplicate"] = True
            return result

        if request_key in _RETURN_REQUESTS:
            return _error(
                "RETURN_ALREADY_REQUESTED",
                "Sản phẩm đã có yêu cầu trả hàng.",
            )

        eligibility = check_return_eligibility(
            normalized_order_id,
            normalized_item_id,
        )
        if "error" in eligibility:
            return eligibility
        if not eligibility.get("eligible"):
            reason_code = str(
                eligibility.get("reason_code", "NOT_ELIGIBLE")
            )
            return _error(
                reason_code,
                str(
                    eligibility.get(
                        "reason",
                        "Sản phẩm không đủ điều kiện đổi hàng.",
                    )
                ),
            )

        order_result = lookup_order(normalized_order_id)
        if "error" in order_result:
            return order_result
        item = _find_item(order_result, normalized_item_id)
        if item is None:
            return _error(
                "ITEM_NOT_FOUND",
                f"Không tìm thấy sản phẩm '{normalized_item_id}'.",
            )

        current_size = str(item.get("size", "")).casefold()
        current_color = str(item.get("color", "")).casefold()
        if (
            current_size == normalized_size.casefold()
            and current_color == normalized_color.casefold()
        ):
            return _error(
                "SAME_VARIANT",
                "Size và màu mới trùng với sản phẩm hiện tại.",
            )

        product = str(item.get("name", "")).strip()
        inventory = check_inventory(
            product,
            normalized_size,
            normalized_color,
        )
        if "error" in inventory:
            return inventory
        if int(inventory.get("stock", 0)) <= 0:
            return _error(
                "OUT_OF_STOCK",
                "Biến thể muốn đổi hiện đã hết hàng.",
                stock=0,
            )

        inventory_key = (
            product.casefold(),
            normalized_size.casefold(),
            normalized_color.casefold(),
        )
        _RESERVED_INVENTORY[inventory_key] = (
            _RESERVED_INVENTORY.get(inventory_key, 0) + 1
        )

        ticket = {
            "ticket_id": f"EXC-{len(_EXCHANGE_REQUESTS) + 1:04d}",
            "status": "created",
            "order_id": normalized_order_id,
            "item_id": normalized_item_id,
            "new_size": normalized_size,
            "new_color": normalized_color,
        }
        _EXCHANGE_REQUESTS[request_key] = deepcopy(ticket)
        return ticket
    except (TypeError, ValueError) as exc:
        return _error("INVALID_INPUT", str(exc))
    except Exception as exc:
        return _error(
            "INTERNAL_TOOL_ERROR",
            "Không thể tạo yêu cầu đổi hàng lúc này.",
            detail=str(exc),
        )


def get_return_policy(category: Optional[str] = None) -> ToolResult:
    """
    Tra cứu chính sách đổi/trả chung hoặc theo danh mục sản phẩm.

    Args:
        category: Danh mục cần tra cứu, ví dụ ``"đồ bơi"``. Bỏ trống để
            lấy chính sách chung.

    Returns:
        Dictionary chứa thời hạn đổi/trả, điều kiện sản phẩm, phương thức
        hoàn tiền và ngoại lệ. Mọi thất bại trả ``error`` và ``message``.

    Notes:
        Tool chỉ cung cấp chính sách; không xác định một sản phẩm cụ thể
        có đủ điều kiện hay không. Với trường hợp cụ thể, phải dùng
        ``check_return_eligibility``.
    """
    try:
        config = _load_lab_config()
        policy = deepcopy(config["meta"]["return_policy"])

        if category is None:
            policy["category"] = None
            policy["category_returnable"] = None
            return policy

        normalized_category = _normalize_key(category, "category")
        final_sale_categories = {
            str(value).casefold()
            for value in policy.get("final_sale_categories", [])
        }
        policy["category"] = category.strip()
        policy["category_returnable"] = (
            normalized_category not in final_sale_categories
        )
        if not policy["category_returnable"]:
            policy["category_note"] = (
                "Danh mục này là final sale vì lý do vệ sinh."
            )
        return policy
    except (TypeError, ValueError) as exc:
        return _error("INVALID_INPUT", str(exc))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        return _error(
            "DATA_SOURCE_ERROR",
            "Không thể đọc chính sách đổi/trả lúc này.",
            detail=str(exc),
        )
    except Exception as exc:
        return _error(
            "INTERNAL_TOOL_ERROR",
            "Không thể tra cứu chính sách đổi/trả lúc này.",
            detail=str(exc),
        )


# Mô tả ngắn dành cho Prompt Engineer và Core Developer khi tạo tool schema.
TOOL_SPECS = {
    "lookup_order": {
        "description": "Tra cứu trạng thái và các sản phẩm của một đơn hàng.",
        "required_args": ["order_id"],
        "read_only": True,
    },
    "lookup_orders_by_email": {
        "description": "Tìm các mã đơn khi khách hàng quên mã đơn.",
        "required_args": ["email"],
        "read_only": True,
    },
    "check_return_eligibility": {
        "description": "Kiểm tra điều kiện đổi/trả của một sản phẩm trong đơn.",
        "required_args": ["order_id", "item_id"],
        "read_only": True,
    },
    "check_inventory": {
        "description": "Kiểm tra tồn kho biến thể trước khi đổi size hoặc màu.",
        "required_args": ["product", "size", "color"],
        "read_only": True,
    },
    "initiate_return_request": {
        "description": "Tạo yêu cầu trả hàng sau khi đủ điều kiện và đã xác nhận.",
        "required_args": ["order_id", "item_id", "reason", "refund_method"],
        "read_only": False,
        "requires_confirmation": True,
    },
    "initiate_exchange_request": {
        "description": "Tạo yêu cầu đổi size/màu sau khi kiểm tra kho và xác nhận.",
        "required_args": ["order_id", "item_id", "new_size", "new_color"],
        "read_only": False,
        "requires_confirmation": True,
    },
    "get_return_policy": {
        "description": "Tra cứu chính sách đổi/trả chung hoặc theo danh mục.",
        "required_args": [],
        "optional_args": ["category"],
        "read_only": True,
    },
}


AVAILABLE_TOOLS = {
    "lookup_order": lookup_order,
    "lookup_orders_by_email": lookup_orders_by_email,
    "check_return_eligibility": check_return_eligibility,
    "check_inventory": check_inventory,
    "initiate_return_request": initiate_return_request,
    "initiate_exchange_request": initiate_exchange_request,
    "get_return_policy": get_return_policy,
}
