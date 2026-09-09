import sqlite3
import os
import pandas as pd
from google import genai
from google.genai import types

DB_PATH = "baza_wiedzy.db"

def init_db():
    """Inicjalizuje bazę i tworzy tabele, jeśli plik nie istnieje."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitoring_cen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produkt TEXT,
            cena TEXT,
            zrodlo TEXT,
            weryfikacja TEXT,
            data_odczytu TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_price_record(produkt: str, cena: str, zrodlo: str, weryfikacja: str = "Pozytywna") -> str:
    """Zapisuje zweryfikowaną cenę i źródło bezpośrednio do tabeli monitoring_cen w bazie SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO monitoring_cen (produkt, cena, zrodlo, weryfikacja) VALUES (?, ?, ?, ?)",
            (produkt, cena, zrodlo, weryfikacja)
        )
        conn.commit()
        return f"Sukces: Zapisano do bazy -> {produkt} | Cena: {cena} | Źródło: {zrodlo}"
    except Exception as e:
        return f"Błąd zapisu do bazy: {str(e)}"
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Brak klucza GEMINI_API_KEY w zmiennych środowiskowych.")
        exit(1)
        
    client = genai.Client(api_key=api_key)

    user_prompt = (
        "Przeszukaj sieć pod kątem aktualnych cen adaptera Danfoss RTD na M30x1,5. "
        "Znajdź najbardziej precyzyjną ofertę, sprawdź czy opis na pewno dotyczy gwintu M30x1,5 i RTD, "
        "a następnie użyj narzędzia save_price_record, aby zapisać produkt, cenę oraz adres URL do bazy."
    )

    # Korzystamy z natywnej funkcji Google Search Grounding
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=user_prompt,
        config=types.GenerateContentConfig(
            tools=[
                {"google_search": {}},  # Natywne wyszukiwanie Google
                save_price_record        # Zapis do bazy SQL
            ],
            system_instruction=(
                "Jesteś precyzyjnym agentem badającym rynek. "
                "Używasz Google Search do wyszukiwania aktualnych danych w internecie "
                "oraz zapisujesz potwierdzone wynikiem wyszukiwania oferty bezpośrednio do bazy danych."
            )
        )
    )
    
    print("--- RAPORT AGENTA ---")
    print(response.text)
