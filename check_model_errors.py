from unittest.mock import patch  # 核心：打补丁，临时替换函数
from urllib.error import HTTPError, URLError  # 要模拟的异常类型

from fastapi import HTTPException  # 预期的"翻译结果"

from agent_service import get_reply_from_messages  # 被测函数

cases = [
    (TimeoutError("模拟超时"), 504),
    (URLError("模拟网络失败"), 502),
    (
        HTTPError(
            "https://example.invalid",
            401,
            "模拟认证失败",
            None,
            None,
        ),
        502,
    ),
]

for error, expected_status in cases:
    with patch("agent_service.call_api", side_effect=error):
        try:
            get_reply_from_messages([{"role": "user", "content": "测试"}])
        except HTTPException as response:
            assert response.status_code == expected_status
            print(response.status_code, response.detail)
        else:
            raise AssertionError("没有返回预期的异常")
