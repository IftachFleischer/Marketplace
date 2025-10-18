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
@router.get("/with/{other_user_id}", response_model=List[Message])
async def get_conversation(
    other_user_id: str,
    current_user: User = Depends(get_current_user)
):
    # Verify the other user exists
    other_user = await User.get(PydanticObjectId(other_user_id))
    if not other_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find all messages between the two users (both directions)
    messages = await Message.find(
        {
            "$or": [
                {
                    "$and": [
                        {"sender.$id": current_user.id},
                        {"receiver.$id": other_user.id}
                    ]
                },
                {
                    "$and": [
                        {"sender.$id": other_user.id},
                        {"receiver.$id": current_user.id}
                    ]
                },
            ]
        }
    ).sort("created_at").to_list()

    return messages

@router.get("/unread/count")
async def get_unread_count(current_user: User = Depends(get_current_user)):
    count = await Message.find({
        "receiver.$id": current_user.id,
        "is_read": False
    }).count()
    return {"unread_count": count}

@router.get("/inbox")
async def get_inbox(current_user: User = Depends(get_current_user)):
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

        other_user_id = receiver.id if sender.id == current_user.id else sender.id
        if str(other_user_id) not in conversations:
            conversations[str(other_user_id)] = msg

    result = []
    for user_id, last_msg in conversations.items():
        other_user = await User.get(PydanticObjectId(user_id))
        unread_count = await Message.find({
            "sender.$id": other_user.id,
            "receiver.$id": current_user.id,
            "is_read": False
        }).count()

        result.append({
            "user_id": str(other_user.id),
            "user_name": f"{other_user.first_name} {other_user.last_name}",
            "last_message": last_msg.content,
            "sent_by_me": (await last_msg.sender.fetch()).id == current_user.id,
            "created_at": last_msg.created_at,
            "is_read": last_msg.is_read,
            "unread_count": unread_count
        })

    result.sort(key=lambda x: x["created_at"], reverse=True)
    return result