import sqlite3
import os
import pandas as pd
from google import genai
from google.genai import types
from duckduckgo_search import DDGS

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
            data_odczytu TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def query_local_database(sql_query: str) -> str:
    """Wykonuje zapytania odczytu (SELECT) do uniwersalnej bazy danych SQLite."""
    if not sql_query.strip().upper().startswith("SELECT"):
        return "Błąd: Dozwolone są wyłącznie operacje odczytu (SELECT)."
    
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(sql_query, conn)
        return df.to_string(index=False) if not df.empty else "Brak wyników w bazie."
    except Exception as e:
        return f"Błąd wykonania SQL: {str(e)}"
    finally:
        conn.close()

def search_web(query: str) -> str:
    """Przeszukuje internet w czasie rzeczywistym pod kątem aktualnych cen, ofert i specyfikacji."""
    try:
        results = DDGS().text(query, max_results=5)
        if not results:
            return "Brak wyników wyszukiwania w sieci."
        
        formatted = []
        for r in results:
            formatted.append(f"Tytuł: {r.get('title')}\nURL: {r.get('href')}\nOpis: {r.get('body')}\n")
        return "\n---\n".join(formatted)
    except Exception as e:
        return f"Błąd wyszukiwania w sieci: {str(e)}"

def save_price_record(produkt: str, cena: str, zrodlo: str) -> str:
    """Zapisuje wyciągniętą z sieci cenę i źródło bezpośrednio do tabeli monitoring_cen w bazie SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO monitoring_cen (produkt, cena, zrodlo) VALUES (?, ?, ?)",
            (produkt, cena, zrodlo)
        )
        conn.commit()
        return f"Sukces: Zapisano do bazy rekord -> {produkt} | Cena: {cena} | Źródło: {zrodlo}"
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

    # Polecenie wymuszające wyszukanie i zapis do bazy
    user_prompt = (
        "Znajdź w sieci aktualne ceny adaptera Danfoss RTD na M30x1,5. "
        "Wybierz najkorzystniejszą ofertę i użyj narzędzia save_price_record, "
        "aby zapisać nazwę, cenę oraz URL do naszej bazy danych."
    )

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=user_prompt,
        config=types.GenerateContentConfig(
            tools=[query_local_database, search_web, save_price_record],
            system_instruction=(
                "Jesteś autonomicznym agentem badającym rynek. "
                "Potrafisz wyszukiwać informacje w sieci, sprawdzić bazę SQL "
                "oraz trwale zapisywać nowe ustalenia za pomocą narzędzia save_price_record."
            )
        )
    )
    
    print("--- RAPORT AGENTA ---")
    print(response.text)
