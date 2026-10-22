"""Отправка web push уведомлений (стандарт Web Push + VAPID)"""

import json
import logging

from django.conf import settings
from pywebpush import WebPushException, webpush

from .models import PushSubscription

logger = logging.getLogger(__name__)

# Сколько секунд push-сервис браузера хранит уведомление, если устройство офлайн.
TTL_SECONDS = 24 * 60 * 60


def push_enabled() -> bool:
    """Без VAPID-ключей отправка невозможна, а кнопка в интерфейсе не нужна."""
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def send_push(user, title: str, body: str, url: str = "/user/") -> int:
    """Отправляет уведомление во все браузеры пользователя.
    Возвращает число успешных отправок. Подписки, от которых браузер
    отказался (404/410), удаляются."""
    if not push_enabled():
        return 0

    payload = json.dumps({"title": title, "body": body, "url": url})
    sent = 0
    for subscription in PushSubscription.objects.filter(user=user):
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                ttl=TTL_SECONDS,
            )
            sent += 1
        except WebPushException as error:
            status = error.response.status_code if error.response is not None else None
            if status in (404, 410):
                # пользователь отписался или браузер сбросил подписку
                subscription.delete()
            else:
                logger.warning(
                    "Не удалось отправить push %s: %s", subscription.pk, error
                )
    return sent
