@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\uvicorn.exe" (
  echo No existe el entorno virtual .venv.
  echo Ejecuta primero: python -m venv .venv
  exit /b 1
)

echo Iniciando Motor RAG en http://127.0.0.1:8000
echo Swagger: http://127.0.0.1:8000/docs
echo Presiona Ctrl+C para detenerlo.
".venv\Scripts\uvicorn.exe" api.runtime:app --host 127.0.0.1 --port 8000
