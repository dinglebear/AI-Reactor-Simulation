import json,sys,datetime
for l in sys.stdin:
    d=json.loads(l)["rate_limit_info"]["unifiedWindows"]
    f=d["five_hour"]; s=d["seven_day"]
    r=datetime.datetime.utcfromtimestamp(f["resetsAt"]).strftime("%H:%M UTC")
    print(f"five_hour={f['utilization']:.2f} resets={r} seven_day={s['utilization']:.2f}")
