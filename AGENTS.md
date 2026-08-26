# Proyecto PSKloud Prospector

## Regla de máquina — NO negociable

Docker Desktop **nunca** debe configurarse para arrancar con Windows. El
usuario lo inicia **solo manualmente**. Al abrirlo, los contenedores
(`restart: unless-stopped`) se levantan solos y el prospector arranca — eso es
lo deseado. No activar autostart de Docker bajo ninguna petición.

## Operación habitual (desde `C:\Users\fabio\prospeccion-pskloud`)

- Rebuild/levantar el bot: `docker compose up -d --build openclaw`
- Logs: `docker logs --tail 200 prospeccion-pskloud-openclaw-1`
- Status API: `http://localhost:9000/api/prospector/status`
- Cola de envíos: `leads_para_enviar.json` (no borrar leads válidos)
- Dashboard Streamlit (host): `python -m streamlit run app.py`
- Pausa persistente: marcador `.prospector_paused` (el usuario decide pausar/reanudar)

## Puntos sensibles del código

- `openclaw/main.py:17-19`: `sys.path` inserta la raíz del proyecto; el
  `prospector.py` que corre en el contenedor es el de la raíz, NO el de
  `openclaw/`.
- Cambios en `openclaw/` requieren rebuild (`docker compose up -d --build
  openclaw`); cambios en archivos de la raíz no.
- Los envíos se detienen si el prospector está pausado o fuera del horario
  9-16; no marcar como bug.
