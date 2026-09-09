import os
import sqlite3
import time
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError
from openai import OpenAI

DB_PATH = "baza_wiedzy.db"


def init_db():
    """Tworzy bazę SQLite, jeśli jeszcze nie istnieje."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_cen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produkt TEXT,
            cena TEXT,
            zrodlo TEXT,
            status_weryfikacji TEXT,
            data_odczytu TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def audit_with_deepseek(szukany_produkt: str, tresc_oferty: str) -> str:
    """Weryfikacja wyciągniętych ofert przez DeepSeek."""
    ds_key = os.environ.get("DEEPSEEK_API_KEY")
    if not ds_key:
        return "POMINIĘTO (Brak DEEPSEEK_API_KEY w środowisku)"

    try:
        client_ds = OpenAI(api_key=ds_key, base_url="https://api.deepseek.com")
        prompt = (
            f"Jesteś surowym inżynierem i audytorem ofert handlowych.\n"
            f"Weryfikujesz, czy poniższa oferta odpowiada zapytaniu:"
            f" '{szukany_produkt}'.\n\n"
            f"Otrzymana treść oferty z sieci:\n{tresc_oferty[:1500]}\n\n"
            f"Odpowiedz wyłącznie jednym słowem:\n"
            f"- 'ZATWIERDZONE' – jeśli oferta w 100% spełnia kryteria"
            f" zapytania.\n"
            f"- 'ODRZUCONE' – jeśli oferta dotyczy innego produktu lub brak w"
            f" niej konkretnych cen."
        )
        response = client_ds.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"BŁĄD DEEPSEEK: {str(e)}"


def save_record(produkt: str, cena: str, zrodlo: str, status: str) -> str:
    """Zapis wyniku do bazy SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO monitoring_cen (produkt, cena, zrodlo,"
            " status_weryfikacji) VALUES (?, ?, ?, ?)",
            (produkt, cena, zrodlo, status),
        )
        conn.commit()
        return "Zapisano w bazie SQLite"
    except Exception as e:
        return f"Błąd SQLite: {str(e)}"
    finally:
        conn.close()


def run_pipeline(user_query: str):
    """Główna pętla agenta: Gemini -> DeepSeek -> SQLite."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return (
            "Błąd: Brak klucza GEMINI_API_KEY w środowisku systemowym.",
            "BRAK KLUCZA",
        )

    client = genai.Client(api_key=api_key)
    surowe_dane = None
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    for attempt_model in models_to_try:
        try:
            search_response = client.models.generate_content(
                model=attempt_model,
                contents=f"Znajdź aktualne oferty i ceny dla: {user_query}. Podaj nazwy sklepów, ceny PLN i linki.",
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}]
                ),
            )
            surowe_dane = search_response.text
            if surowe_dane:
                break
        except APIError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(2)
            else:
                pass
        except Exception:
            pass

    if not surowe_dane:
        return (
            "Nie udało się pobrać danych z Gemini (przekroczone limity API).",
            "BŁĄD LIMITU",
        )

    status_audytu = audit_with_deepseek(user_query, surowe_dane)
    save_record(
        user_query, "Wg raportu Google", "Google Search Grounding", status_audytu
    )

    return surowe_dane, status_audytu


# --- INTERFEJS GRAFICZNY STREAMLIT ---
st.set_page_config(
    page_title="Universal AI Agent", page_icon="🤖", layout="centered"
)
st.title("🤖 Universal AI Agent")
st.caption(
    "Wpisz dowolny produkt – agent przeszuka sieć przez Gemini, przeprowadzi"
    " audyt w DeepSeek i zapisze dane w bazie SQLite."
)

init_db()

# Pamięć sesji czatu
if "messages" not in st.session_state:
    st.session_state.messages = []

# Wyświetlanie dotychczasowej historii rozmowy
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Okno wpisywania wiadomości
if prompt := st.chat_input("Napisz np.: 'Znajdź ceny oleju Millers 5W30'"):
    # Wyświetl wiadomość użytkownika
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Procesowanie przez Agenta
    with st.chat_message("assistant"):
        with st.spinner("Skanuję sieć (Gemini) i weryfikuję dane (DeepSeek)..."):
            raport, status = run_pipeline(prompt)

            odpowiedz_full = (
                f"{raport}\n\n"
                f"---\n"
                f"📊 **Audyt DeepSeek:** `{status}` | 💾 **Baza SQLite:**"
                f" `Zaktualizowana`"
            )
            st.markdown(odpowiedz_full)

    st.session_state.messages.append(
        {"role": "assistant", "content": odpowiedz_full}
    )
