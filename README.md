# TRIAX AI - Modelo de Triage con Gemini

Aplicación Flask para clasificar casos de triage con apoyo de Gemini API.

## Requisitos

- Python 3.10 o superior.
- API key de Google AI Studio.

## Instalación

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuración

Copia `.env.example` como `.env` y reemplaza el valor de `GEMINI_API_KEY`:

```env
GEMINI_API_KEY=tu_api_key_real
GEMINI_MODEL=gemini-2.5-flash
```

## Ejecución

```powershell
.venv\Scripts\python.exe app.py
```

Luego abre:

```text
http://127.0.0.1:5000/modelo
```

## Nota clínica

El resultado generado por IA es solo una herramienta de apoyo y no reemplaza la valoración del personal médico.
