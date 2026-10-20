# Despliegue de producción

El motor no debe exponerse directamente a Internet con Uvicorn. En producción,
termina HTTPS en un proxy o balanceador y deja Uvicorn escuchando solo en la
red interna:

```bash
uvicorn api.runtime:app --host 127.0.0.1 --port 8000 --workers 1
```

Se recomienda un solo worker por instancia porque el lease distribuido coordina
la indexación mediante SQLite; para escalar consultas, usa varias instancias
con almacenamiento compartido y migra el lease a una cola/DB de producción.

## Variables obligatorias

Configura `RAG_API_KEY` o `RAG_API_KEYS` mediante el gestor de secretos del
entorno. No guardes `.env` en el repositorio ni imprimas sus valores en logs.
Configura también `RAG_DATA_DIR`, `RAG_CORPUS` y `RAG_EMBEDDING_VERSION`.

## Proxy HTTPS

El proxy debe:

- validar el certificado TLS y redirigir HTTP a HTTPS;
- reenviar `X-Request-ID` o generarlo;
- limitar tamaño y tiempo de solicitudes;
- permitir únicamente las rutas API necesarias;
- comprobar `GET /api/v1/health` como health check;
- no registrar el encabezado `X-API-Key`.

## Comprobación posterior

```bash
curl https://rag.example.internal/api/v1/health
curl -H 'X-API-Key: <clave>' https://rag.example.internal/api/v1/metrics
```

La terminación TLS, los certificados y el gestor de secretos dependen de la
infraestructura final; no se generan ni se publican desde este repositorio.
