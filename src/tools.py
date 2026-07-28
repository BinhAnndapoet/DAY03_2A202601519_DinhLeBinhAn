"""
Tool registry và đặc tả công cụ cho đề tài 5:
Trợ lý tra cứu đơn hàng và xử lý đổi/trả.

Mốc 2 chỉ chuẩn hóa tên tool, tham số, kiểu trả về và mô tả sử dụng.
Logic nghiệp vụ và xử lý lỗi sẽ được cài đặt ở Mốc 3.
"""

from typing import Any, Dict, List, Optional


ToolResult = Dict[str, Any]


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

        - Thành công: ``{"status": str, "delivery_date": str | None,
          "eta": str | None, "items": list, "customer_email": str,
          "is_gift": bool, "membership": str}``.
        - Không tìm thấy: ``{"error": "NOT_FOUND"}``.

    Notes:
        Tool chỉ tra cứu dữ liệu, không thay đổi trạng thái đơn hàng.
        Không được tự suy đoán dữ liệu khi mã đơn không tồn tại.
    """
    pass


def lookup_orders_by_email(email: str) -> List[str]:
    """
    Tìm các mã đơn hàng liên kết với email khách hàng.

    Dùng khi khách hàng quên mã đơn. Nếu tìm thấy nhiều đơn, Agent phải
    hiển thị danh sách ngắn gọn và yêu cầu người dùng chọn một đơn trước
    khi tiếp tục kiểm tra đổi/trả.

    Args:
        email: Email khách hàng, ví dụ ``"linh.pham@email.com"``.

    Returns:
        Danh sách mã đơn hàng. Trả về danh sách rỗng nếu email không có
        đơn hàng tương ứng.

    Notes:
        Tool không tự chọn đơn thay cho người dùng khi có nhiều kết quả.
    """
    pass


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
        Nếu đơn hoặc sản phẩm không tồn tại, kết quả chứa trường ``error``.

    Notes:
        Tool chỉ đánh giá theo dữ liệu hệ thống. Điều kiện như sản phẩm đã
        giặt, đã mặc hoặc mất tag phải được Agent làm rõ từ hội thoại.
        Tool không tự tạo yêu cầu đổi/trả.
    """
    pass


def check_inventory(product: str, size: str, color: str) -> ToolResult:
    """
    Kiểm tra tồn kho của một biến thể sản phẩm trước khi đổi size/màu.

    Args:
        product: Tên sản phẩm, ví dụ ``"Áo hoodie nỉ"``.
        size: Kích thước mong muốn, ví dụ ``"XL"``.
        color: Màu mong muốn, ví dụ ``"Đen"``.

    Returns:
        Dictionary dạng ``{"stock": int}``. Giá trị ``0`` có nghĩa là
        biến thể hiện hết hàng. Nếu sản phẩm hoặc biến thể không tồn tại,
        kết quả chứa trường ``error``.

    Notes:
        Bắt buộc gọi tool này trước ``initiate_exchange``. Không được hứa
        đổi thành công nếu tồn kho bằng 0.
    """
    pass


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
        refund_method: Phương thức hoàn tiền; dự kiến là
            ``"original_payment"`` hoặc ``"store_credit"``.

    Returns:
        Dictionary dạng ``{"ticket_id": str, "status": str}`` khi tạo
        thành công; nếu thất bại, kết quả chứa trường ``error``.

    Notes:
        Đây là tool làm thay đổi trạng thái. Agent không được gọi khi
        người dùng chưa xác nhận hoặc khi sản phẩm không đủ điều kiện.
    """
    pass


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
        thành công; nếu thất bại, kết quả chứa trường ``error``.

    Notes:
        Đây là tool làm thay đổi trạng thái. Không gọi nếu biến thể đích
        hết hàng hoặc người dùng chưa xác nhận.
    """
    pass


def get_return_policy(category: Optional[str] = None) -> ToolResult:
    """
    Tra cứu chính sách đổi/trả chung hoặc theo danh mục sản phẩm.

    Args:
        category: Danh mục cần tra cứu, ví dụ ``"đồ bơi"``. Bỏ trống để
            lấy chính sách chung.

    Returns:
        Dictionary chứa thời hạn đổi/trả, điều kiện sản phẩm, phương thức
        hoàn tiền và các ngoại lệ liên quan đến danh mục.

    Notes:
        Tool chỉ cung cấp chính sách; không xác định một sản phẩm cụ thể
        có đủ điều kiện hay không. Với trường hợp cụ thể, phải dùng
        ``check_return_eligibility``.
    """
    pass


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
        "description": "Tạo yêu cầu đổi size/màu sau khi kiểm tra tồn kho và xác nhận.",
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
