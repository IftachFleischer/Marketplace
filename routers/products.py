# routers/products.py
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from beanie import PydanticObjectId

from models import Product, User, ProductCreate
from routers.auth import get_current_user

router = APIRouter(prefix="/products", tags=["products"])


# --- Helpers -----------------------------------------------------------------
async def _extract_seller_id(product: Product) -> Optional[str]:
    """
    Normalize the seller id across possible shapes:
    - Beanie Link(User)  -> fetch() and read doc.id
    - {"id": ObjectId}   -> str(value)
    - {"$id": ...}       -> DBRef-like; supports {"$oid": "..."} as well
    - "string_id"        -> as-is
    Returns the seller id as a string, or None if it cannot be determined.
    """
    s = product.seller

    # Link[User] (Beanie)
    try:
        if hasattr(s, "fetch"):
            doc = await s.fetch()
            return str(doc.id)
    except Exception:
        pass

    # Dict-like shapes
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


# --- Routes ------------------------------------------------------------------
# GET - Public route (no auth required)
@router.get("/", response_model=list[Product])
async def get_products():
    return await Product.find_all().to_list()


# GET single product - Public
@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str):
    try:
        oid = PydanticObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    product = await Product.get(oid)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# CREATE - Protected
@router.post("/", response_model=Product, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_user),
):
    # --- validate images (before insert) ---
    images = product_data.images or []
    if not isinstance(images, list):
        raise HTTPException(status_code=400, detail="'images' must be a list of URLs")
    if len(images) > 5:
        raise HTTPException(status_code=400, detail="Up to 5 images allowed")

    # Coerce price to float (Product model uses int, but your ProductCreate uses float)
    # Keep as-is if you intentionally want an int in the DB.
    price = float(product_data.price_usd)

    product = Product(
        product_name=product_data.product_name,
        product_description=product_data.product_description,
        price_usd=price,
        category=product_data.category,
        brand=product_data.brand,
        images=images,
        size=product_data.size,
        seller={"id": current_user.id, "collection": "users"},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    await product.insert()
    return product


# UPDATE - Protected (only seller or admin)
@router.put("/{product_id}", response_model=Product)
async def update_product(
    product_id: str,
    update_data: dict,
    current_user: User = Depends(get_current_user),
):
    try:
        oid = PydanticObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    product = await Product.get(oid)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    seller_id = await _extract_seller_id(product)
    if str(seller_id) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if "images" in update_data:
        imgs = update_data.get("images") or []
        if not isinstance(imgs, list):
            raise HTTPException(status_code=400, detail="'images' must be a list of URLs")
        if len(imgs) > 5:
            raise HTTPException(status_code=400, detail="Up to 5 images allowed")

    # Whitelist fields that can be updated via this endpoint
    ALLOWED_FIELDS = {
        "product_name",
        "product_description",
        "price_usd",
        "category",
        "brand",
        "images",
        "stock_quantity",
        "is_sold",
        "size",
    }
    safe_update = {k: v for k, v in update_data.items() if k in ALLOWED_FIELDS}
    safe_update["updated_at"] = datetime.utcnow()

    if not safe_update:
        return product

    await product.set(safe_update)
    return product


# DELETE - Protected (only seller or admin)
@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
):
    try:
        oid = PydanticObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    product = await Product.get(oid)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    seller_id = await _extract_seller_id(product)
    if str(seller_id) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    await product.delete()
    return {"detail": "Product deleted"}


# PATCH mark as SOLD (idempotent)
@router.patch("/{product_id}/mark_sold", response_model=Product)
async def mark_product_sold(
    product_id: str,
    current_user: User = Depends(get_current_user),
):
    try:
        oid = PydanticObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    product = await Product.get(oid)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    seller_id = await _extract_seller_id(product)
    if str(seller_id) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if product.is_sold:
        return product  # idempotent

    await product.set({
        "is_sold": True,
        "stock_quantity": 0,
        "updated_at": datetime.utcnow(),
    })
    return product
