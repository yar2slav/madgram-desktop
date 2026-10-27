# развёртывание mad sync

production: `https://sync.mad.tg`. исходники: `/opt/mad-sync/server`, sqlite: `/var/lib/mad-sync/history.sqlite`, резервные копии: `/var/backups/mad-sync`. node 24 закреплён по digest в compose. контейнер слушает только loopback `127.0.0.1:28787`; наружу запросы принимает nginx с сертификатом let's encrypt. корень сайта возвращает 404: это api, веб-панели нет.

## воспроизведение

скопируй каталог `server` в `/opt/mad-sync/server` и выполни на linux-хосте с docker compose, nginx, certbot и python 3:

```sh
find /opt/mad-sync/server -type d -exec chmod 755 {} +
find /opt/mad-sync/server -type f -exec chmod 644 {} +
install -d -m 700 -o 65532 -g 65532 /var/lib/mad-sync
install -d -m 700 /var/backups/mad-sync
docker compose -f /opt/mad-sync/server/deploy/compose.yaml up -d
```

направь dns `sync.mad.tg` на хост. для первоначального сертификата создай временный http-vhost с `server_name sync.mad.tg` и webroot `/var/www/html` для `/.well-known/acme-challenge/`, затем выполни:

```sh
certbot certonly --webroot -w /var/www/html -d sync.mad.tg
install -m 644 /opt/mad-sync/server/deploy/nginx.conf /etc/nginx/sites-available/sync.mad.tg
ln -s /etc/nginx/sites-available/sync.mad.tg /etc/nginx/sites-enabled/sync.mad.tg
nginx -t
systemctl reload nginx
install -m 644 /opt/mad-sync/server/deploy/mad-sync-backup.service /opt/mad-sync/server/deploy/mad-sync-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mad-sync-backup.timer
systemctl start mad-sync-backup.service
```

если симлинк уже существует, повторять `ln` не нужно. включи штатный таймер обновления certbot и deploy-hook `nginx -t && systemctl reload nginx`. на текущем хосте они настроены. конфигурация nginx включает ограничение запросов и отключает access log этого api.

## обслуживание

```sh
docker compose -f /opt/mad-sync/server/deploy/compose.yaml ps
docker compose -f /opt/mad-sync/server/deploy/compose.yaml logs --tail 50 server
docker compose -f /opt/mad-sync/server/deploy/compose.yaml exec -T server node admin.mjs create-vault /data/new-connection.json
docker compose -f /opt/mad-sync/server/deploy/compose.yaml exec -T server node admin.mjs alias short real_username
systemctl status mad-sync-backup.timer
```

скачай файл подключения через ssh в защищённый локальный каталог, затем удали его серверную копию. не добавляй его в git. мастер-ключ создаёт клиент; `create-vault` выдаёт только vault и токен. команды `add-device`, `devices` и `revoke-device` описаны в [основной инструкции](../README.md).

после обновления исходников выполни серверные тесты на закреплённом образе с отдельной временной базой, затем `docker compose -f /opt/mad-sync/server/deploy/compose.yaml restart server`. база хранится отдельно и сохраняется при пересоздании контейнера.

резервная копия делается через sqlite backup ежедневно около 04:20 utc, сохраняются последние 7 успешных копий. каждая проходит `quick_check`. это копии на том же хосте; внешнее резервирование пока не настроено. для восстановления останови контейнер, сохрани текущую базу вместе с wal/shm отдельно, установи выбранную копию как `history.sqlite` с владельцем `65532:65532` и правами `600`, убери старые wal/shm из рабочего каталога и запусти контейнер. не подменяй базу работающего процесса.

## проверено

8 тестов сервера проходят на production-образе: подмена шифротекста и ключа, изоляция и отзыв токенов, лимиты, атомарность, повторы, точные 64-битные курсоры, перезапуск базы и etag, включая слабые etag после gzip nginx. через публичный https проверены запись и расшифровка отдельного тестового события после перезапуска контейнера, дедупликация, курсор и отказ без авторизации. тестовое хранилище удалено. перенос между двумя авторизованными клиентами остаётся ручной проверкой.
