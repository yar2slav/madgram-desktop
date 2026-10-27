# mad

[русский](#русский) · [english](#english)

## русский

сначала спасибо [nitreojs](https://github.com/nitreojs) за [tele](https://github.com/nitreojs/tele). почти всё, что умеет mad, сделано там: гостмод, сохранённые удалённые сообщения, скрипты, mtproto-консоль, shots, локальные папки и ещё три с лишним сотни патчей. mad это форк tele с нашими патчами поверх

сам tele это очередь патчей поверх каждого стабильного релиза [telegram desktop](https://github.com/telegramdesktop/tdesktop). mad устроен так же: `UPSTREAM` фиксирует тег tdesktop (сейчас `v7.3.3`), `patches/` хранит всю очередь, сборки делает github actions в этом репозитории

### скачать

последняя сборка лежит в [релизах](https://github.com/yar2slav/madgram-desktop/releases). установленную телегу и её данные ни одна из них не трогает

| файл | |
|---|---|
| `mad.exe` | один файл. при запуске распаковывает нужное сам, данные хранит в `%localappdata%/mad-single/profile` |
| `mad-<версия>-win64.zip` | распакуй куда угодно и запусти `mad.exe`. данные лежат рядом с exe |

пока только windows x64. сборки не подписаны сертификатом, так что windows может ругнуться при первом запуске. mad обновляется сам: раз в 3 часа проверяет релизы, качает новую версию в фоне и предлагает перезапуститься. фид обновлений подписан, так что сборку не отсюда он не поставит. выключается в настройки → mad → обновления. к каждому релизу приложены `SHA256SUMS` и `source-manifest.json` с хешами патчей, из которых он собран

### что есть из tele

всё, что даёт tele, в mad осталось. коротко:

- гостмод: без прочтений, «печатает», онлайна и просмотров сторис, для всех чатов или только некоторых
- удалённые сообщения и история правок остаются в чате, если надо, то и после перезапуска
- режим стримера: окно скрыто от записи экрана, имена и текст скрыты в уведомлениях
- больше папок, чатов в папке и закрепов, чем разрешает телеграм. лишнее хранится на этом устройстве
- shots: сохранить сообщения картинкой
- скрипты на js и ts, которым доступен весь api телеграма
- mtproto-консоль, редактор меню, чистка ссылок от трекинга, экспорт и импорт настроек
- студия подарков, оформление карточки money, подписи к стикерам и прочее

полный список по страницам настроек лежит в [docs/features.md](docs/features.md)

### что добавили мы

настройки mad вынесены отдельной секцией в самый верх настроек

- **русский интерфейс.** все строки tele и mad переведены на русский, подписи и объяснения переписаны по смыслу, а не дословно
- **подсказки к настройкам.** скрепка рядом с опцией открывает её описание и не переключает её. названия переносятся, а не обрезаются
- **быстрые режимы.** гостмод и режим стримера включаются из бокового меню и трея, по желанию сразу при запуске. ненужное прячется правым кликом
- **синхронизация истории.** удалённые сообщения и версии правок можно синкать между своими пк через `sync.mad.tg`. по умолчанию выключено, включается отдельно для каждого аккаунта. шифруется на клиенте, мастер-ключ на сервер не уходит, медиа не переносятся. [код сервера и протокол](server/README.md)
- **свои бейджи.** галочки mad приходят с `b.mad.tg`, проверяются по подписи и не путаются с premium и верификацией
- **apple-эмодзи.** обычные эмодзи рисуются картинками apple, кастомные эмодзи телеграма не меняются
- **иконки.** красный mad, белый mad, стандартная телеграм или своя, для окна и для трея
- **сообщения.** действия tele с сообщениями собраны в плоское меню. рядом с «переслать» в режиме выделения есть кнопка shot со счётчиком. в профиле можно скрыть или показать сообщения конкретного человека, не трогая общий режим игнора
- **выделение чатов** прямо из контекстного меню списка чатов
- **диплинки `mad://`.** управление клиентом по ссылкам, их можно вешать на ярлыки или горячие клавиши:

  | ссылка | что делает |
  |---|---|
  | `mad://ghost/on`, `mad://ghost/off` | включает или выключает гостмод |
  | `mad://streamer/on`, `mad://streamer/off` | включает или выключает режим стримера |
  | `mad://settings` | открывает настройки mad |
  | `mad://ghost`, `mad://streamer`, `mad://sync` | открывает нужный раздел |

  правый клик на любой настройке → «скопировать ссылку» даёт ссылку прямо на неё, например `mad://settings/privacy?highlight=mad-hide-stories`. ссылки работают и прямо в тексте сообщений
- **приветствие.** при первом входе в аккаунт приходит локальное сообщение mad с кратким обзором и ссылками на нужные настройки
- **свои обновления.** апдейтер tele переведён на релизы этого репо и свой ключ подписи, работает и в однофайловом `mad.exe`
- **сборка одним файлом.** `mad.exe` плюс релизы через actions с тестами, контрольными суммами и манифестом исходников

все наши патчи с номерами от 337 и выше описаны в [docs/releases.md](docs/releases.md)

### ещё

- [docs/mad.md](docs/mad.md): сборка mad локально и подробности про синхронизацию
- [docs/actions.md](docs/actions.md): как собрать и выпустить релиз через actions
- [server](server/README.md): сервер синхронизации и как поднять свой
- [канал](https://t.me/maadgram)

### сборка

как у tele: ставишь всё, что нужно tdesktop для тега из `UPSTREAM`, применяешь очередь и собираешь

```
git clone https://github.com/yar2slav/madgram-desktop.git mad
git clone --branch v7.3.3 --recurse-submodules https://github.com/telegramdesktop/tdesktop.git tdesktop
python mad/tele.py --tdesktop tdesktop apply
python mad/configure-mad.py
python mad/build-mad.py
```

`configure-mad.py` спросит твои `api_id` и `api_hash` с [my.telegram.org](https://my.telegram.org). они остаются в локальном кеше cmake и в репозиторий не попадают. подробности в [docs/mad.md](docs/mad.md) и в [docs/development.md](docs/development.md) от tele

### благодарности

- [tele](https://github.com/nitreojs/tele) от nitreojs: на нём mad и построен. история и авторство его патчей сохранены
- [tdesktop](https://github.com/telegramdesktop/tdesktop), из которого собирается каждая сборка
- [materialgram](https://github.com/kukuruzka165/materialgram), [freshGram](https://github.com/Snowy-Fluffy/freshGram), [AyuGram Desktop](https://github.com/AyuGram/AyuGramDesktop) и [SPOwnerBot](https://github.com/arynyklas/SPOwnerBot): из их идей выросла часть фич tele, подробнее в [его readme](https://github.com/nitreojs/tele#credits)
- [emoji-datasource-apple](https://github.com/iamcal/emoji-data): картинки эмодзи

лицензия: [gpl v3 telegram desktop с исключением для openssl](LICENSE)

## english

first of all, thanks to [nitreojs](https://github.com/nitreojs) for [tele](https://github.com/nitreojs/tele). almost everything mad can do comes from it: ghost mode, kept deleted messages, scripts, the mtproto console, shots, local folders and three hundred-odd other patches. mad is a fork of tele with our own patches on top

tele is a queue of patches applied on top of every stable [telegram desktop](https://github.com/telegramdesktop/tdesktop) release. mad works the same way: `UPSTREAM` pins the tdesktop tag (`v7.3.3` right now), `patches/` holds the whole queue, and github actions in this repository builds it

### download

grab the latest build from [releases](https://github.com/yar2slav/madgram-desktop/releases). none of them touch an installed telegram or its data

| file | |
|---|---|
| `mad.exe` | a single file. it unpacks what it needs on launch and keeps its data in `%localappdata%/mad-single/profile` |
| `mad-<version>-win64.zip` | unpack anywhere and run `mad.exe`. data stays next to the exe |

windows x64 only for now. builds aren't code-signed, so windows may warn you on first launch. mad updates itself: it checks these releases every 3 hours, downloads new builds in the background and asks you to restart. the feed is signed, so a build that isn't from here won't be installed. turn it off in settings → mad → updates. every release comes with `SHA256SUMS` and a `source-manifest.json` listing the hashes of the patches it was built from

### what comes from tele

everything tele gives you is still in mad. in short:

- ghost mode: no read receipts, typing, online status or story views, for every chat or just some
- deleted messages and edit history stay in the chat, even after a restart if you want
- streamer mode: hide the window from screen capture, names and text from notifications
- more folders, chats per folder and pinned chats than telegram allows, kept on this device
- shots: save messages as a picture
- javascript and typescript scripts with access to telegram's whole api
- mtproto console, menu editor, link cleaner, settings export and import
- gift studio, money card designs, sticker captions and more

the full list, grouped by settings page, is in [docs/features.md](docs/features.md)

### what we added

mad's settings live in their own section at the very top of the settings

- **russian interface.** every tele and mad string is translated into russian, with labels and explanations rewritten for meaning, not word by word
- **setting hints.** the paperclip next to an option opens its description without toggling it. long names wrap instead of getting cut off
- **quick modes.** ghost mode and streamer mode toggle from the side menu and the tray, optionally right at startup. right-click hides what you don't need
- **history sync.** sync kept deleted messages and edit versions between your own pcs through `sync.mad.tg`. off by default and turned on per account. encrypted on the client, the master key never leaves it, media isn't synced. [server code and protocol](server/README.md)
- **own badges.** mad badges come from `b.mad.tg`, are checked against a signature and don't mix with premium or verification icons
- **apple emoji.** standard emoji are drawn with apple's images. telegram's custom emoji stay as they are
- **icons.** red mad, white mad, the stock telegram icon or your own, for the window and the tray
- **messages.** tele's message actions are flattened into one menu. selection mode gets a shot button with a counter next to forward. a profile can hide or show one person's messages without touching the global ignore mode
- **chat selection** right from the chat list context menu
- **`mad://` deep links.** control the client with links, handy for shortcuts and hotkeys:

  | link | what it does |
  |---|---|
  | `mad://ghost/on`, `mad://ghost/off` | turns ghost mode on or off |
  | `mad://streamer/on`, `mad://streamer/off` | turns streamer mode on or off |
  | `mad://settings` | opens mad's settings |
  | `mad://ghost`, `mad://streamer`, `mad://sync` | opens that section |

  right-click any setting → "copy link" for a link straight to it, like `mad://settings/privacy?highlight=mad-hide-stories`. links work inside message text too
- **welcome.** the first time you sign in, a local mad message gives a short tour with links to the right settings
- **own updates.** tele's updater points at this repository's releases and its own signing key, and works in the single-file `mad.exe` too
- **single-file build.** `mad.exe`, plus releases from actions with tests, checksums and a source manifest

every patch of ours, from 337 up, is listed in [docs/releases.md](docs/releases.md)

### more

- [docs/mad.md](docs/mad.md): building mad locally and the details of sync
- [docs/actions.md](docs/actions.md): building and publishing a release with actions
- [server](server/README.md): the sync server and how to run your own
- [channel](https://t.me/maadgram)

### building

same as tele: install what tdesktop needs for the tag in `UPSTREAM`, apply the queue and build

```
git clone https://github.com/yar2slav/madgram-desktop.git mad
git clone --branch v7.3.3 --recurse-submodules https://github.com/telegramdesktop/tdesktop.git tdesktop
python mad/tele.py --tdesktop tdesktop apply
python mad/configure-mad.py
python mad/build-mad.py
```

`configure-mad.py` asks for your own `api_id` and `api_hash` from [my.telegram.org](https://my.telegram.org). they stay in the local cmake cache and never end up in the repository. see [docs/mad.md](docs/mad.md) and tele's [docs/development.md](docs/development.md) for the details

### credits

- [tele](https://github.com/nitreojs/tele) by nitreojs, which mad is built on. the history and authorship of its patches are kept
- [tdesktop](https://github.com/telegramdesktop/tdesktop), which every build is made from
- [materialgram](https://github.com/kukuruzka165/materialgram), [freshGram](https://github.com/Snowy-Fluffy/freshGram), [AyuGram Desktop](https://github.com/AyuGram/AyuGramDesktop) and [SPOwnerBot](https://github.com/arynyklas/SPOwnerBot), whose ideas shaped a part of tele's features. more in [its readme](https://github.com/nitreojs/tele#credits)
- [emoji-datasource-apple](https://github.com/iamcal/emoji-data) for the emoji images

license: [telegram desktop's gpl v3 with the openssl exception](LICENSE)
