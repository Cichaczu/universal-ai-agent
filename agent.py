import os
import time
import sqlite3
from datetime import datetime
from google import genai
import openai

# 1. Inicjalizacja Klientów API
gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

deepseek_client = openai.OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

openai_client = openai.OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)

# 2. Inicjalizacja Lokalnej Bazy Danych SQLite
def init_db():
    conn = sqlite3.connect('agent_memory.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_research (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            query TEXT,
            search_raw TEXT,
            audit_findings TEXT,
            final_report TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 3. Główna Logika Hiper-Agenta z maksymalną bazą modeli Gemini i fallbackiem
def run_hyper_agent(query: str):
    search_data = ""
    audit_data = ""
    final_report = ""

    # --- ETAP 1: Gemini (Maksymalna baza modeli z automatycznym przełączaniem) ---
    gemini_models = [
        'gemini-2.0-flash', 
        'gemini-1.5-pro', 
        'gemini-1.5-flash',
        'gemini-3.1',
        'gemini-3.5',
        'gemini-3.6'
    ]
    
    for model_name in gemini_models:
        try:
            gemini_response = gemini_client.models.generate_content(
                model=model_name,
                contents=query,
                config={'tools': [{'google_search': {}}]}
            )
            search_data = gemini_response.text
            if search_data:
                break  # Sukces - uzyskano dane z aktywnego modelu
        except Exception as e:
            # Automatyczne przejście do kolejnego modelu w bazie przy napotkaniu limitu/błędu
            continue

    if not search_data:
        search_data = "[BŁĄD GEMINI - Wszystkie modele z maksymalnej bazy osiągnęły limity API]"

    # Krótka pauza między etapami
    time.sleep(1)

    # --- ETAP 2: DeepSeek (Audyt techniczny z obsługą ponawiania) ---
    max_retries = 3
    for attempt in range(max_retries):
        try:
            deepseek_response = deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system", 
                        "content": (
                            "Jesteś analitykiem i audytorem technicznym. Przeanalizuj uzyskane dane z sieci. "
                            "Wyciągnij twarde fakty, zweryfikuj specyfikację, usuń szum marketingowy, "
                            "sprawdź wyliczenia i wskaż ewentualne ryzyka lub rozbieżności cenowe."
                        )
                    },
                    {
                        "role": "user", 
                        "content": f"Pytanie użytkownika: {query}\n\nSurowe dane z wyszukiwarki:\n{search_data}"
                    }
                ]
            )
            audit_data = deepseek_response.choices[0].message.content
            break
        except Exception as e:
            if attempt == max_retries - 1:
                audit_data = f"[BŁĄD DEEPSEEK - Błąd limitu / saldo: {str(e)}]"
            else:
                time.sleep(3)

    time.sleep(1)

    # --- ETAP 3: OpenAI GPT-4o (Raport końcowy z obsługą ponawiania) ---
    for attempt in range(max_retries):
        try:
            openai_response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system", 
                        "content": (
                            "Jesteś eksperckim doradcą strategicznym. Na podstawie przeprowadzonego audytu technicznego "
                            "stwórz bardzo przejrzysty, elegancki i bezpośredni raport końcowy z rekomendacjami dla użytkownika."
                        )
                    },
                    {
                        "role": "user", 
                        "content": f"Pytanie pierwotne: {query}\n\nWyniki audytu technicznego:\n{audit_data}"
                    }
                ]
            )
            final_report = openai_response.choices[0].message.content
            break
        except Exception as e:
            if attempt == max_retries - 1:
                final_report = f"[BŁĄD OPENAI: {str(e)}]"
            else:
                time.sleep(3)

    # --- ETAP 4: Zapis do SQLite ---
    try:
        conn = sqlite3.connect('agent_memory.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO market_research (timestamp, query, search_raw, audit_findings, final_report)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
            query, 
            search_data, 
            audit_data, 
            final_report
        ))
        conn.commit()
        conn.close()
    except Exception as db_err:
        print(f"Błąd zapisu bazy danych: {db_err}")

    return {
        "final_report": final_report,
        "audit_data": audit_data,
        "search_raw": search_data
    }
