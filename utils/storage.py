import os
import json
import hashlib
import uuid
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

DEFAULT_DATA = {
    "profile": {
        "name": "",
        "course": "",
        "subject": "",
        "exam_date": "",
        "study_hours_per_day": 4,
        "num_units": 0
    },
    "syllabus": {
        "reasoning": "",
        "units": []
    },
    "completed_topics": [],
    "study_plan": [],
    "chat_history": [],
    "last_updated": ""
}

def ensure_data_dir():
    """
    Ensures that the primary data directory and users index file exist.
    Creates them if they do not.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def hash_password(password, salt=None):
    """
    Hashes a password using SHA-256 with a randomized salt.
    Returns the hashed password and the salt used.
    """
    if salt is None:
        salt = os.urandom(16).hex()
    hashed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return hashed, salt

def register_user(fullname, username, email, password):
    """
    Registers a new user by securely hashing their password and storing their profile.
    Also initializes their personal storage directory.
    Returns (True, 'Success') if successful, or (False, error_message).
    """
    ensure_data_dir()
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    
    if username in users:
        return False, "Username already exists."
        
    hashed_pwd, salt = hash_password(password)
    users[username] = {
        "fullname": fullname,
        "email": email,
        "password": hashed_pwd,
        "salt": salt
    }
    
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)
        
    # Create user directory
    user_dir = os.path.join(DATA_DIR, "users", username)
    os.makedirs(user_dir, exist_ok=True)
    
    # Create plans index
    plans_index_file = os.path.join(user_dir, "plans_index.json")
    if not os.path.exists(plans_index_file):
        with open(plans_index_file, "w", encoding="utf-8") as f:
            json.dump([], f)
            
    return True, "Success"

def authenticate_user(username, password):
    """
    Verifies user credentials by hashing the input password with the stored salt
    and comparing it to the stored hash.
    Returns (True, fullname) if successful, or (False, None) if not.
    """
    ensure_data_dir()
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
        
    if username not in users:
        return False, None
        
    user_data = users[username]
    hashed_pwd, _ = hash_password(password, user_data["salt"])
    
    if hashed_pwd == user_data["password"]:
        return True, user_data["fullname"]
    return False, None

def get_user_plans(username):
    """
    Retrieves all study plans associated with a given user.
    Returns a list of plan summary dictionaries.
    """
    user_dir = os.path.join(DATA_DIR, "users", username)
    os.makedirs(user_dir, exist_ok=True)
    index_file = os.path.join(user_dir, "plans_index.json")
    if not os.path.exists(index_file):
        return []
    with open(index_file, "r", encoding="utf-8") as f:
        return json.load(f)

def create_study_plan(username, plan_name, subject, mode):
    """
    Creates a new study plan for the specified user and initializes its data file.
    Returns the unique plan_id.
    """
    user_dir = os.path.join(DATA_DIR, "users", username)
    os.makedirs(user_dir, exist_ok=True)
    index_file = os.path.join(user_dir, "plans_index.json")
    
    plans = get_user_plans(username)
    plan_id = str(uuid.uuid4())
    
    new_plan_meta = {
        "plan_id": plan_id,
        "name": plan_name,
        "subject": subject,
        "mode": mode,
        "created_at": datetime.now().isoformat(),
        "last_modified": datetime.now().isoformat()
    }
    plans.append(new_plan_meta)
    
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(plans, f, indent=2)
        
    # Initialize the actual data file for the plan
    plan_file = os.path.join(user_dir, f"{plan_id}.json")
    with open(plan_file, "w", encoding="utf-8") as f:
        initial_data = DEFAULT_DATA.copy()
        initial_data["profile"]["subject"] = subject
        json.dump(initial_data, f, indent=2)
        
    return plan_id

def delete_study_plan(username, plan_id):
    user_dir = os.path.join(DATA_DIR, "users", username)
    index_file = os.path.join(user_dir, "plans_index.json")
    plans = get_user_plans(username)
    plans = [p for p in plans if p["plan_id"] != plan_id]
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(plans, f, indent=2)
        
    plan_file = os.path.join(user_dir, f"{plan_id}.json")
    if os.path.exists(plan_file):
        os.remove(plan_file)

def load_data(username=None, plan_id=None):
    ensure_data_dir()
    
    # Backwards compatibility / Fallback
    if not username or not plan_id:
        PROGRESS_FILE = os.path.join(DATA_DIR, "progress.json")
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "syllabus" not in data:
                    data["syllabus"] = {"reasoning": "", "units": []}
                if "chat_history" not in data:
                    data["chat_history"] = []
                return data
        except Exception:
            return DEFAULT_DATA.copy()
            
    plan_file = os.path.join(DATA_DIR, "users", username, f"{plan_id}.json")
    try:
        with open(plan_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "syllabus" not in data:
                data["syllabus"] = {"reasoning": "", "units": []}
            if "chat_history" not in data:
                data["chat_history"] = []
            return data
    except Exception:
        return DEFAULT_DATA.copy()

def save_data(data, username=None, plan_id=None):
    ensure_data_dir()
    data["last_updated"] = datetime.now().isoformat()
    
    if not username or not plan_id:
        PROGRESS_FILE = os.path.join(DATA_DIR, "progress.json")
        try:
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False
            
    user_dir = os.path.join(DATA_DIR, "users", username)
    os.makedirs(user_dir, exist_ok=True)
    plan_file = os.path.join(user_dir, f"{plan_id}.json")
    
    try:
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        # Update last_modified in index
        index_file = os.path.join(user_dir, "plans_index.json")
        with open(index_file, "r", encoding="utf-8") as f:
            plans = json.load(f)
        for p in plans:
            if p["plan_id"] == plan_id:
                p["last_modified"] = data["last_updated"]
                break
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(plans, f, indent=2)
            
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

def _get_current_context():
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is not None:
            import streamlit as st
            return st.session_state.get("username"), st.session_state.get("active_plan_id")
    except Exception:
        pass
    return None, None

def update_profile(name, course, subject, exam_date, study_hours_per_day, num_units, semester=""):
    username, plan_id = _get_current_context()
    data = load_data(username, plan_id)
    data["profile"] = {
        "name": name,
        "course": course,
        "subject": subject,
        "exam_date": str(exam_date),
        "study_hours_per_day": int(study_hours_per_day),
        "num_units": int(num_units),
        "semester": semester
    }
    return save_data(data, username, plan_id)

def update_syllabus(syllabus_data):
    username, plan_id = _get_current_context()
    data = load_data(username, plan_id)
    data["syllabus"] = syllabus_data
    
    all_topics = []
    for unit in syllabus_data.get("units", []):
        for topic in unit.get("topics", []):
            all_topics.append(f"{unit['unit_name']} - {topic}")
            
    data["completed_topics"] = [t for t in data["completed_topics"] if t in all_topics]
    return save_data(data, username, plan_id)

def toggle_topic_status(topic_identifier, is_completed):
    username, plan_id = _get_current_context()
    data = load_data(username, plan_id)
    completed = data.get("completed_topics", [])
    if is_completed:
        if topic_identifier not in completed:
            completed.append(topic_identifier)
    else:
        if topic_identifier in completed:
            completed.remove(topic_identifier)
    data["completed_topics"] = completed
    return save_data(data, username, plan_id)

def save_study_plan(study_plan):
    username, plan_id = _get_current_context()
    data = load_data(username, plan_id)
    data["study_plan"] = study_plan
    return save_data(data, username, plan_id)

def save_chat_history(chat_history):
    username, plan_id = _get_current_context()
    data = load_data(username, plan_id)
    data["chat_history"] = chat_history
    return save_data(data, username, plan_id)
