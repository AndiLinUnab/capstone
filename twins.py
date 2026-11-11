"""Gemelos digitales UNAB-Ambiental Capstone: 4 estaciones simuladas con retroceso.

Topics (por dispositivo):
  unab/capstone/twin/<nombre>/telemetria  publica {"var":..., "ts": ms}
  unab/capstone/twin/<nombre>/cmd         escucha {"cmd":"power|set_interval|calibrate|reset_calibration", ...}
  unab/capstone/twin/<nombre>/ack         responde al comando
  unab/capstone/twin/<nombre>/estado      retenido; el LWT lo pone online=0
"""
import json, logging, math, os, random, signal, threading
from datetime import datetime, timedelta, timezone
import paho.mqtt.client as mqtt

HOST = os.environ.get("MQTT_HOST", "mosquitto")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
USER, PASS = os.environ["MQTT_USER"], os.environ["MQTT_PASS"]
TZ = float(os.environ.get("TZ_OFFSET_HOURS", "-5"))
INTERVAL = float(os.environ.get("INTERVAL_SECONDS", "30"))
BASE = "unab/capstone/twin"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("twins")
stop = threading.Event()
g = random.gauss


def dia(h, pico=15):
    return math.cos(2 * math.pi * (h - pico) / 24)


def trafico(h):  # dos picos: 7:30 y 18:00
    return math.exp(-((h - 7.5) / 1.6) ** 2) + 0.9 * math.exp(-((h - 18) / 1.9) ** 2)


def aire(escala):
    def f(h, st):
        t = trafico(h) * escala
        return {
            "pm25": max(2, 8 + 24 * t + g(0, 2)),
            "pm10": max(4, 16 + 36 * t + g(0, 3)),
            "no2": max(3, 12 + 40 * t + g(0, 2.5)),
            "temperature": 24 + 4 * dia(h) + g(0, 0.3),
            "humidity": min(95, 66 - 14 * dia(h) + g(0, 1)),
        }
    return f


def clima(h, st):
    uv = max(0.0, math.cos(math.pi * (h - 12) / 12)) ** 1.5 * 10
    return {
        "temperature": 23 + 4.5 * dia(h) + g(0, 0.3),
        "humidity": min(95, 68 - 16 * dia(h) + g(0, 1)),
        "pressure": 906 + 1.5 * math.cos(2 * math.pi * (h - 10) / 12) + g(0, 0.3),
        "uv_index": max(0.0, uv + g(0, 0.2)),
        "wind_speed": abs(2 + 2 * dia(h, 14) + g(0, 0.6)),
    }


def rio(h, st):
    if random.random() < 0.003:  # evento de lluvia
        st["pulso"] = random.uniform(0.6, 2.0)
    st["pulso"] *= 0.995
    p = st["pulso"]
    return {
        "nivel_m": 1.1 + p + g(0, 0.02),
        "turbidez_ntu": max(0, 12 + 70 * p + g(0, 1.5)),
        "ph": 7.5 - 0.25 * p + g(0, 0.03),
        "temp_agua_c": 22 + 1.5 * dia(h, 16) + g(0, 0.1),
    }


class Dispositivo(threading.Thread):
    def __init__(self, nombre, gen):
        super().__init__(daemon=True)
        self.nombre, self.gen = nombre, gen
        self.on, self.intervalo, self.offset, self.st = True, INTERVAL, {}, {"pulso": 0.0}
        self.t_tel = f"{BASE}/{nombre}/telemetria"
        self.t_cmd = f"{BASE}/{nombre}/cmd"
        self.t_ack = f"{BASE}/{nombre}/ack"
        self.t_est = f"{BASE}/{nombre}/estado"
        c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"twin-{nombre}")
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
                if not 2 <= v <= 3600:
                    raise ValueError("intervalo fuera de 2-3600 s")
                self.intervalo = v
            elif cmd == "calibrate":
                self.offset[str(o["variable"])] = float(o["offset"])
            elif cmd == "reset_calibration":
                self.offset = {}
            else:
                raise ValueError("comando desconocido")
        except Exception as e:
            ok, err = False, str(e)
        log.warning("%s cmd=%s ok=%s %s", self.nombre, cmd, ok, err or "")
        self.c.publish(self.t_ack, json.dumps({"id": cid, "cmd": cmd, "ok": ok, "error": err,
                                               "estado": self.estado(), "ts": int(datetime.now().timestamp() * 1000)}), qos=1)
        self.publica_estado()

    def run(self):
        self.c.connect_async(HOST, PORT, keepalive=60)
        self.c.loop_start()
        while not stop.is_set():
            if self.on:
                ahora = datetime.now(timezone.utc)
                h = (ahora + timedelta(hours=TZ)).hour + (ahora + timedelta(hours=TZ)).minute / 60
                vals = {k: round(v + self.offset.get(k, 0.0), 2) for k, v in self.gen(h, self.st).items()}
                vals["ts"] = int(ahora.timestamp() * 1000)
                try:
                    self.c.publish(self.t_tel, json.dumps(vals), qos=1)
                except Exception:
                    log.exception("error publicando")
            stop.wait(self.intervalo)
        self.c.publish(self.t_est, json.dumps({"online": 0}), qos=1, retain=True).wait_for_publish(2)
        self.c.loop_stop()
        self.c.disconnect()


def main():
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    ds = [Dispositivo("aire-centro", aire(1.0)), Dispositivo("aire-cabecera", aire(0.6)),
          Dispositivo("clima-floridablanca", clima), Dispositivo("rio-oro", rio)]
    for d in ds:
        d.start()
    stop.wait()
    for d in ds:
        d.join(5)


if __name__ == "__main__":
    main()
