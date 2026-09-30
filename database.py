from datetime import datetime
from pathlib import Path
import re

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

Path("data").mkdir(exist_ok=True)

DATABASE_URL = "sqlite:///data/chatbot_memory.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String, unique=True, index=True)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String, index=True)
    role = Column(String)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class LongTermMemory(Base):
    __tablename__ = "long_term_memory"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String, index=True)
    memory = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def create_or_update_conversation(thread_id: str, first_message: str | None = None):
    db = SessionLocal()

    try:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.thread_id == thread_id)
            .first()
        )

        if not conversation:
            title = "New Chat"

            if first_message:
                title = first_message.strip()[:40]
                if len(first_message.strip()) > 40:
                    title += "..."

            conversation = Conversation(
                thread_id=thread_id,
                title=title,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            db.add(conversation)

        else:
            conversation.updated_at = datetime.utcnow()

        db.commit()

    finally:
        db.close()


def list_conversations():
    db = SessionLocal()

    try:
        return (
            db.query(Conversation)
            .order_by(Conversation.updated_at.desc())
            .all()
        )

    finally:
        db.close()


def delete_conversation_records(thread_id: str):
    db = SessionLocal()

    try:
        db.query(ChatMessage).filter(ChatMessage.thread_id == thread_id).delete(
            synchronize_session=False
        )
        db.query(LongTermMemory).filter(LongTermMemory.thread_id == thread_id).delete(
            synchronize_session=False
        )
        db.query(Conversation).filter(Conversation.thread_id == thread_id).delete(
            synchronize_session=False
        )
        db.commit()

    finally:
        db.close()


def save_chat_message(thread_id: str, role: str, content: str):
    db = SessionLocal()

    try:
        msg = ChatMessage(
            thread_id=thread_id,
            role=role,
            content=content,
            created_at=datetime.utcnow()
        )

        db.add(msg)

        conversation = (
            db.query(Conversation)
            .filter(Conversation.thread_id == thread_id)
            .first()
        )

        if conversation:
            conversation.updated_at = datetime.utcnow()

        db.commit()

    finally:
        db.close()


def get_chat_history(thread_id: str):
    db = SessionLocal()

    try:
        return (
            db.query(ChatMessage)
            .filter(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )

    finally:
        db.close()


def save_memory(thread_id: str, memory: str):
    db = SessionLocal()

    try:
        fact_key = _memory_fact_key(memory)
        if fact_key:
            existing = (
                db.query(LongTermMemory)
                .filter(LongTermMemory.thread_id == thread_id)
                .all()
            )
            matching = [
                item for item in existing
                if _memory_fact_key(item.memory) == fact_key
            ]

            if matching:
                current = max(matching, key=lambda item: item.created_at)
                current.memory = memory
                current.created_at = datetime.utcnow()
                for duplicate in matching:
                    if duplicate.id != current.id:
                        db.delete(duplicate)
                db.commit()
                return "Memory updated successfully."

        item = LongTermMemory(
            thread_id=thread_id,
            memory=memory,
            created_at=datetime.utcnow()
        )

        db.add(item)
        db.commit()

        return "Memory saved successfully."

    finally:
        db.close()


def _memory_fact_key(memory: str) -> str | None:
    match = re.search(
        r"\b(?:my|your|the user['’]s|user['’]s)\s+(.+?)\s+(?:is|are|=|:)\s+",
        memory,
        flags=re.IGNORECASE
    )
    if not match:
        match = re.match(r"^(.+?)\s*:\s*.+$", memory.strip())
    if not match:
        match = re.match(r"^(.+?)\s+(?:is|are|=)\s+.+$", memory.strip(), re.IGNORECASE)
    if not match:
        return None

    return " ".join(re.findall(r"[a-z0-9]+", match.group(1).lower())) or None


def search_memory(thread_id: str, query: str):
    db = SessionLocal()

    try:
        memories = (
            db.query(LongTermMemory)
            .filter(LongTermMemory.thread_id == thread_id)
            .order_by(LongTermMemory.created_at.desc())
            .limit(50)
            .all()
        )

        if not memories:
            return "No saved memory found."

        stop_words = {
            "what", "which", "who", "when", "where", "why", "how", "do",
            "does", "did", "you", "i", "me", "my", "mine", "is", "are",
            "was", "were", "the", "a", "an", "to", "about", "remember",
            "recall", "tell", "please", "earlier", "before"
        }
        query_terms = {
            term for term in re.findall(r"[a-z0-9]+", query.lower())
            if term not in stop_words
        }

        if query_terms:
            ranked = [
                (sum(term in item.memory.lower() for term in query_terms), item)
                for item in memories
            ]
            memories = [
                item for score, item in ranked
                if score > 0
            ]

            if not memories:
                return "No saved memory found for that topic."

        return "\n".join([f"- {item.memory}" for item in memories[:10]])

    finally:
        db.close()