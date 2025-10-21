from fastapi import APIRouter, Depends, HTTPException
from beanie import PydanticObjectId
from typing import List
from datetime import datetime
from pydantic import BaseModel
from models import Message, User
from routers.auth import get_current_user
from beanie.operators import Or
from pymongo import DESCENDING

router = APIRouter(prefix="/messages", tags=["messages"])


# ==============================
# SCHEMA
# ==============================
class MessageCreate(BaseModel):
    receiver_id: str
    content: str


# ==============================
# CREATE MESSAGE
# ==============================
@router.post("/", response_model=Message)
async def send_message(
    data: MessageCreate,
    current_user: User = Depends(get_current_user)
):
    if data.receiver_id == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot send message to yourself")

    receiver = await User.get(PydanticObjectId(data.receiver_id))
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")

    message = Message(
        sender=current_user,
        receiver=receiver,
        content=data.content,
        created_at=datetime.utcnow()
    )
    await message.insert()
    return message


# ==============================
# GET ALL MESSAGES FOR CURRENT USER
# ==============================
@router.get("/", response_model=List[Message])
async def get_my_messages(current_user: User = Depends(get_current_user)):
    messages = await Message.find(
        {
            "$or": [
                {"sender.$id": current_user.id},
                {"receiver.$id": current_user.id}
            ]
        }
    ).sort("-created_at").to_list()
    return messages


# ==============================
# MARK AS READ
# ==============================
@router.put("/{message_id}/read")
async def mark_as_read(message_id: str, current_user: User = Depends(get_current_user)):
    message = await Message.get(PydanticObjectId(message_id))
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Fetch linked receiver
    receiver_doc = await message.receiver.fetch()

    if receiver_doc.id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to mark this message")

    message.is_read = True
    await message.save()
    return {"detail": "Message marked as read"}


# ==============================
# GET CONVERSATION BETWEEN TWO USERS
# ==============================

@router.get("/unread/count")
async def get_unread_count(current_user: User = Depends(get_current_user)):
    count = await Message.find({
        "receiver.$id": current_user.id,
        "is_read": False
    }).count()
    return {"unread_count": count}

@router.get("/inbox")
async def get_inbox(current_user: User = Depends(get_current_user)):
    # Fetch all messages where user is sender or receiver
    messages = await Message.find(
        Or(
            {"sender.$id": current_user.id},
            {"receiver.$id": current_user.id}
        )
    ).sort([("created_at", DESCENDING)]).to_list()

    conversations = {}
    for msg in messages:
        sender = await msg.sender.fetch()
        receiver = await msg.receiver.fetch()

        # Identify the "other" user in this conversation
        other_user = receiver if sender.id == current_user.id else sender
        other_user_id = str(other_user.id)

        # Only store the latest message per conversation
        if other_user_id not in conversations:
            conversations[other_user_id] = msg

    # Build inbox response
    inbox = []
    for user_id, last_msg in conversations.items():
        other_user = await User.get(PydanticObjectId(user_id))

        # Count unread messages from this user
        unread_count = await Message.find({
            "sender.$id": other_user.id,
            "receiver.$id": current_user.id,
            "is_read": False
        }).count()

        # Truncate message for preview (like WhatsApp)
        preview_text = (
            last_msg.content[:40] + "..."
            if len(last_msg.content) > 40
            else last_msg.content
        )

        inbox.append({
            "user_id": str(other_user.id),
            "user_name": f"{other_user.first_name} {other_user.last_name}",
            "preview": preview_text,
            "last_message": last_msg.content,
            "sent_by_me": (await last_msg.sender.fetch()).id == current_user.id,
            "timestamp": last_msg.created_at.isoformat(),
            "is_read": last_msg.is_read,
            "unread_count": unread_count
        })

    # Sort conversations by latest message timestamp
    inbox.sort(key=lambda x: x["timestamp"], reverse=True)
    return inbox

@router.get("/with/{other_user_id}")
async def get_conversation(
    other_user_id: str,
    current_user: User = Depends(get_current_user)
):
    other_user = await User.get(PydanticObjectId(other_user_id))
    if not other_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch all messages between the two users
    messages = await Message.find(
        Or(
            {"sender.$id": current_user.id, "receiver.$id": other_user.id},
            {"sender.$id": other_user.id, "receiver.$id": current_user.id}
        )
    ).sort("created_at").to_list()

    conversation = []
    for msg in messages:
        sender_doc = await msg.sender.fetch()
        receiver_doc = await msg.receiver.fetch()

        conversation.append({
            "id": str(msg.id),
            "content": msg.content,
            "sent_by_me": sender_doc.id == current_user.id,
            "is_read": msg.is_read,
            "created_at": msg.created_at.isoformat()
        })

    # Mark all received (unread) messages as read
    await Message.find(
        {"sender.$id": other_user.id, "receiver.$id": current_user.id, "is_read": False}
    ).update_many({"$set": {"is_read": True}})

    return {
        "other_user": {
            "id": str(other_user.id),
            "name": f"{other_user.first_name} {other_user.last_name}"
        },
        "messages": conversation
    }