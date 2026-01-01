
from sgp4.api import jday
from datetime import datetime, timezone

try:
    from sgp4.api import gstime
    print("gstime in api")
except ImportError:
    from sgp4.propagation import gstime
    print("gstime in propagation")

now = datetime.now(timezone.utc)
jd, fr = jday(now.year, now.month, now.day, now.hour, now.minute, now.second + now.microsecond * 1e-6)
print(f"JD: {jd}, FR: {fr}")
