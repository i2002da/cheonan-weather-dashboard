import json, os, urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
SERVICE_KEY_RAW = os.environ["KMA_SERVICE_KEY"]  # percent-encoded value from data.go.kr
NX = "63"
NY = "111"

BASE_TIMES = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]


def pick_base_datetime(now_kst):
    candidates = []
    for d_offset in (0, -1):
        day = now_kst + timedelta(days=d_offset)
        for bt in BASE_TIMES:
            dt = day.replace(hour=int(bt[:2]), minute=int(bt[2:]), second=0, microsecond=0)
            candidates.append(dt)
    candidates = [c for c in candidates if c + timedelta(minutes=15) <= now_kst]
    return max(candidates)


def fetch_vilage_fcst(base_date, base_time):
    url = (
        "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
        f"?serviceKey={SERVICE_KEY_RAW}&numOfRows=1000&pageNo=1&dataType=JSON"
        f"&base_date={base_date}&base_time={base_time}&nx={NX}&ny={NY}"
    )
    with urllib.request.urlopen(url, timeout=20) as res:
        data = json.load(res)
    header = data["response"]["header"]
    if header["resultCode"] != "00":
        raise RuntimeError(f"KMA API error: {header}")
    return data["response"]["body"]["items"]["item"]


def sky_pty_to_desc(sky, pty):
    pty = str(pty) if pty is not None else "0"
    sky = str(sky) if sky is not None else None
    pty_map = {"1": "비", "2": "비/눈", "3": "눈", "4": "소나기"}
    if pty in pty_map:
        return pty_map[pty]
    sky_map = {"1": "맑음", "3": "구름많음", "4": "흐림"}
    return sky_map.get(sky, "-")


def main():
    now_kst = datetime.now(KST)
    base_dt = pick_base_datetime(now_kst)
    base_date = base_dt.strftime("%Y%m%d")
    base_time = base_dt.strftime("%H%M")

    items = fetch_vilage_fcst(base_date, base_time)

    by_key = {}
    for it in items:
        by_key[(it["fcstDate"], it["fcstTime"], it["category"])] = it["fcstValue"]

    all_datetimes = sorted(
        set((it["fcstDate"], it["fcstTime"]) for it in items if it["category"] == "TMP")
    )

    def dt_of(date_s, time_s):
        return datetime.strptime(date_s + time_s, "%Y%m%d%H%M").replace(tzinfo=KST)

    now_floor = now_kst.replace(minute=0, second=0, microsecond=0)
    future_dt = [(d, t) for (d, t) in all_datetimes if dt_of(d, t) >= now_floor]

    hourly = []
    step = 0
    for (d, t) in future_dt:
        hour = int(t[:2])
        if hour % 3 == 0:
            temp = by_key.get((d, t, "TMP"))
            sky = by_key.get((d, t, "SKY"))
            pty = by_key.get((d, t, "PTY"))
            pop = by_key.get((d, t, "POP"))
            hourly.append(
                {
                    "date": d,
                    "time": t,
                    "temperature": float(temp) if temp is not None else None,
                    "condition": sky_pty_to_desc(sky, pty),
                    "sky": sky,
                    "pty": pty,
                    "precipProb": int(pop) if pop is not None else None,
                }
            )
            step += 1
        if step >= 6:
            break

    dates_all = sorted(set(d for (d, t) in all_datetimes))
    daily = []
    for d in dates_all[:4]:
        times_today = sorted(t for (dd, t) in all_datetimes if dd == d)
        tmp_values = [float(by_key[(d, t, "TMP")]) for t in times_today if (d, t, "TMP") in by_key]
        tmn = None
        tmx = None
        for t in times_today:
            if tmn is None and (d, t, "TMN") in by_key:
                tmn = by_key[(d, t, "TMN")]
            if tmx is None and (d, t, "TMX") in by_key:
                tmx = by_key[(d, t, "TMX")]
        tmn_val = float(tmn) if tmn is not None else (min(tmp_values) if tmp_values else None)
        tmx_val = float(tmx) if tmx is not None else (max(tmp_values) if tmp_values else None)

        pops = [int(by_key[(d, t, "POP")]) for t in times_today if (d, t, "POP") in by_key]
        pop_max = max(pops) if pops else None

        noon_t = min(times_today, key=lambda t: abs(int(t[:2]) - 12)) if times_today else None
        sky_noon = by_key.get((d, noon_t, "SKY")) if noon_t else None
        pty_noon = by_key.get((d, noon_t, "PTY")) if noon_t else None

        daily.append(
            {
                "date": d,
                "tempMax": tmx_val,
                "tempMin": tmn_val,
                "precipProb": pop_max,
                "condition": sky_pty_to_desc(sky_noon, pty_noon),
            }
        )

    weather = {
        "location": "충남 천안시 서북구 성성동 (천안농협하나로 성성점 인근)",
        "baseDate": base_date,
        "baseTime": base_time,
        "generatedAt": now_kst.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "hourly": hourly,
        "daily": daily,
    }

    with open("weather.json", "w", encoding="utf-8") as f:
        json.dump(weather, f, ensure_ascii=False, indent=2)

    print(json.dumps(weather, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
