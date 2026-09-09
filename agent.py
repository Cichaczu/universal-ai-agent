import os
import sqlite3
from datetime import datetime
from google import genai
import openai

# 1. Inicjalizacja Klientów API z zmiennych środowiskowych / Streamlit Secrets
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

# Uruchomienie inicjalizacji przy załadowaniu modułu
init_db()

# 3. Główna Logika Hiper-Agenta (3-etapowy potok przetwarzania)
def run_hyper_agent(query: str):
    """
    Krok 1: Gemini przeszukuje sieć na żywo (Google Search Grounding).
    Krok 2: DeepSeek audytuje dane pod kątem precyzji i faktów.
    Krok 3: OpenAI (GPT-4o) syntezuje wyniki i tworzy elegancki raport.
    Krok 4: SQLite zapisuje całą ścieżkę do bazy danych.
    """
    
    # ETAP 1: Gemini - Wyszukiwanie w internecie
    gemini_response = gemini_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=query,
        config={'tools': [{'google_search': {}}]}
    )
    search_data = gemini_response.text

    # ETAP 2: DeepSeek - Audyt techniczny i weryfikacja faktów
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

    # ETAP 3: OpenAI GPT-4o - Podsumowanie i raport końcowy
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

    # ETAP 4: Trwały zapis w bazie danych SQLite
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

    return {
        "final_report": final_report,
        "audit_data": audit_data,
        "search_raw": search_data
    }
