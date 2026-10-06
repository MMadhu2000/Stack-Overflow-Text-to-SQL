import sqlite3
import requests
import time
from datetime import datetime

DB_PATH = "stackoverflow.db"
API_BASE = "https://api.stackexchange.com/2.3"
SITE = "stackoverflow"

API_KEY = "rl_yFT7JwiQvS3LBK9HnkYtsRc9T"  

def get_connection():
    return sqlite3.connect(DB_PATH)


def create_tables(conn):
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        display_name TEXT,
        reputation INTEGER,
        location TEXT,
        creation_date TEXT,
        last_access_date TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        question_id INTEGER PRIMARY KEY,
        title TEXT,
        body TEXT,
        tags TEXT,
        score INTEGER,
        view_count INTEGER,
        answer_count INTEGER,
        is_answered INTEGER,
        owner_user_id INTEGER,
        creation_date TEXT,
        last_activity_date TEXT,
        link TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS answers (
        answer_id INTEGER PRIMARY KEY,
        question_id INTEGER,
        body TEXT,
        score INTEGER,
        is_accepted INTEGER,
        owner_user_id INTEGER,
        creation_date TEXT,
        last_activity_date TEXT
    )
    """)

    conn.commit()


def fetch_questions(page=1, pagesize=30):
    params = {
        "order": "desc",
        "sort": "activity",
        "site": SITE,
        "page": page,
        "pagesize": pagesize,
        "filter": "withbody",
    }
    if API_KEY:
        params["key"] = API_KEY

    url = f"{API_BASE}/questions"
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "error_message" in data:
        print("API Error:", data.get("error_message"))
    if "backoff" in data:
        print(f"API requested backoff of {data['backoff']} seconds...")
        time.sleep(data["backoff"] + 1)

    return data


def fetch_answers_for_question(question_id):
    params = {
        "order": "desc",
        "sort": "votes",
        "site": SITE,
        "filter": "withbody",
        "pagesize": 10,
    }
    if API_KEY:
        params["key"] = API_KEY

    url = f"{API_BASE}/questions/{question_id}/answers"
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "backoff" in data:
        time.sleep(data["backoff"] + 1)

    return data.get("items", [])


def upsert_user(cursor, user):
    if not user or "user_id" not in user:
        return

    cursor.execute("""
    INSERT OR REPLACE INTO users
    (user_id, display_name, reputation, location, creation_date, last_access_date)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user.get("user_id"),
        user.get("display_name"),
        user.get("reputation"),
        user.get("location"),
        datetime.utcfromtimestamp(user["creation_date"]).isoformat() if user.get("creation_date") else None,
        datetime.utcfromtimestamp(user["last_access_date"]).isoformat() if user.get("last_access_date") else None,
    ))


def upsert_question(cursor, q):
    tags = ",".join(q.get("tags", [])) if q.get("tags") else None
    owner = q.get("owner", {})

    cursor.execute("""
    INSERT OR REPLACE INTO questions
    (question_id, title, body, tags, score, view_count, answer_count,
     is_answered, owner_user_id, creation_date, last_activity_date, link)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        q.get("question_id"),
        q.get("title"),
        q.get("body"),
        tags,
        q.get("score"),
        q.get("view_count"),
        q.get("answer_count"),
        1 if q.get("is_answered") else 0,
        owner.get("user_id"),
        datetime.utcfromtimestamp(q["creation_date"]).isoformat() if q.get("creation_date") else None,
        datetime.utcfromtimestamp(q["last_activity_date"]).isoformat() if q.get("last_activity_date") else None,
        q.get("link"),
    ))

    upsert_user(cursor, owner)


def upsert_answer(cursor, a, question_id):
    owner = a.get("owner", {})

    cursor.execute("""
    INSERT OR REPLACE INTO answers
    (answer_id, question_id, body, score, is_accepted,
     owner_user_id, creation_date, last_activity_date)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        a.get("answer_id"),
        question_id,
        a.get("body"),
        a.get("score"),
        1 if a.get("is_accepted") else 0,
        owner.get("user_id"),
        datetime.utcfromtimestamp(a["creation_date"]).isoformat() if a.get("creation_date") else None,
        datetime.utcfromtimestamp(a["last_activity_date"]).isoformat() if a.get("last_activity_date") else None,
    ))

    upsert_user(cursor, owner)


def ingest(max_pages=3, pagesize=30):
    conn = get_connection()
    create_tables(conn)
    cursor = conn.cursor()

    total_questions = 0
    total_answers = 0

    print("Starting live ingestion from Stack Overflow API...")
    print(f"Pages to fetch: {max_pages} | Page size: {pagesize}")
    print("-" * 50)

    for page in range(1, max_pages + 1):
        print(f"Fetching page {page}...")
        data = fetch_questions(page=page, pagesize=pagesize)
        items = data.get("items", [])

        print(f"  → Received {len(items)} questions")
        print(f"  → Quota remaining: {data.get('quota_remaining', 'N/A')}")

        if not items:
            print("No more questions found.")
            print("Raw response keys:", list(data.keys()))
            break

        for q in items:
            upsert_question(cursor, q)
            total_questions += 1

            answers = fetch_answers_for_question(q["question_id"])
            for a in answers:
                upsert_answer(cursor, a, q["question_id"])
                total_answers += 1

            time.sleep(0.3)

        conn.commit()
        print(f"  → Page {page} done | Questions: {total_questions} | Answers: {total_answers}")

        if not data.get("has_more", False):
            break

        time.sleep(1)

    conn.close()
    print("-" * 50)
    print("Ingestion complete.")
    print(f"Total questions stored/updated: {total_questions}")
    print(f"Total answers stored/updated:   {total_answers}")
    print(f"Database file: {DB_PATH}")


if __name__ == "__main__":
    ingest(max_pages=3, pagesize=30)