# Image Dataset Cleaner & Review Tool

A fast, local, full-stack internal tool designed to ingest, review, and export image datasets. Built as a streamlined solution for data review pipelines, it allows users to import images via `.zip` or URL scraping, manually review and tag them, automatically filter out exact duplicates, and export the final metadata to CSV.

## Features Implemented
* **Core Requirements:** Zip upload ingestion, visual gallery review, manual status tagging (Keep/Reject/Needs Review), local session persistence via SQLite, and CSV export.
* **Bonus - Exact Duplicate Detection:** Uses SHA-256 file hashing to automatically identify and ignore duplicate files during ingestion to save disk space.
* **Bonus - URL/HTML Scraping:** A built-in regex-powered extractor that accepts raw HTML or lists of URLs, safely downloads the images, and adds them to the review queue with graceful timeout handling.
* **Bonus - UI Filters:** Real-time dropdown filtering to sort the gallery by review status.
* **Bonus - Dockerized:** Fully containerized for instant deployment without local environment configuration.

## Tech Stack
* **Backend:** Python, FastAPI (for async routing and file handling)
* **Database:** SQLite (Requires zero setup, writes to `review_session.db`)
* **Frontend:** Vanilla HTML/JavaScript, Tailwind CSS (via CDN)
* **Deployment:** Docker & Docker Compose

---

## Setup & Installation

You can run this project either using Docker (Recommended) or locally via Python.

### Option A: Using Docker (Recommended)
Make sure you have Docker Desktop installed and running.
1. Open your terminal in the root folder of this project.
2. Run the following command:
   ```bash
   docker compose up --build
3. Open your browser and navigate to the index.html file on your local machine to use the UI.

### Option B: Local Manual Setup (Windows/Mac/Linux)
Requires Python 3.10+.

1. Open your terminal in the root folder.
2. Create and activate a virtual environment:
    ```bash
    python -m venv .venv
    # Windows:
    .\.venv\Scripts\activate
    # Mac/Linux:
    source .venv/bin/activate
3. Install dependencies:
    ```bash
    pip install -r requirements.txt
4. Start the FastAPI backend server:
    ```bash
    python -m uvicorn main:app --reload
5. Open the index.html file directly in your web browser.

---

## How to Use
1. Ingest Data: Use the blue Upload Zip button to import a local .zip file containing images, or paste a list of image URLs into the purple Extract Links box.
2. Review: Click Keep or Reject on the image cards. The borders will change color to indicate their status.
3. Filter: Use the dropdown menu in the header to view only specific statuses.
4. Export: Click the dark Export CSV button to download the finalized dataset metadata.
### (Note: You can safely refresh the page or restart the server; your session is automatically saved to the SQLite database).

---

## Known Limitations
To maintain transparency, here are the current limitations of the tool:
* **Scraper Scope:** The URL extractor uses Regex to find standard image extensions (`.jpg`, `.png`, `.webp`, `.gif`). It does not execute JavaScript, so it cannot bypass bot-protection or scrape images dynamically loaded via modern SPA frameworks (e.g., React/Vue background images).
* **Perceptual Hashing:** The tool currently detects *exact* file duplicates using SHA-256 byte hashing. It does not use perceptual hashing (pHash) for near-duplicates (e.g., the same image resized by 1 pixel).
* **Zip File Size:** For extremely large datasets (1GB+), the synchronous local extraction might briefly hang the backend. A production version would offload extraction to a background worker (like Celery).