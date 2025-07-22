

from flask import Flask, render_template, request, jsonify, session, redirect
import sys
print("🐍 Python version:", sys.version)


import os
from dotenv import load_dotenv
load_dotenv()
import speech_recognition as sr
import sqlite3
from textblob import TextBlob
from datetime import datetime
import random
import requests


app = Flask(__name__)
app.secret_key = "secret123"

DB_FILE = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_message TEXT,
            bot_response TEXT,
            stress_level TEXT,
            source TEXT DEFAULT 'AIML'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            visible INTEGER DEFAULT 1
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
        )
    ''')

    conn.commit()
    conn.close()

init_db()

CASUAL_WORDS = {"hello", "hi", "good", "thanks", "okay"}
STRESS_WORDS = {"stressed", "anxious", "scored bad", "worried", "sad"}
CRISIS_WORDS = {"die", "suicide", "kill myself", "end my life", "want to die"}

def detect_stress_level(user_message):
    words = set(user_message.lower().split())
    if any(word in words for word in CRISIS_WORDS):
        return "CRISIS"
    elif any(word in words for word in STRESS_WORDS):
        return "STRESS"
    else:
        return "NEUTRAL"

def analyze_sentiment(text):
    sentiment = TextBlob(text).sentiment.polarity
    if sentiment < -0.3:
        return "CRISIS"
    elif sentiment < 0:
        return "STRESS"
    else:
        return "NEUTRAL"

def save_chat_history(user_message, bot_response, stress_level, source="AIML"):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_history (user_message, bot_response, stress_level, source) VALUES (?, ?, ?, ?)",
        (user_message, bot_response, stress_level, source)
    )
    conn.commit()
    conn.close()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat")
def chat_page():
    if "user" not in session:
        return redirect("/login")
    return render_template("chat.html")

@app.route("/get", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message")
    user_api_key = data.get("user_api_key")

    keyword_stress = detect_stress_level(user_message)
    sentiment_stress = analyze_sentiment(user_message)
    stress_level = max(keyword_stress, sentiment_stress, key=lambda x: ["NEUTRAL", "STRESS", "CRISIS"].index(x))

    if stress_level == "CRISIS":
        bot_response = "I'm really sorry you're feeling this way. 💙 You're not alone. Please talk to someone you trust or seek professional help."
        source = "AIML"
    elif stress_level == "STRESS":
        bot_response = "I understand that you're feeling stressed. Take a deep breath. Do you want to share what's on your mind?"
        source = "AIML"
    else:
        bot_response = ask_openrouter(user_message, user_api_key)
        source = "OpenChat"

    save_chat_history(user_message, bot_response, stress_level, source)
    return jsonify({"response": bot_response, "stress_level": stress_level})

@app.route("/voice-input", methods=["POST"])
def voice_chat():
    audio_file_path = request.json.get("audio_file_path")
    user_message = speech_to_text(audio_file_path)

    keyword_stress = detect_stress_level(user_message)
    sentiment_stress = analyze_sentiment(user_message)
    stress_level = max(keyword_stress, sentiment_stress, key=lambda x: ["NEUTRAL", "STRESS", "CRISIS"].index(x))

    if stress_level == "CRISIS":
        bot_response = "You're not alone. Please reach out to someone you trust."
    elif stress_level == "STRESS":
        bot_response = "Take a deep breath. Want to talk about it?"
    else:
        bot_response = kernel.respond(user_message)

    save_chat_history(user_message, bot_response, stress_level)
    return jsonify({"response": bot_response, "stress_level": stress_level, "transcribed_text": user_message})

from langdetect import detect

def ask_openrouter(prompt,user_key=None):
    api_key = user_key or os.getenv("OPENROUTER_API_KEY")
    print("👉 Using API Key:", api_key)
    try:
        user_lang = detect(prompt)
    except:
        user_lang = "en"

    lang_instruction = {
        "hi": "Respond in Hindi.",
        "pa": "Respond in Punjabi.",
        "en": "Respond in English."
    }.get(user_lang, "Respond in the user's language.")

    system_prompt = (
        "You are MindEase, a warm, multilingual mental health assistant. "
        "You help users feel heard and supported. Keep your replies short, empathetic, and in plain language. "
        + lang_instruction
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "deepseek/deepseek-chat-v3-0324:free",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    }

    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)

    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"].strip()
    else:
        print("❌ OpenRouter error:", response.text)
        return "Sorry, I'm having trouble connecting to the AI. Please try again later."

@app.route("/history")
def chat_history():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chat_history")
    history = cursor.fetchall()
    conn.close()
    return jsonify({"history": history})

@app.route("/journal", methods=["POST"])
def journal():
    try:
        data = request.get_json()
        if not data or 'entry' not in data:
            return jsonify({"error": "No journal entry provided"}), 400

        entry = data['entry']
        save_journal_entry(entry)
        return jsonify({"message": "Journal entry saved successfully!"})
    except Exception as e:
        print("Error in /journal:", e)
        return jsonify({"error": "Failed to save journal entry."}), 500

def save_journal_entry(entry):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO journal (entry) VALUES (?)", (entry,))
    conn.commit()
    conn.close()

@app.route("/journal/history")
def journal_history():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, entry, timestamp 
            FROM journal 
            WHERE visible = 1 
            ORDER BY timestamp DESC
        """)
        history = cursor.fetchall()
        conn.close()

        return jsonify({"journal_history": history})
    except Exception as e:
        print("🔥 Error in /journal/history route:", e)
        return jsonify({"error": "Failed to load journal history"}), 500

@app.route("/journal/delete/<int:entry_id>", methods=["DELETE"])
def delete_journal_entry(entry_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM journal WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Journal entry deleted successfully."})

@app.route("/journal/hide/<int:entry_id>", methods=["POST"])
def hide_journal(entry_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE journal SET visible = 0 WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Journal entry hidden."})

@app.route("/journal/unhide/<int:entry_id>", methods=["POST"])
def unhide_journal(entry_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE journal SET visible = 1 WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Journal entry unhidden."})

QUOTES = [
    "You are doing your best, and that’s enough.",
    "Every day is a new beginning.",
    "You are capable of amazing things.",
    "It’s okay to not be okay.",
    "Your feelings are valid.",
    "You are stronger than you think.",
    "Keep going, you’re doing great!",
    "You are not alone. ❤️"
]

@app.route("/daily-quote")
def daily_quote():
    return jsonify({"quote": random.choice(QUOTES)})

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor() 
        try:
            cursor.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, password))
            conn.commit()
            conn.close()
            return redirect("/login")
        except sqlite3.IntegrityError:
            return render_template("signup.html", error="Email already exists")

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session["user"] = email
            return redirect("/chat")
        else:
            return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/apikey")
def apikey_page():
    return render_template("apikey.html")


if __name__ == "__main__":
    app.run(debug=True)
