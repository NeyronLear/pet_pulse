{% load static %}
"use strict";

// Service worker PetPulse: показывает push-уведомления, даже когда вкладка закрыта.
// Отдаётся вьюхой service_worker по адресу /user/sw.js, поэтому управляет страницами /user/.

const ICON = "{% static 'img/logo.jpeg' %}";

// Сервер (main_api/push.py) присылает JSON: {"title", "body", "url"}.
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data.text() };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "PetPulse", {
      body: data.body || "",
      icon: ICON,
      badge: ICON,
      data: { url: data.url || "/user/" },
    }),
  );
});

// По клику открываем приложение: переключаемся на уже открытую вкладку или открываем новую.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data.url, self.location.origin).href;
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((windows) => {
        const open = windows.find((client) => client.url.startsWith(self.registration.scope));
        if (open) {
          // navigate() работает только во вкладках, которыми уже управляет воркер
          return open.focus().then((client) => client.navigate(url)).catch(() => {});
        }
        return self.clients.openWindow(url);
      }),
  );
});
