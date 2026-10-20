$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path -LiteralPath ".venv\Scripts\uvicorn.exe")) {
    throw "No existe el entorno virtual .venv. Ejecuta python -m venv .venv"
}
Write-Host "Iniciando Motor RAG en http://127.0.0.1:8000"
Write-Host "Swagger: http://127.0.0.1:8000/docs"
& ".venv\Scripts\uvicorn.exe" api.runtime:app --host 127.0.0.1 --port 8000
