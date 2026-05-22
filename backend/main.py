from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import json
import re
import gspread
from google.oauth2.service_account import Credentials
from google import genai
from datetime import datetime
import os

app = FastAPI()

CATEGORIES = ["Dining", "Transport", "Groceries", "Entertainment", "Utilities", "Other"]
SHEET_NAME = "Expense Tracker Data"  # Make sure this matches your exact Google Sheet name!

# ── Google Sheets Setup ───────────────────────────────────────
def get_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Find the directory where main.py is located (backend folder)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. First look in the root directory (where Render drops secret files)
    key_path = os.path.join(current_dir, "..", "google_creations.json")
    
    # 2. Fall back to the backend directory if running locally on your laptop
    if not os.path.exists(key_path):
        key_path = os.path.join(current_dir, "google_creations.json")
        
    creds = Credentials.from_service_account_file(key_path, scopes=scopes)
    client = gspread.authorize(creds)
    return client

def init_sheets():
    """Ensures our spreadsheets have the correct sheet names and column headers on Row 1"""
    try:
        client = get_sheets()
        spreadsheet = client.open(SHEET_NAME)
        
        # 1. Setup Transactions Sheet
        try:
            tx_sheet = spreadsheet.worksheet("transactions")
        except gspread.exceptions.WorksheetNotFound:
            tx_sheet = spreadsheet.add_worksheet(title="transactions", rows="1000", cols="8")
            tx_sheet.append_row(["id", "user_id", "message", "amount", "vendor", "category", "description", "created_at"])
            
        # 2. Setup Users Sheet
        try:
            users_sheet = spreadsheet.worksheet("users")
        except gspread.exceptions.WorksheetNotFound:
            users_sheet = spreadsheet.add_worksheet(title="users", rows="1000", cols="2")
            users_sheet.append_row(["user_id", "created_at"])
            
    except Exception as e:
        print(f"Warning: Could not initialize Google Sheets layout automatically. Error: {e}")

# Run the initialization check when backend fires up
init_sheets()

# ── Models ────────────────────────────────────────────────────
class MessageRequest(BaseModel):
    user_id: str
    text: str

class UserRequest(BaseModel):
    user_id: str

# ── Helpers ───────────────────────────────────────────────────
def extract_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except:
        pass
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No valid JSON found in: {raw}")

# ── Routes ────────────────────────────────────────────────────

@app.get("/")
def home():
    return {"status": "healthy", "message": "Expense Tracker AI Backend is Live!"}

@app.post("/register")
def register_user(req: UserRequest):
    client = get_sheets()
    users_sheet = client.open(SHEET_NAME).worksheet("users")
    
    # Get all users (returns a list of dict records)
    all_users = users_sheet.get_all_records()
    existing = any(user["user_id"] == req.user_id for user in all_users)

    if existing:
        return {"status": "existing", "user_id": req.user_id}

    # Add new user row
    users_sheet.append_row([
        req.user_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ])
    return {"status": "created", "user_id": req.user_id}


@app.post("/classify")
def classify_expense(req: MessageRequest):
    client = get_sheets()
    spreadsheet = client.open(SHEET_NAME)
    users_sheet = spreadsheet.worksheet("users")
    tx_sheet = spreadsheet.worksheet("transactions")

    # Check if user exists
    all_users = users_sheet.get_all_records()
    user_exists = any(user["user_id"] == req.user_id for user in all_users)

    if not user_exists:
        raise HTTPException(status_code=404, detail="User not found. Register first.")

    # Request to Google Gemini API using cloud variable
    prompt = f"""Extract expense details from this message and return ONLY a JSON object.

Message: "{req.text}"

Return this exact format:
{{
  "amount": <number or null>,
  "vendor": "<vendor name or null>",
  "category": "<one of: {', '.join(CATEGORIES)}>",
  "description": "<short description>"
}}

No explanation, just the raw JSON structure."""

    try:
        # Get your Gemini Key from your environmental configurations
        ai_key = os.environ.get("GEMINI_API_KEY")
        if not ai_key:
            raise ValueError("GEMINI_API_KEY environmental variable is missing on Render.")
            
        ai_client = genai.Client(api_key=ai_key)
        
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        raw = response.text.strip()
        data = extract_json(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini Cloud AI Failure: {str(e)}")

    # To create an incremental id, count total records and add 1
    total_records = len(tx_sheet.get_all_records())
    new_id = total_records + 1

    # Save data into the 'transactions' sheet
    tx_sheet.append_row([
        new_id,
        req.user_id,
        req.text,
        data.get("amount"),
        data.get("vendor"),
        data.get("category"),
        data.get("description"),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ])

    return data


@app.get("/transactions/{user_id}")
def get_transactions(user_id: str):
    client = get_sheets()
    tx_sheet = client.open(SHEET_NAME).worksheet("transactions")
    
    all_txs = tx_sheet.get_all_records()
    # Filter by user_id and sort descending (newest first)
    filtered = [tx for tx in all_txs if str(tx["user_id"]) == user_id]
    filtered.sort(key=lambda x: x["created_at"], reverse=True)
    
    return filtered


@app.get("/summary/{user_id}")
def get_summary(user_id: str):
    client = get_sheets()
    tx_sheet = client.open(SHEET_NAME).worksheet("transactions")
    
    all_txs = tx_sheet.get_all_records()
    filtered = [tx for tx in all_txs if str(tx["user_id"]) == user_id and tx["amount"] != ""]
    
    # Calculate summary counts and totals grouped by category
    summary_dict = {}
    for tx in filtered:
        cat = tx["category"]
        try:
            amt = float(tx["amount"])
        except ValueError:
            continue
            
        if cat not in summary_dict:
            summary_dict[cat] = {"category": cat, "total": 0.0, "count": 0}
        summary_dict[cat]["total"] += amt
        summary_dict[cat]["count"] += 1
        
    # Convert dictionary values to an ordered list sorted by total spent
    summary_list = list(summary_dict.values())
    summary_list.sort(key=lambda x: x["total"], reverse=True)
    
    return summary_list