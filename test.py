from datetime import date, timedelta
from app.routers.student import _next_period

t = date.today()
d = 30
print(_next_period(t, t - timedelta(days=5), d))   # expired -> starts today, ends today+30
print(_next_period(t, t + timedelta(days=10), d))  # in trial -> starts end+1, ends end+30
print(_next_period(t, t + timedelta(days=20), d))  # already paid -> continues after paid_until
print(_next_period(t, t, d))      