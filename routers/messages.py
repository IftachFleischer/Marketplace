# routers/messages.py
from datetime import datetime
from typing import List, Optional

from beanie import PydanticObjectId
from beanie.operators import Or
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from pymongo import DESCENDING

from models import Message, Product, User
from routers.auth import get_current_user

router = APIRouter(prefix="/messages", tags=["messages"])


# ==============================
# SCHEMA
# ==============================
class MessageCreate(BaseModel):
    receiver_id: str
    content: str
    product_id: Optional[str] = None  # optional: tie message to a listing


# ==============================
# HELPERS
# ==============================
async def _product_seller_id(product: Product) -> Optional[str]:
    """
    Normalize the seller id from a Product.seller link or various stored shapes.
    """
    s = product.seller
    # Link[User]
    try:
        if hasattr(s, "fetch"):
            doc = await s.fetch()
            return str(doc.id)
    except Exception:
        pass

    # Dict shapes
    if isinstance(s, dict):
        if "id" in s:
            return str(s["id"])
        if "$id" in s:
            sid = s["$id"]
            if isinstance(sid, dict) and "$oid" in sid:
                return str(sid["$oid"])
            return str(sid)

    # Raw string id
    if isinstance(s, str):
        return s

    return None


# ==============================
# CREATE MESSAGE
# ==============================
@router.post("/", response_model=Message)
async def send_message(
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
):
    if data.receiver_id == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot send message to yourself")

    # Validate receiver
    try:
        receiver_oid = PydanticObjectId(data.receiver_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid receiver ID")
    receiver = await User.get(receiver_oid)
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")

    # Optional product tie-in
    product_doc = None
    if data.product_id:
        try:
            pid = PydanticObjectId(data.product_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid product ID")
        product_doc = await Product.get(pid)
        if not product_doc:
            raise HTTPException(status_code=404, detail="Product not found")

        # If the item is SOLD, block new buyer messages (seller can still follow up)
        if product_doc.is_sold:
            seller_id = await _product_seller_id(product_doc)
            if str(current_user.id) != str(seller_id):
                raise HTTPException(
                    status_code=400,
                    detail="This item has been sold. Messaging is closed.",
                )

    message = Message(
        sender=current_user,
        receiver=receiver,
        content=data.content,
        product=product_doc,
        created_at=datetime.utcnow(),
    )
    await message.insert()
    return message


# ==============================
# GET ALL MESSAGES FOR CURRENT USER (raw stream)
# ==============================
@router.get("/", response_model=List[Message])
async def get_my_messages(current_user: User = Depends(get_current_user)):
    messages = await Message.find(
        {
            "$or": [
                {"sender.$id": current_user.id},
                {"receiver.$id": current_user.id},
            ]
        }
    ).sort("-created_at").to_list()
    return messages


# ==============================
# UNREAD COUNT (overall)
# ==============================
@router.get("/unread/count")
async def get_unread_count(current_user: User = Depends(get_current_user)):
    count = await Message.find(
        {"receiver.$id": current_user.id, "is_read": False}
    ).count()
    return {"unread_count": count}


# ==============================
# INBOX — one row per (other user, product)
# ==============================
@router.get("/inbox")
async def get_inbox(current_user: User = Depends(get_current_user)):
    # Grab all messages involving me, newest first
    messages = (
        await Message.find(
            Or({"sender.$id": current_user.id}, {"receiver.$id": current_user.id})
        )
        .sort([("created_at", DESCENDING)])
        .to_list()
    )

    conversations = {}
    for msg in messages:
        # Resolve sender/receiver
        sender = await msg.sender.fetch()
        receiver = await msg.receiver.fetch()
        other_user = receiver if sender.id == current_user.id else sender
        other_user_id = str(other_user.id)

        # Resolve product (if any)
        product_doc = await msg.product.fetch() if msg.product else None
        product_id = str(product_doc.id) if product_doc else None

        # Build a key: one conversation per (other_user, product or no_product)
        key = f"{other_user_id}::{product_id or 'no_product'}"
        if key not in conversations:
            preview_text = msg.content[:40] + "..." if len(msg.content) > 40 else msg.content

            # Count unread for this thread (from other -> me, same product context)
            unread_filter = {
                "sender.$id": other_user.id,
                "receiver.$id": current_user.id,
                "is_read": False,
            }
            if product_doc:
                unread_filter["product.$id"] = product_doc.id
            else:
                unread_filter["product"] = None
            unread_count = await Message.find(unread_filter).count()

            conversations[key] = {
                "user_id": other_user_id,
                "user_name": f"{other_user.first_name} {other_user.last_name}",
                "preview": preview_text,
                "last_message": msg.content,
                "sent_by_me": sender.id == current_user.id,
                "timestamp": msg.created_at.isoformat(),
                "is_read": msg.is_read,
                "unread_count": unread_count,
                # Product context for richer inbox UI
                "product_id": product_id,
                "product_name": product_doc.product_name if product_doc else None,
                "product_is_sold": bool(product_doc.is_sold) if product_doc else None,
                "product_price_usd": product_doc.price_usd if product_doc else None,
                "product_image": (
                    (product_doc.images or [None])[0] if product_doc else None
                ),
            }

    # Latest first
    inbox = sorted(conversations.values(), key=lambda x: x["timestamp"], reverse=True)
    return inbox


# ==============================
# CONVERSATION (with optional product filter)
# ==============================
@router.get("/with/{other_user_id}")
async def get_conversation(
    other_user_id: str,
    product_id: Optional[str] = Query(default=None, alias="product_id"),
    current_user: User = Depends(get_current_user),
):
    # Validate other user
    try:
        other_oid = PydanticObjectId(other_user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    other_user = await User.get(other_oid)
    if not other_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Optional product filter
    product_doc = None
    if product_id:
        try:
            pid = PydanticObjectId(product_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid product ID")
        product_doc = await Product.get(pid)
        if not product_doc:
            raise HTTPException(status_code=404, detail="Product not found")

    # Build query: both directions, optional product match
    base = Or(
        {"sender.$id": current_user.id, "receiver.$id": other_user.id},
        {"sender.$id": other_user.id, "receiver.$id": current_user.id},
    )
    prod_filter = {"product.$id": product_doc.id} if product_doc else {"product": None}

    messages = (
        await Message.find({"$and": [base, prod_filter]})
        .sort("created_at")
        .to_list()
    )

    # Serialize thread
    conversation = []
    for msg in messages:
        sender_doc = await msg.sender.fetch()
        conversation.append(
            {
                "id": str(msg.id),
                "content": msg.content,
                "sent_by_me": sender_doc.id == current_user.id,
                "is_read": msg.is_read,
                "created_at": msg.created_at.isoformat(),
            }
        )

    # Mark received as read for this thread
    await Message.find(
        {"sender.$id": other_user.id, "receiver.$id": current_user.id, **prod_filter}
    ).update_many({"$set": {"is_read": True}})

    return {
        "other_user": {
            "id": str(other_user.id),
            "name": f"{other_user.first_name} {other_user.last_name}",
        },
        "product": (
            {
                "id": str(product_doc.id),
                "name": product_doc.product_name,
                "is_sold": bool(product_doc.is_sold),
                "price_usd": product_doc.price_usd,
                "image": (product_doc.images or [None])[0],
            }
            if product_doc
            else None
        ),
        "messages": conversation,
    }
