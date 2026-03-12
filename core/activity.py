from collections import deque
from datetime import datetime

# In-memory activity log — last 50 events
_log: deque = deque(maxlen=50)
_fired_today = 0
_errors_today = 0


def log_event(client_id: str, message: str, level: str = "INFO"):
    global _fired_today, _errors_today
    _log.appendleft({
        "client": client_id,
        "message": message,
        "level": level,
        "time": datetime.now().strftime("%H:%M:%S"),
    })
    if level == "ERROR":
        _errors_today += 1
    elif level == "INFO":
        _fired_today += 1


def get_activity():
    return list(_log)


def get_counts():
    return _fired_today, _errors_today
