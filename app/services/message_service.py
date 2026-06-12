from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.db_models import ChatMessageDB


async def append_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    display_content: str | None = None,
    is_context: bool = False,
    visible_in_history: bool = True,
    attachments: list | None = None,
) -> ChatMessageDB:
    result = await db.execute(
        select(func.coalesce(func.max(ChatMessageDB.seq), 0))
        .where(ChatMessageDB.session_id == session_id)
    )
    max_seq = result.scalar_one()
    msg = ChatMessageDB(
        session_id=session_id,
        seq=max_seq + 1,
        role=role,
        content=content,
        display_content=display_content,
        is_context=is_context,
        visible_in_history=visible_in_history,
        attachments=attachments,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def get_session_messages(db: AsyncSession, session_id: str) -> list[ChatMessageDB]:
    result = await db.execute(
        select(ChatMessageDB)
        .where(ChatMessageDB.session_id == session_id)
        .order_by(ChatMessageDB.seq)
    )
    return list(result.scalars().all())


async def append_context_messages(
    db: AsyncSession,
    session_id: str,
    context_messages: list[dict],
) -> list[ChatMessageDB]:
    result = await db.execute(
        select(func.coalesce(func.max(ChatMessageDB.seq), 0))
        .where(ChatMessageDB.session_id == session_id)
    )
    max_seq = result.scalar_one()

    db_msgs = []
    for i, msg in enumerate(context_messages):
        db_msg = ChatMessageDB(
            session_id=session_id,
            seq=max_seq + 1 + i,
            role=msg.get('role', 'system'),
            content=msg.get('content', ''),
            is_context=True,
            visible_in_history=msg.get('visible_in_history', True),
        )
        db.add(db_msg)
        db_msgs.append(db_msg)
    await db.commit()
    return db_msgs
