#!/usr/bin/env python3

import json
import os
import time
import subprocess
from pathlib import Path
import argparse

from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

load_dotenv()

BASE = "https://academicservices.iitbhu.ac.in"

COOKIES = {
    "sessionid": os.getenv("COOKIE_SESSIONID", ""),
    "csrftoken": os.getenv("COOKIE_CSRFTOKEN", ""),
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

session = requests.Session()
session.cookies.update(COOKIES)
session.headers.update(HEADERS)

def get_target_courses():
    """Load all course codes from the JSON files and record their source."""
    courses = {}
    for filename in ["courses.json", "courses-4thyr.json"]:
        p = Path(filename)
        if p.exists():
            try:
                db = json.loads(p.read_text())
                for code in db.keys():
                    courses[code] = filename
                print(f"Loaded {len(db)} courses from {filename}")
            except Exception as e:
                print(f"Error reading {filename}: {e}")
        else:
            print(f"Warning: {filename} not found.")
    return courses

def download_syllabus_pdf(download_url, course_code, output_dir):
    try:
        r = session.get(download_url, stream=True)
        r.raise_for_status()
        
        out_path = output_dir / f"{course_code}.pdf"
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True, out_path
    except Exception as e:
        print(f"    Failed to download PDF for {course_code}: {e}")
        return False, None

def main():
    parser = argparse.ArgumentParser(description="Map acad site IDs and download course PDFs.")
    parser.add_argument("--show", "-s", type=str, help="Open the PDF for a specific course code")
    parser.add_argument("--scan", action="store_true", help="Scan the acad site to build the ID mapping")
    parser.add_argument("--start", type=int, default=1, help="Start index for scanning (default: 1)")
    parser.add_argument("--end", type=int, default=2000, help="End index for scanning (default: 2000)")
    args = parser.parse_args()

    pdf_dir = Path("pdfs")
    pdf_dir.mkdir(exist_ok=True)

    if args.show:
        pdf_path = pdf_dir / f"{args.show}.pdf"
        if pdf_path.exists():
            print(f"Opening {pdf_path}...")
            if os.name == 'posix':
                subprocess.run(['xdg-open', str(pdf_path)])
            elif os.name == 'nt':
                os.startfile(str(pdf_path))
            else:
                subprocess.run(['open', str(pdf_path)])
        else:
            print(f"PDF for {args.show} not found. Please download it first.")
        return

    target_courses = get_target_courses()
    if not target_courses:
        print("No target courses found. Please ensure courses.json exists.")
        return

    map_file = Path("course_ids_map.json")
    course_ids = {}
    if map_file.exists():
        try:
            course_ids = json.loads(map_file.read_text())
            print(f"Loaded {len(course_ids)} mappings from {map_file.name}")
        except Exception as e:
            print(f"Error reading {map_file.name}: {e}")

    # PHASE 1: Scan and map IDs
    if args.scan:
        print(f"\n[PHASE 1] Scanning from {args.start} to {args.end} to build ID mapping...")
        for i in range(args.start, args.end + 1):
            detail_url = f"{BASE}/studnt_acad/subject_content_detail/{i}"
            
            try:
                r = session.get(detail_url, timeout=10)
                if r.status_code != 200:
                    continue
                
                # Check if we were redirected to a login page (e.g. ?next=...)
                if "?next=" in r.url or "/login" in r.url:
                    print("\n[!] ERROR: Session expired or invalid! You have been redirected to the login page.")
                    print("[!] Please update your COOKIE_SESSIONID and COOKIE_CSRFTOKEN in your .env file.")
                    break

                soup = BeautifulSoup(r.text, "html.parser")
                course_divs = soup.find_all("div", class_="h5")
                
                for div in course_divs:
                    if "text-secondary" in div.get("class", []):
                        text_content = div.get_text(strip=True)
                        if ":" in text_content:
                            course_code = text_content.split(":", 1)[0].strip()
                            if course_code not in course_ids:
                                print(f"  Found ID {i} -> {course_code}")
                                course_ids[course_code] = i
                                # Save incrementally
                                map_file.write_text(json.dumps(course_ids, indent=2))
                            break # Found the course code, no need to check other divs
            
            except requests.exceptions.RequestException as e:
                print(f"  [{i}] Request error: {e}")
            except Exception as e:
                print(f"  [{i}] Unexpected error: {e}")
                
            time.sleep(0.3)
        print("Done scanning.\n")
    elif not course_ids:
        print("\nNo ID mapping found! You should run with --scan first to build the map.")
        return

    # PHASE 2: Download PDFs based on targets
    print(f"\n[PHASE 2] Downloading PDFs for {len(target_courses)} target courses...")
    for code, source_file in target_courses.items():
        if code in course_ids:
            site_id = course_ids[code]
            pdf_path = pdf_dir / f"{code}.pdf"
            
            if pdf_path.exists():
                print(f"✓ {code} (from {source_file}): already downloaded.")
            else:
                print(f"Downloading PDF for {code} (ID: {site_id})...")
                download_url = f"{BASE}/studnt_acad/download_content/{site_id}"
                success, path = download_syllabus_pdf(download_url, code, pdf_dir)
                if success:
                    print(f"  -> Saved {code}.pdf")
                time.sleep(0.5)
        else:
            print(f"✗ {code} (from {source_file}): ID not found in mapping. (Need to --scan?)")

if __name__ == "__main__":
    main()
