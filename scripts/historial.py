"""Mirador Markets · historial semanal largo.

Corre una vez por semana en GitHub Actions. Baja ~5 años de cierres semanales
de cada activo del universo y escribe historial.json en la raíz del repositorio.

- Acciones: Twelve Data (necesita el secreto TWELVEDATA_KEY).
- Cripto: Binance (datos públicos, sin llave). Si una moneda no está en Binance,
  usa CoinGecko (gratis, solo el último año).

Solo usa la biblioteca estándar de Python.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

SEMANAS = 262  # ~5 años
TD_KEY = os.environ.get("TWELVEDATA_KEY", "").strip()

ACCIONES = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "AMZN": "Amazon", "GOOGL": "Alphabet",
    "META": "Meta", "TSLA": "Tesla", "AMD": "AMD", "INTC": "Intel", "UBER": "Uber", "PFE": "Pfizer",
    "AVGO": "Broadcom", "JPM": "JPMorgan Chase", "V": "Visa", "MA": "Mastercard", "WMT": "Walmart",
    "COST": "Costco", "XOM": "Exxon Mobil", "UNH": "UnitedHealth", "JNJ": "Johnson & Johnson",
    "PG": "Procter & Gamble", "HD": "Home Depot", "ORCL": "Oracle", "NFLX": "Netflix", "CRM": "Salesforce",
    "BAC": "Bank of America", "KO": "Coca-Cola", "DIS": "Walt Disney", "PEP": "PepsiCo", "CSCO": "Cisco",
    "QCOM": "Qualcomm", "TXN": "Texas Instruments", "ADBE": "Adobe", "PYPL": "PayPal", "ABNB": "Airbnb",
    "SBUX": "Starbucks", "NKE": "Nike", "BA": "Boeing", "GE": "GE Aerospace", "CAT": "Caterpillar",
}

# id de CoinGecko (como en Airtable) -> (nombre, par en Binance o None)
CRIPTO = {
    "bitcoin": ("Bitcoin", "BTCUSDT"), "ethereum": ("Ethereum", "ETHUSDT"), "solana": ("Solana", "SOLUSDT"),
    "ripple": ("XRP", "XRPUSDT"), "dogecoin": ("Dogecoin", "DOGEUSDT"), "binancecoin": ("BNB", "BNBUSDT"),
    "cardano": ("Cardano", "ADAUSDT"), "tron": ("TRON", "TRXUSDT"), "avalanche-2": ("Avalanche", "AVAXUSDT"),
    "chainlink": ("Chainlink", "LINKUSDT"), "polkadot": ("Polkadot", "DOTUSDT"), "litecoin": ("Litecoin", "LTCUSDT"),
    "shiba-inu": ("Shiba Inu", "SHIBUSDT"), "bitcoin-cash": ("Bitcoin Cash", "BCHUSDT"), "uniswap": ("Uniswap", "UNIUSDT"),
    "stellar": ("Stellar", "XLMUSDT"), "hedera-hashgraph": ("Hedera", "HBARUSDT"), "aptos": ("Aptos", "APTUSDT"),
    "cosmos": ("Cosmos", "ATOMUSDT"), "near": ("NEAR Protocol", "NEARUSDT"), "filecoin": ("Filecoin", "FILUSDT"),
    "arbitrum": ("Arbitrum", "ARBUSDT"), "internet-computer": ("Internet Computer", "ICPUSDT"),
    "monero": ("Monero", None), "algorand": ("Algorand", "ALGOUSDT"),
    "pepe": ("Pepe", "PEPEUSDT"), "dogwifcoin": ("dogwifhat", "WIFUSDT"), "bonk": ("Bonk", "BONKUSDT"),
    "floki": ("Floki", "FLOKIUSDT"),
}


def get_json(url, intentos=3):
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MiradorMarkets/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if i == intentos - 1:
                raise
            print(f"  reintento ({e})", file=sys.stderr)
            time.sleep(5 * (i + 1))


def dia(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def accion(simbolo):
    url = ("https://api.twelvedata.com/time_series?symbol=" + simbolo +
           f"&interval=1week&outputsize={SEMANAS}&order=ASC&apikey=" + TD_KEY)
    j = get_json(url)
    if j.get("status") != "ok":
        raise RuntimeError(j.get("message", "respuesta sin datos"))
    return [[v["datetime"][:10], round(float(v["close"]), 6)] for v in j["values"]]


def cripto_binance(par):
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={par}&interval=1w&limit={SEMANAS}"
    filas = get_json(url)
    if not filas:
        raise RuntimeError("sin velas")
    return [[dia(f[0]), float(f[4])] for f in filas]


def cripto_coingecko(cg_id):
    url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days=365&interval=daily"
    precios = get_json(url)["prices"]
    semanal, ultima = [], None
    for ms, p in precios:  # un punto por semana (el de cada lunes) + el último
        d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        clave = d.isocalendar()[:2]
        if clave != ultima:
            semanal.append([d.strftime("%Y-%m-%d"), p])
            ultima = clave
        else:
            semanal[-1] = [semanal[-1][0], p]
    return semanal


def main():
    salida = {"actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "activos": {}}
    previo = {}
    try:
        with open("historial.json", encoding="utf-8") as f:
            previo = json.load(f).get("activos", {})
    except Exception:  # noqa: BLE001
        pass
    fallos = []

    if not TD_KEY:
        print("Falta TWELVEDATA_KEY: las acciones conservan el historial anterior.", file=sys.stderr)
    for s, n in ACCIONES.items():
        try:
            if not TD_KEY:
                raise RuntimeError("sin llave")
            serie = accion(s)
            salida["activos"][s] = {"n": n, "m": "acciones", "fuente": "Twelve Data", "w": serie}
            print(f"{s}: {len(serie)} semanas")
        except Exception as e:  # noqa: BLE001
            fallos.append(f"{s}: {e}")
            if s in previo:
                salida["activos"][s] = previo[s]
        time.sleep(8.5)  # plan gratis: 8 consultas por minuto

    for cg_id, (n, par) in CRIPTO.items():
        try:
            if par:
                try:
                    serie, fuente = cripto_binance(par), "Binance"
                except Exception:  # noqa: BLE001
                    serie, fuente = cripto_coingecko(cg_id), "CoinGecko"
            else:
                serie, fuente = cripto_coingecko(cg_id), "CoinGecko"
            salida["activos"][cg_id] = {"n": n, "m": "cripto", "fuente": fuente, "w": serie}
            print(f"{cg_id}: {len(serie)} semanas ({fuente})")
        except Exception as e:  # noqa: BLE001
            fallos.append(f"{cg_id}: {e}")
            if cg_id in previo:
                salida["activos"][cg_id] = previo[cg_id]
        time.sleep(2.5)

    with open("historial.json", "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Listo: {len(salida['activos'])} activos.")
    if fallos:
        print("No se pudieron actualizar:\n  " + "\n  ".join(fallos), file=sys.stderr)


if __name__ == "__main__":
    main()
