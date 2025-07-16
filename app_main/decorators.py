from django.core.cache import cache
from django.http import JsonResponse
from functools import wraps
import time


def ratelimit_ip(rate='10/s', block=True):
    """
    rate — формат '10/s', '100/m', '1000/h'
    """
    num, per = rate.lower().split('/')
    num = int(num)

    if per == 's':
        duration = 1
    elif per == 'm':
        duration = 60
    elif per == 'h':
        duration = 3600
    else:
        raise ValueError("Invalid rate limit period")

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            ip = request.META.get("REMOTE_ADDR", "")
            key = f"ratelimit:{ip}:{view_func.__name__}"
            history = cache.get(key, [])

            now = time.time()
            # удаляем старые запросы
            history = [t for t in history if now - t < duration]
            history.append(now)

            if len(history) > num:
                if block:
                    return JsonResponse({
                        "error": "Слишком много запросов, подождите.",
                        "code": 429
                    }, status=429)
                else:
                    request.limited = True

            cache.set(key, history, timeout=duration)
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
