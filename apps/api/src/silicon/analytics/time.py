from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
ZONE=ZoneInfo('Asia/Shanghai')
def day(value):
    if isinstance(value,str):
        if len(value)==10:return date.fromisoformat(value)
        value=datetime.fromisoformat(value.replace('Z','+00:00'))
    if isinstance(value,datetime) and value.tzinfo is None:raise ValueError('经营时刻必须包含时区')
    return value.astimezone(ZONE).date() if isinstance(value,datetime) else value

def boundary(value):return datetime.combine(value,time.min,ZONE).astimezone(timezone.utc)
def until(value):return boundary(value+timedelta(days=1))
def today():return datetime.now(ZONE).date()
