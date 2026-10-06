from mini_agent_1 import call_api
from urllib.error import HTTPError, URLError

from fastapi import HTTPException


def get_reply_from_messages(messages: list[dict]) -> str:
    try:
        response = call_api(messages)
    except HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail="模型服务返回错误，请检查密钥、额度或稍后重试",
        ) from error
    except TimeoutError as error:
        raise HTTPException(
            status_code=504,
            detail="模型请求超时，请稍后重试",
        ) from error
    except URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise HTTPException(
                status_code=504,
                detail="模型请求超时，请稍后重试",
            ) from error

        raise HTTPException(
            status_code=502,
            detail="无法连接模型服务，请检查网络或稍后重试",
        ) from error

    reply_parts = []

    for block in response.get("content", []):
        if block["type"] == "tool_use":
            raise HTTPException(
                status_code=502,
                detail="模型请求了工具调用，当前版本仅支持文本聊天",
            )

        if block["type"] == "text":
            reply_parts.append(block["text"])

    return "\n".join(reply_parts)


def get_agent_reply(message: str) -> str:
    messages = [{"role": "user", "content": message}]

    return get_reply_from_messages(messages)
