import sqlite3
import os
import time
import pandas as pd
from google import genai
from google.genai import types
from google.genai.errors import APIError
from openai import OpenAI

DB_PATH = "baza_wiedzy.db"

def init_db():
    """Inicjalizuje bazę i tworzy tabele z kolumną weryfikacji."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitoring_cen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produkt TEXT,
            cena TEXT,
            zrodlo TEXT,
            status_weryfikacji TEXT,
            data_odczytu TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def audit_with_deepseek(szukany_produkt: str, tresc_oferty: str) -> str:
    """Wysyła pobrane dane do DeepSeek API w celu ścisłej weryfikacji technicznej."""
    ds_key = os.environ.get("DEEPSEEK_API_KEY")
    if not ds_key:
        return "POMINIĘTO (Brak DEEPSEEK_API_KEY w Secrets)"

    try:
        client_ds = OpenAI(api_key=ds_key, base_url="https://api.deepseek.com")
        
        prompt = (
            f"Jesteś surowym inżynierem i audytorem ofert handlowych.\n"
            f"Weryfikujesz, czy poniższa oferta znaleziona w sieci odpowiada produktowi: '{szukany_produkt}'.\n\n"
            f"Otrzymana treść oferty z sieci:\n{tresc_oferty[:1500]}\n\n"
            f"Odpowiedz wyłącznie jednym słowem:\n"
            f"- 'ZATWIERDZONE' – jeśli oferta na 100% dotyczy adaptera Danfoss RTD na gwint M30x1,5.\n"
            f"- 'ODRZUCONE' – jeśli oferta dotyczy innego gwintu (np. Danfoss RA, RAVL) lub innego produktu."
        )

        response = client_ds.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"BŁĄD DEEPSEEK: {str(e)}"

def save_record(produkt: str, cena: str, zrodlo: str, status: str) -> str:
    """Zapisuje zweryfikowany rekord bezpośrednio w SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO monitoring_cen (produkt, cena, zrodlo, status_weryfikacji) VALUES (?, ?, ?, ?)",
            (produkt, cena, zrodlo, status)
        )
        conn.commit()
        return "Sukces zapisu w bazie SQLite."
    except Exception as e:
        return f"Błąd SQLite: {str(e)}"
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Brak klucza GEMINI_API_KEY w środowisku.")
        exit(1)
        
    client = genai.Client(api_key=api_key)

    print("Krok 1: Wyszukiwanie w sieci przez Gemini Google Search Grounding...")
    search_prompt = "Znajdź aktualne ceny adaptera Danfoss RTD na M30x1,5 w polskich sklepach. Podaj nazwy sklepów, ceny w PLN i linki."
    
    surowe_dane = None
    
    # Wykorzystujemy stabilny model gemini-2.0-flash z obsługą błędów przekroczenia limitów
    for attempt_model in ['gemini-2.0-flash', 'gemini-1.5-flash']:
        try:
            search_response = client.models.generate_content(
                model=attempt_model,
                contents=search_prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}]
                )
            )
            surowe_dane = search_response.text
            if surowe_dane:
                break
        except APIError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"[Ostrzeżenie] Limit dla {attempt_model} osiągnięty. Czekam 5 sekund przed ponowieniem...")
                time.sleep(5)
            else:
                print(f"Błąd API Gemini ({attempt_model}): {e}")
        except Exception as e:
            print(f"Błąd ogólny ({attempt_model}): {e}")

    if not surowe_dane:
        print("Nie udało się pobrać danych z Gemini z powodu przekroczenia limitów API. Proces przełożony do następnego uruchomienia.")
        exit(0)  # Zamykamy skrypt z kodem 0, aby GitHub Actions nie zgłaszał fałszywego awaryjnego czerwonego błędu

    print("\n--- RAPORT Z WYSZUKIWARKI GOOGLE ---")
    print(surowe_dane)

    print("\nKrok 2: Audyt weryfikacyjny w DeepSeek...")
    status_audytu = audit_with_deepseek("Adapter Danfoss RTD na M30x1,5", surowe_dane)
    
    wynik_zapisu = save_record(
        produkt="Adapter Danfoss RTD na M30x1,5",
        cena="Wg raportu Google",
        zrodlo="Google Search Grounding",
        status=status_audytu
    )
    
    print(f"\n--- Wynik Audytu DeepSeek: [{status_audytu}] ---")
    print(f"Stan zapisu bazy: {wynik_zapisu}")
