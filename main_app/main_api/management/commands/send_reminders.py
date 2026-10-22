"""Рассылка push-напоминаний о запланированных делах питомцев.
Запускается раз в день по расписанию (cron на сервере)."""

from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from main_api.models import History
from main_api.push import push_enabled, send_push

REMINDERS_URL = "/user/#reminders"


def collect_reminders(today) -> dict:
    """Пользователь → строки уведомления.
    Напоминание — запись History с done=False: о ней пишем в день события и накануне.
    У выполненных записей бывает next_date (повторная прививка и т. п.) — о ней пишем накануне.
    """
    tomorrow = today + timedelta(days=1)
    records = (
        History.objects.filter(
            Q(done=False, date__in=[today, tomorrow]) | Q(next_date=tomorrow)
        )
        .select_related("pet__owner")
        .order_by("date", "time", "id")
    )

    lines = defaultdict(list)
    for record in records:
        if not record.done and record.date in (today, tomorrow):
            when = "Сегодня" if record.date == today else "Завтра"
            time = f" в {record.time:%H:%M}" if record.time else ""
            lines[record.pet.owner].append(
                f"{when}{time}: {record.title} ({record.pet.name})"
            )
        if record.next_date == tomorrow:
            lines[record.pet.owner].append(
                f"Завтра повторить: {record.title} ({record.pet.name})"
            )
    return lines


class Command(BaseCommand):
    help = "Отправляет push-напоминания о делах на сегодня и завтра"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать, что было бы отправлено",
        )

    def handle(self, *args, **options):
        if not push_enabled() and not options["dry_run"]:
            self.stderr.write("VAPID-ключи не заданы, push выключен.")
            return

        reminders = collect_reminders(timezone.localdate())
        sent = 0
        for user, lines in reminders.items():
            title = (
                "PetPulse: напоминание"
                if len(lines) == 1
                else f"PetPulse: дел — {len(lines)}"
            )
            body = "\n".join(lines)
            if options["dry_run"]:
                self.stdout.write(f"{user}: {title}\n{body}\n")
                continue
            sent += send_push(user, title, body, REMINDERS_URL)
        self.stdout.write(
            f"Пользователей с напоминаниями: {len(reminders)}, отправлено push: {sent}"
        )
