import sqlite3
import os
import pandas as pd
from google import genai
from google.genai import types

DB_PATH = "baza_wiedzy.db"

def init_db():
    """Inicjalizuje bazę i tworzy przykładową strukturę, jeśli plik nie istnieje."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rejsestruj_zdarzenia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kategoria TEXT,
            opis TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def query_local_database(sql_query: str) -> str:
    """Wykonuje zapytania odczytu (SELECT) do uniwersalnej bazy danych."""
    if not sql_query.strip().upper().startswith("SELECT"):
        return "Błąd: Dozwolone są wyłącznie operacje odczytu (SELECT)."
    
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(sql_query, conn)
        return df.to_string(index=False) if not df.empty else "Brak wyników."
    except Exception as e:
        return f"Błąd wykonania SQL: {str(e)}"
    finally:
        conn.close()

if __name__ == "__main__":
    # 1. Przygotowanie bazy danych
    init_db()
    
    # 2. Inicjalizacja klienta Gemini
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Brak klucza GEMINI_API_KEY w zmiennych środowiskowych.")
        exit(1)
        
    client = genai.Client(api_key=api_key)

    # 3. Bezstanowa analiza struktury i danych
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents='Sprawdź w bazie SQLite jakie tabele są dostępne (użyj zapytania SELECT name FROM sqlite_master WHERE type="table";) i opisz krótko strukturę bazy.',
        config=types.GenerateContentConfig(
            tools=[query_local_database],
            system_instruction="Jesteś uniwersalnym agentem analitycznym. Używasz narzędzia SQL do badania struktury bazy i odpowiadania na zapytania."
        )
    )
    
    print("--- RAPORT AGENTA ---")
    print(response.text)
