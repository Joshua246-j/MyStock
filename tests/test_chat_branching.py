import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import ChatMessage, ChatSession
from app.services.chat import ChatService


@pytest.fixture
def chat_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        yield db
    engine.dispose()


def test_branch_copies_context_through_selected_assistant_reply(chat_db):
    parent = ChatSession(session_id="parent", document_ids=[12, 18], dataset_id=25)
    chat_db.add(parent)
    chat_db.flush()
    rows = [
        ChatMessage(session_id="parent", role="user", content="Analyze AAPL"),
        ChatMessage(session_id="parent", role="assistant", content="AAPL evidence summary", sources=["Market provider"]),
        ChatMessage(session_id="parent", role="user", content="What about its risks?"),
        ChatMessage(session_id="parent", role="assistant", content="Risk summary", sources=["10-K, page 8"]),
        ChatMessage(session_id="parent", role="user", content="A later question"),
    ]
    chat_db.add_all(rows)
    chat_db.commit()
    anchor_id = rows[3].id

    branch = ChatService(chat_db).branch_session("parent", anchor_id)

    assert branch["parent_session_id"] == "parent"
    branch_session = chat_db.query(ChatSession).filter_by(session_id=branch["session_id"]).one()
    assert branch_session.branch_from_message_id == anchor_id
    assert branch_session.document_ids == [12, 18]
    assert branch_session.dataset_id == 25
    branch_data = ChatService(chat_db).get_session(branch["session_id"])
    assert branch_data["document_ids"] == [12, 18]
    assert branch_data["dataset_id"] == 25
    assert [message["content"] for message in branch_data["messages"]] == [
        "Analyze AAPL", "AAPL evidence summary", "What about its risks?", "Risk summary",
    ]
    assert branch_data["messages"][-1]["sources"] == ["10-K, page 8"]
    assert ChatService(chat_db).list_sessions()[0]["is_branch"] is True


def test_branch_rejects_failed_or_foreign_reply(chat_db):
    chat_db.add_all([ChatSession(session_id="one"), ChatSession(session_id="two")])
    chat_db.flush()
    failed = ChatMessage(session_id="one", role="assistant", content="Error: Could not connect to Ollama")
    foreign = ChatMessage(session_id="two", role="assistant", content="Valid reply")
    chat_db.add_all([failed, foreign])
    chat_db.commit()

    with pytest.raises(ValueError, match="failed response"):
        ChatService(chat_db).branch_session("one", failed.id)
    with pytest.raises(ValueError, match="message in this conversation"):
        ChatService(chat_db).branch_session("one", foreign.id)


def test_branch_can_start_at_user_message_and_survives_parent_delete(chat_db):
    chat_db.add(ChatSession(session_id="parent", document_ids=[7], dataset_id=9))
    chat_db.flush()
    first = ChatMessage(session_id="parent", role="user", content="Compare AAPL and MSFT")
    first_content = first.content
    later = ChatMessage(session_id="parent", role="assistant", content="AAPL and MSFT comparison")
    chat_db.add_all([first, later])
    chat_db.commit()

    service = ChatService(chat_db)
    branch = service.branch_session("parent", first.id)
    assert [item["content"] for item in service.get_session(branch["session_id"])["messages"]] == [first.content]
    assert service.delete_session("parent") is True
    branch_row = chat_db.query(ChatSession).filter_by(session_id=branch["session_id"]).one()
    assert branch_row.parent_session_id is None
    assert branch_row.branch_from_message_id is None
    assert service.get_session(branch["session_id"])["messages"][0]["content"] == first_content
