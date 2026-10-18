"""Создание пары VAPID-ключей для web push"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class Command(BaseCommand):
    help = "Печатает новую пару VAPID-ключей в формате строк для .env"

    def handle(self, *args, **options):
        private_key = ec.generate_private_key(ec.SECP256R1())
        # приватный ключ — 32 байта числа, публичный — несжатая точка кривой (65 байт):
        # именно в таком виде их ждут pywebpush и pushManager.subscribe()
        private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
        public_raw = private_key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        self.stdout.write(f"VAPID_PUBLIC_KEY={_b64url(public_raw)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={_b64url(private_raw)}")
        self.stderr.write(
            "Добавьте строки в .env (на сервере — в CI-переменную APP_ENV_FILE). "
            "Если ключи поменять, старые подписки браузеров перестанут работать."
        )
