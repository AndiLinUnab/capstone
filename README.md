# Capstone UNAB-Ambiental: monitoreo IoT en Bucaramanga

Proyecto final de IoT + Cloud + Sistemas Distribuidos (UNAB, 2026).
Equipo: Andi Lin, Juan Sebastian Buitrago Caballero, Miguel Angel Solano Diaz.

## Que es
Plataforma IoT propia en la nube con 11 dispositivos de 4 tipos, protocolo MQTT, visualizacion en Grafana,
alertas por Telegram y retroceso (apagar, ajustar, calibrar) desde un panel web.

| Tipo | Dispositivos |
|---|---|
| Digital twin (Python) | aire-centro, aire-cabecera, clima-floridablanca, rio-oro |
| API (Azure Maps) | clima-bga, aire-bga, trafico-bga |
| DataSet (UCI Air Quality, reproducido) | ds-gases, ds-oxidos, ds-meteo |
| Real (laptop con psutil) | laptop-casa |

## Arquitectura
Dispositivos -> Mosquitto (MQTT, usuario y ACL; WebSocket seguro para el dispositivo real) -> Telegraf -> InfluxDB 2 -> Grafana.
Caddy da HTTPS (Let's Encrypt) con DuckDNS. Un API de control (FastAPI) envia comandos por MQTT y recibe confirmaciones (ack).

Topics: `unab/capstone/<tipo>/<dispositivo>/{telemetria,cmd,ack,estado}`. Payload JSON con `ts` en milisegundos.
Comandos: `power`, `set_interval`, `calibrate`, `reset_calibration`, y segun el tipo `poll_now`, `set_speed`, `rewind`.

## Despliegue (resumen)
1. VM Ubuntu con Docker. Copiar `.env.example` a `.env` y rellenar los valores (no se suben al repositorio).
2. Crear `mosquitto/passwd` con `mosquitto_passwd` para los usuarios ingesta, dispositivos, control y real.
3. `./dataset/descargar.sh` para bajar el dataset.
4. `docker compose up -d --build`.
5. Grafana: ejecutar `grafana/make_dashboard.py`, `grafana/add_panels.py`, `grafana/make_alerts*.py` y `grafana/make_notif.py`.
6. Dispositivo real: `real_device/real_device.py` en Windows (con su `real.env`, que no se sube).

## Seguridad
Sin secretos en el repositorio. Solo se exponen los puertos 80 y 443 (HTTPS). Broker, InfluxDB, Grafana y el API de control quedan detras del proxy.

## Evidencias
Carpeta `evidencias/`. Las capturas no incluyen credenciales.
