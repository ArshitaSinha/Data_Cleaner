import requests
import re
import uuid
from urllib.parse import urlparse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from database import get_db, init_db
import os
import hashlib
import zipfile
import shutil
import csv
import io
from pathlib import Path

app = FastAPI()

# Make sure the folder exists BEFORE we try to mount it
os.makedirs("uploads", exist_ok=True) 

# Allow our frontend to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the uploads folder so the frontend can display the images
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Ensure database exists on startup
@app.on_event("startup")
def startup_event():
    init_db()

def calculate_file_hash(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        # Read in chunks for memory efficiency
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

@app.get("/")
def read_root():
    return {"message": "Dataset Cleaner API is running!"}

@app.get("/images")
def get_images():
    conn = get_db()
    images = conn.execute("SELECT * FROM images").fetchall()
    conn.close()
    return [dict(ix) for ix in images]

@app.post("/upload/zip")
async def upload_zip(file: UploadFile = File(...)):
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only .zip files are allowed")
        
    # 1. Save the incoming zip locally first
    temp_zip_path = f"temp_{file.filename}"
    with open(temp_zip_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    extracted_count = 0
    duplicate_count = 0
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 2. Open and read the zip
        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                # Skip folders and hidden files
                if member.endswith('/') or not member.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                    continue
                    
                # 3. Extract and flatten the image directly into our uploads folder
                filename = os.path.basename(member)
                extracted_path = os.path.join("uploads", filename)
                
                with zip_ref.open(member) as source, open(extracted_path, "wb") as target:
                    shutil.copyfileobj(source, target)
                    
                file_size_kb = os.path.getsize(extracted_path) / 1024
                
                # 4. The Duplicate Check
                file_hash = calculate_file_hash(extracted_path)
                existing = cursor.execute("SELECT id FROM images WHERE file_hash = ?", (file_hash,)).fetchone()
                
                if existing:
                    duplicate_count += 1
                    os.remove(extracted_path)
                else:
                    # 5. It's new! Save metadata to the database
                    cursor.execute('''
                        INSERT INTO images (filename, file_type, size_kb, file_hash, status)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (filename, filename.split('.')[-1], file_size_kb, file_hash, 'needs_review'))
                    extracted_count += 1
                    
        # 6. Log the operation
        cursor.execute('''
            INSERT INTO logs (action, details) VALUES (?, ?)
        ''', ('import_zip', f"Imported {extracted_count} images. Found/ignored {duplicate_count} exact duplicates."))
        conn.commit()
        
    finally:
        conn.close()
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
            
    return {
        "message": "Upload complete", 
        "extracted_new_images": extracted_count, 
        "duplicates_ignored": duplicate_count
    }

class StatusUpdate(BaseModel):
    status: str

class ScrapeRequest(BaseModel):
    text: str

@app.post("/scrape")
def scrape_images(request: ScrapeRequest):
    # 1. Regex to find all valid image URLs (http/https ending in jpg/png/gif/webp)
    url_pattern = r'https?://[^\s<>"\']+?\.(?:jpg|jpeg|png|gif|webp)'
    found_urls = re.findall(url_pattern, request.text, re.IGNORECASE)
    
    # Remove exact duplicate URLs from the pasted text to save time
    unique_urls = list(set(found_urls))
    
    extracted_count = 0
    duplicate_count = 0
    failed_count = 0
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        for url in unique_urls:
            try:
                # 2. Download the image safely with a timeout
                response = requests.get(url, stream=True, timeout=5)
                if response.status_code == 200:
                    
                    # 3. Create a unique, safe filename
                    parsed_url = urlparse(url)
                    original_name = os.path.basename(parsed_url.path)
                    if not original_name:
                        original_name = f"scraped_{uuid.uuid4().hex[:8]}.jpg"
                        
                    safe_filename = f"{uuid.uuid4().hex[:4]}_{original_name}"
                    extracted_path = os.path.join("uploads", safe_filename)
                    
                    # Save to hard drive
                    with open(extracted_path, 'wb') as f:
                        for chunk in response.iter_content(1024):
                            f.write(chunk)
                            
                    file_size_kb = os.path.getsize(extracted_path) / 1024
                    
                    # 4. Run our Duplicate Hash Check!
                    file_hash = calculate_file_hash(extracted_path)
                    existing = cursor.execute("SELECT id FROM images WHERE file_hash = ?", (file_hash,)).fetchone()
                    
                    if existing:
                        duplicate_count += 1
                        os.remove(extracted_path)
                    else:
                        # 5. Save metadata to DB
                        cursor.execute('''
                            INSERT INTO images (filename, source_url, file_type, size_kb, file_hash, status)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (safe_filename, url, safe_filename.split('.')[-1], file_size_kb, file_hash, 'needs_review'))
                        extracted_count += 1
                else:
                    failed_count += 1
            except Exception:
                failed_count += 1 # Catch bad URLs or timeouts

        # 6. Log the scrape action
        cursor.execute('''
            INSERT INTO logs (action, details) VALUES (?, ?)
        ''', ('scrape_urls', f"Scraped {extracted_count} new images. {duplicate_count} dupes, {failed_count} failed."))
        conn.commit()
        
    finally:
        conn.close()
        
    return {
        "message": "Scraping complete",
        "extracted_new_images": extracted_count,
        "duplicates_ignored": duplicate_count,
        "failed_urls": failed_count,
        "total_found_urls": len(unique_urls)
    }

@app.patch("/images/{image_id}")
def update_status(image_id: int, update_data: StatusUpdate):
    if update_data.status not in ['keep', 'reject', 'needs_review']:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE images SET status = ? WHERE id = ?", (update_data.status, image_id))
    
    cursor.execute('''
        INSERT INTO logs (action, details) VALUES (?, ?)
    ''', ('update_status', f"Image ID {image_id} marked as {update_data.status}"))
    
    conn.commit()
    conn.close()
    
    return {"message": "Status updated successfully"}

@app.get("/export")
def export_csv():
    conn = get_db()
    images = conn.execute("SELECT filename, source_url, file_type, size_kb, status, tags, file_hash FROM images").fetchall()
    
    cursor = conn.cursor()
    cursor.execute("INSERT INTO logs (action, details) VALUES (?, ?)", ('export', f"Exported {len(images)} records to CSV."))
    conn.commit()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Filename", "Source URL", "File Type", "Size (KB)", "Status", "Tags", "File Hash"])

    for img in images:
        writer.writerow(img)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=dataset_metadata.csv"}
    )