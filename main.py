from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from agent_service import get_agent_reply, get_reply_from_messages
from sqlalchemy import text
from database import engine
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

# Pydantic 是 Python 的数据校验库

app = FastAPI()


# 全局异常处理
@app.exception_handler(OperationalError)
async def handle_database_error(request, error):
    return JSONResponse(
        status_code=503,
        content={"detail": "数据库暂时不可用，请确认 MySQL 服务正在运行"},
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "project": "mini-agent-api",
    }


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


@app.post("/chat")
def chat(request: ChatRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="消息不能只包含空白字符",
        )

    reply = get_agent_reply(message)

    return {"reply": reply}


@app.get("/conversations")
def list_conversations(page: int = 1, page_size: int = 10):
    if page < 1:
        raise HTTPException(
            status_code=400,
            detail="页码必须大于等于 1",
        )

    if page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=400,
            detail="每页条数必须在 1 到 100 之间",
        )

    offset = (page - 1) * page_size

    with engine.connect() as connection:
        total = connection.execute(
            text("SELECT COUNT(*) FROM conversations")
        ).scalar_one()

        result = connection.execute(
            text(
                "SELECT id, title, created_at "
                "FROM conversations ORDER BY id "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": page_size, "offset": offset},
        )

        conversations = [dict(row) for row in result.mappings()]

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "conversations": conversations,
    }


class ConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)


@app.post("/conversations", status_code=201)
def create_conversation(request: ConversationCreate):
    title = request.title.strip()

    if not title:
        raise HTTPException(
            status_code=400,
            detail="会话标题不能只包含空白字符",
        )

    with engine.begin() as connection:
        result = connection.execute(
            text("INSERT INTO conversations (title) " "VALUES (:title)"),
            {"title": title},
        )

        conversation_id = result.lastrowid

    return {
        "id": conversation_id,
        "title": title,
    }


@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int):
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT id, title, created_at " "FROM conversations WHERE id = :id"),
            {"id": conversation_id},
        )

        conversation = result.mappings().first()  # first() 只取第一行

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="会话不存在",
            )

        return dict(conversation)


@app.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int):
    with engine.connect() as connection:
        conversation = connection.execute(
            text("SELECT id FROM conversations WHERE id = :id"),
            {"id": conversation_id},
        ).first()

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="会话不存在",
            )

        result = connection.execute(
            text(
                "SELECT id, conversation_id, role, content, created_at "
                "FROM messages "
                "WHERE conversation_id = :id "
                "ORDER BY id"
            ),
            {"id": conversation_id},
        )

        messages = [dict(row) for row in result.mappings()]

    return {"messages": messages}


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=100)


@app.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: int,
    request: ConversationUpdate,
):
    title = request.title.strip()

    if not title:
        raise HTTPException(
            status_code=400,
            detail="会话标题不能只包含空白字符",
        )

    with engine.begin() as connection:
        conversation = connection.execute(
            text("SELECT id FROM conversations " "WHERE id = :id FOR UPDATE"),
            {"id": conversation_id},
        ).first()
        # 加了 FOR UPDATE：请求A查的时候就把这行锁住，请求B必须等A的事务提交才能动它
        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="会话不存在",
            )

        connection.execute(
            text("UPDATE conversations " "SET title = :title WHERE id = :id"),
            {"title": title, "id": conversation_id},
        )

    return {"id": conversation_id, "title": title}


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: int):
    with engine.begin() as connection:
        conversation = connection.execute(
            text("SELECT id FROM conversations " "WHERE id = :id FOR UPDATE"),
            {"id": conversation_id},
        ).first()

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="会话不存在",
            )

        connection.execute(
            text("DELETE FROM messages " "WHERE conversation_id = :id"),
            {"id": conversation_id},
        )

        connection.execute(
            text("DELETE FROM conversations WHERE id = :id"),
            {"id": conversation_id},
        )

    return {"id": conversation_id, "deleted": True}


@app.post("/conversations/{conversation_id}/messages")
def send_message(conversation_id: int, request: ChatRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="消息不能只包含空白字符",
        )

    # 1. 检查会话，并读取历史
    with engine.connect() as connection:
        conversation = connection.execute(
            text("SELECT id FROM conversations WHERE id = :id"),
            {"id": conversation_id},
        ).first()

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="会话不存在",
            )

        result = connection.execute(
            text(
                "SELECT role, content FROM messages "
                "WHERE conversation_id = :id ORDER BY id"
            ),
            {"id": conversation_id},
        )

        history = [dict(row) for row in result.mappings()]

    # 2. 将历史和当前问题一起交给模型
    history.append({"role": "user", "content": message})

    reply = get_reply_from_messages(history)

    if not reply.strip():
        raise HTTPException(
            status_code=502,
            detail="模型没有返回有效回答",
        )

    # 3. 在一个事务中保存用户消息和模型回答
    with engine.begin() as connection:
        conversation = connection.execute(
            text("SELECT id FROM conversations " "WHERE id = :id FOR UPDATE"),
            {"id": conversation_id},
        ).first()

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="会话在生成回答期间已被删除",
            )

        connection.execute(
            text(
                "INSERT INTO messages "
                "(conversation_id, role, content) "
                "VALUES (:conversation_id, :role, :content)"
            ),
            [
                {
                    "conversation_id": conversation_id,
                    "role": "user",
                    "content": message,
                },
                {
                    "conversation_id": conversation_id,
                    "role": "assistant",
                    "content": reply,
                },
            ],
        )

    return {"conversation_id": conversation_id, "reply": reply}
