import sqlite3
import os
import pandas as pd
from google import genai
from google.genai import types
from openai import OpenAI

DB_PATH = "baza_wiedzy.db"

def init_db():
    """Inicjalizuje bazę i tworzy tabele z nową kolumną weryfikacyjną."""
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

def audit_with_deepseek(produkt: str, cena: str, zrodlo: str) -> str:
    """Wysyła pobrane dane do DeepSeek API w celu ścisłej weryfikacji technicznej."""
    ds_key = os.environ.get("DEEPSEEK_API_KEY")
    if not ds_key:
        return "POMINIĘTO (Brak DEEPSEEK_API_KEY)"

    try:
        # DeepSeek używa tego samego interfejsu co OpenAI, zmieniamy tylko base_url
        client_ds = OpenAI(api_key=ds_key, base_url="https://api.deepseek.com")
        
        prompt = (
            f"Jesteś surowym inżynierem i audytorem ofert handlowych.\n"
            f"Weryfikujesz, czy znaleziona oferta odpowiada szukanemu produktowi: 'Adapter Danfoss RTD na M30x1,5'.\n\n"
            f"Znaleziona nazwa: {produkt}\n"
            f"Znaleziona cena: {cena}\n"
            f"URL: {zrodlo}\n\n"
            f"Odpowiedz wyłącznie jednym słowem:\n"
            f"- 'ZATWIERDZONE' – jeśli oferta na 100% dotyczy adaptera ze starego standardu Danfoss RTD na gwint M30x1,5.\n"
            f"- 'ODRZUCONE' – jeśli oferta dotyczy innego gwintu (np. Danfoss RA, RAVL, M28) lub innego przedmiotu."
        )

        response = client_ds.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"BŁĄD DEEPSEEK: {str(e)}"

def verify_and_save_record(produkt: str, cena: str, zrodlo: str) -> str:
    """Narzędzie używane przez Gemini: przeprowadza audyt w DeepSeek i zapisuje wynik do bazy SQLite."""
    # 1. Audyt krzyżowy w DeepSeek
    status_weryfikacji = audit_with_deepseek(produkt, cena, zrodlo)
    
    # 2. Zapis do lokalnej bazy danych
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO monitoring_cen (produkt, cena, zrodlo, status_weryfikacji) VALUES (?, ?, ?, ?)",
            (produkt, cena, zrodlo, status_weryfikacji)
        )
        conn.commit()
        return (
            f"Wykonano weryfikację. Wynik DeepSeek: [{status_weryfikacji}]. "
            f"Zapisano rekord w bazie: {produkt} | {cena} PLN | {zrodlo}"
        )
    except Exception as e:
        return f"Błąd zapisu do bazy SQL: {str(e)}"
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Brak klucza GEMINI_API_KEY.")
        exit(1)
        
    client = genai.Client(api_key=api_key)

    user_prompt = (
        "Przeszukaj sieć pod kątem najnowszych cen adaptera Danfoss RTD na M30x1,5. "
        "Wyciągnij najkorzystniejszą ofertę (nazwę, cenę oraz URL) i przekaż ją "
        "do narzędzia verify_and_save_record w celu weryfikacji przez DeepSeek i zapisu do bazy."
    )

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=user_prompt,
        config=types.GenerateContentConfig(
            tools=[
                {"google_search": {}},      # Natywne wyszukiwanie Google przez Gemini
                verify_and_save_record      # Pętla weryfikacji w DeepSeek + Zapis SQL
            ],
            system_instruction=(
                "Jesteś autonomicznym agentem badawczym. Pozyskujesz dane z Google Search "
                "i przekazujesz je do zewnętrznego audytu przed zapisem do bazy."
            )
        )
    )
    
    print("--- RAPORT KOŃCOWY AGENTA ---")
    print(response.text)
