#!/usr/bin/env python3

import json
import os
import time
import difflib
from pathlib import Path

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


def get_csrf():
    r = session.get(f"{BASE}/studnt_acad/subj_search")
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    return soup.find("input", {"name": "csrfmiddlewaretoken"})["value"]


def get_oe_courses():

    r = session.get(f"{BASE}/studnt_acad/subj_chcs/OE")
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    courses = {}

    for li in soup.select("li[data-code]"):
        code = li["data-code"]

        text = li.find("span").get_text(" ", strip=True)

        _, rest = text.split(".", 1)

        code2, name = rest.split(":", 1)

        courses[code2.strip()] = name.strip()

    return courses


def search_course(code):

    csrf = get_csrf()

    r = session.post(
        f"{BASE}/studnt_acad/subj_search",
        data={
            "csrfmiddlewaretoken": csrf,
            "search": code,
            "year_sem": "All",
            "dept": "All",
        },
        headers={"Referer": f"{BASE}/studnt_acad/subj_search"},
    )

    r.raise_for_status()

    return r.text


def choose_subject(info_rows, oe_name):

    # exact
    for row in info_rows:
        if row["name"].casefold() == oe_name.casefold():
            return row

    # fuzzy
    names = [r["name"] for r in info_rows]

    match = difflib.get_close_matches(
        oe_name,
        names,
        n=1,
        cutoff=0.85,
    )

    if match:
        return next(r for r in info_rows if r["name"] == match[0])

    print(f"WARNING: couldn't match '{oe_name}', using first row.")

    return info_rows[0]


def parse_course(html, oe_name):

    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")

    if len(tables) < 2:
        raise RuntimeError("Unexpected page layout")

    info_rows = []

    for tr in tables[0].tbody.find_all("tr"):
        td = [x.get_text(" ", strip=True) for x in tr.find_all("td")]

        info_rows.append(
            {
                "code": td[0],
                "name": td[1],
                "credits": td[2],
                "ltp": td[3],
                "department": td[4],
                "professor": td[5],
            }
        )

    subject = choose_subject(info_rows, oe_name)

    batches = []

    for tr in tables[1].tbody.find_all("tr"):
        td = [x.get_text(" ", strip=True) for x in tr.find_all("td")]

        batches.append(
            {
                "subject": td[0],
                "type": td[1],
                "credits": td[2],
                "semester": td[3],
                "batch": td[4],
            }
        )

    subject["batches"] = batches

    return subject


OUT = Path("courses.json")

if OUT.exists():
    db = json.loads(OUT.read_text())
else:
    db = {}

oe = get_oe_courses()

print(f"Found {len(oe)} OE courses.\n")

for code, oe_name in oe.items():
    if code in db:
        print(f"✓ Skipping {code}")
        continue

    print(f"Downloading {code}...")

    try:
        html = search_course(code)

        db[code] = parse_course(
            html,
            oe_name,
        )

        OUT.write_text(
            json.dumps(
                db,
                indent=2,
                ensure_ascii=False,
            )
        )

        print(f"  Saved {code}")

    except Exception as e:
        print(f"  ERROR: {code}: {e}")

    time.sleep(0.3)

print("\nDone.")
