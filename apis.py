"""Dispositivos tipo API (Azure Maps) UNAB-Ambiental Capstone, con retroceso.

Topics: unab/capstone/api/<nombre>/{telemetria,cmd,ack,estado}
Comandos: power(on|off), set_interval(60-3600), calibrate(variable, offset),
          reset_calibration, poll_now
"""
import json, logging, os, signal, threading, urllib.request
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

HOST = os.environ.get("MQTT_HOST", "mosquitto")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
USER, PASS = os.environ["MQTT_USER"], os.environ["MQTT_PASS"]
KEY = os.environ["AZURE_MAPS_KEY"]
LAT = os.environ.get("LAT", "7.1182633")
LON = os.environ.get("LON", "-73.1113583")
BBOX = os.environ.get("BBOX", "-73.20,7.05,-73.05,7.20")
BASE = "unab/capstone/api"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("apis")
stop = threading.Event()


def get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def clima():
    u = (f"https://atlas.microsoft.com/weather/currentConditions/json?api-version=1.0"
         f"&query={LAT},{LON}&subscription-key={KEY}&language=es-MX")
    d = get(u)["results"][0]
    return {
        "temperature": d["temperature"]["value"],
        "sensacion_c": d["realFeelTemperature"]["value"],
        "humidity": d["relativeHumidity"],
        "wind_kmh": d["wind"]["speed"]["value"],
        "uv_index": d["uvIndex"],
        "pressure_mb": d["pressure"]["value"],
        "cloud_cover": d["cloudCover"],
        "visibility_km": d["visibility"]["value"],
        "rain_1h_mm": d["precipitationSummary"]["pastHour"]["value"],
    }


def aire():
    u = (f"https://atlas.microsoft.com/weather/airQuality/current/json?api-version=1.1"
         f"&query={LAT},{LON}&subscription-key={KEY}&language=es-MX")
    r = get(u)["results"][0]
    out = {"aqi": r["globalIndex"]}
    for p in r["pollutants"]:
        out[p["type"].lower().replace(".", "")] = p["concentration"]["value"]
    return out


def trafico():
    u = (f"https://atlas.microsoft.com/traffic/incident?api-version=2025-01-01"
         f"&bbox={BBOX}&subscription-key={KEY}&language=es-MX")
    fs = get(u).get("features", [])
    pr = [f["properties"] for f in fs]
    sev = [p.get("severity") or 0 for p in pr]
    dly = [p.get("delay") or 0 for p in pr]
    return {
        "incidentes": len(pr),
        "congestionados": sum(1 for p in pr if p.get("isTrafficJam")),
        "severidad_max": max(sev) if sev else 0,
        "severidad_media": round(sum(sev) / len(sev), 2) if sev else 0,
        "retraso_total_s": sum(dly),
        "retraso_max_s": max(dly) if dly else 0,
    }


class Api(threading.Thread):
    def __init__(self, nombre, fn, intervalo):
        super().__init__(daemon=True)
        self.nombre, self.fn, self.intervalo = nombre, fn, intervalo
        self.on, self.offset, self.wake = True, {}, threading.Event()
        self.t_tel, self.t_cmd = f"{BASE}/{nombre}/telemetria", f"{BASE}/{nombre}/cmd"
        self.t_ack, self.t_est = f"{BASE}/{nombre}/ack", f"{BASE}/{nombre}/estado"
        c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"api-{nombre}")
        c.username_pw_set(USER, PASS)
        c.will_set(self.t_est, json.dumps({"online": 0}), qos=1, retain=True)
        c.on_connect, c.on_message = self.on_connect, self.on_message
        c.reconnect_delay_set(1, 30)
        self.c = c

    def estado(self):
        return {"online": 1, "power": "on" if self.on else "off", "intervalo_s": self.intervalo, "offset": self.offset}

    def publica_estado(self):
        self.c.publish(self.t_est, json.dumps(self.estado()), qos=1, retain=True)

    def on_connect(self, c, u, f, rc, p=None):
        if rc.is_failure:
            log.error("%s: conexión rechazada: %s", self.nombre, rc)
            return
        c.subscribe(self.t_cmd, qos=1)
        self.publica_estado()
        log.info("%s conectado", self.nombre)

    def on_message(self, c, u, msg):
        ok, err, cmd, cid = True, None, None, None
        try:
            o = json.loads(msg.payload.decode("utf-8"))
            cmd, cid = o.get("cmd"), o.get("id")
            if cmd == "power":
                self.on = o["value"] == "on"
            elif cmd == "set_interval":
                v = float(o["value"])
                if not 60 <= v <= 3600:
                    raise ValueError("intervalo fuera de 60-3600 s")
                self.intervalo = v
            elif cmd == "calibrate":
                self.offset[str(o["variable"])] = float(o["offset"])
            elif cmd == "reset_calibration":
                self.offset = {}
            elif cmd == "poll_now":
                pass
            else:
                raise ValueError("comando desconocido")
        except Exception as e:
            ok, err = False, str(e)
        log.warning("%s cmd=%s ok=%s %s", self.nombre, cmd, ok, err or "")
        self.c.publish(self.t_ack, json.dumps({"id": cid, "cmd": cmd, "ok": ok, "error": err,
                       "estado": self.estado(), "ts": int(datetime.now().timestamp() * 1000)}), qos=1)
        self.publica_estado()
        self.wake.set()

    def run(self):
        self.c.connect_async(HOST, PORT, keepalive=60)
        self.c.loop_start()
        while not stop.is_set():
            if self.on:
                try:
                    vals = {k: round(v + self.offset.get(k, 0.0), 2) for k, v in self.fn().items()}
                    vals["ts"] = int(datetime.now(timezone.utc).timestamp() * 1000)
                    self.c.publish(self.t_tel, json.dumps(vals), qos=1)
                    log.info("%s publicado (%d variables)", self.nombre, len(vals) - 1)
                except Exception as e:  # nunca imprime la URL (lleva la key)
                    log.error("%s fallo consultando la API: %s", self.nombre, type(e).__name__)
            self.wake.wait(self.intervalo)
            self.wake.clear()
        self.c.publish(self.t_est, json.dumps({"online": 0}), qos=1, retain=True).wait_for_publish(2)
        self.c.loop_stop()
        self.c.disconnect()


def main():
    signal.signal(signal.SIGTERM, lambda *_: (stop.set()))
    signal.signal(signal.SIGINT, lambda *_: (stop.set()))
    iv = lambda k, d: float(os.environ.get(k, d))
    ds = [Api("clima-bga", clima, iv("INTERVALO_CLIMA", 600)),
          Api("aire-bga", aire, iv("INTERVALO_AIRE", 600)),
          Api("trafico-bga", trafico, iv("INTERVALO_TRAFICO", 300))]
    for d in ds:
        d.start()
    stop.wait()
    for d in ds:
        d.wake.set()
        d.join(5)


if __name__ == "__main__":
    main()
