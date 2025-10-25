# routers/uploads.py
import os
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
import cloudinary
import cloudinary.uploader
from routers.auth import get_current_user
from models import User

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 5 * 1024 * 1024  # 5MB
MAX_FILES = 5

def ensure_cloudinary_config():
    cfg = cloudinary.config(cloud_name=None)
    if not cfg.cloud_name or not cfg.api_key:
        cloudinary.config(
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
            api_key=os.getenv("CLOUDINARY_API_KEY"),
            api_secret=os.getenv("CLOUDINARY_API_SECRET"),
            secure=True,
        )
    if not os.getenv("CLOUDINARY_API_KEY"):
        raise HTTPException(status_code=500, detail="Cloudinary API key not loaded from env")

@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    ensure_cloudinary_config()
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 5MB)")
    await file.seek(0)

    folder = os.getenv("CLOUDINARY_FOLDER", "marketplace")
    try:
        res = cloudinary.uploader.upload(file.file, folder=folder, resource_type="image", overwrite=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    return {"url": res.get("secure_url"), "public_id": res.get("public_id")}

@router.post("/images")
async def upload_images(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user)
):
    ensure_cloudinary_config()
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES} images")

    folder = os.getenv("CLOUDINARY_FOLDER", "marketplace")
    urls = []
    for f in files:
        if f.content_type not in ALLOWED_MIME:
            raise HTTPException(status_code=400, detail=f"Unsupported type: {f.content_type}")
        data = await f.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"Image too large: {f.filename}")
        await f.seek(0)

        try:
            res = cloudinary.uploader.upload(f.file, folder=folder, resource_type="image", overwrite=False)
            urls.append({"url": res.get("secure_url"), "public_id": res.get("public_id")})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload failed for {f.filename}: {e}")

    return {"items": urls}
