# Форматы баз данных каталогизаторов коллекций

Описания форматов и небольшие скрипты на Python для выгрузки данных из
программ, в которых ведут домашние коллекции фильмов и книг. Если ваша
коллекция лежит в одной из этих программ и её нужно достать - в таблицу,
в другую программу или просто чтобы убедиться, что данные не заперты, -
вам сюда. Полная версия описания на английском: [README.md](README.md).

Все инструменты только читают: исходный файл не изменяется.

| Программа | Файл | Описание формата | Скрипт | Что выгружает |
|---|---|---|---|---|
| All My Movies | `.amm` | [docs/allmymovies-amm.md](docs/allmymovies-amm.md) | `tools/amm_export.py` | фильмы, эпизоды, персоны, выдачи, обложки, кадры, фото |
| All My Books | `.amb` | [docs/allmybooks-amb.md](docs/allmybooks-amb.md) | `tools/amb_export.py` | книги, авторы, выдачи, обложки |
| Movienizer, Booknizer, Medianizer | `.dmo` `.dbo` `.dmb` | [docs/nizers.md](docs/nizers.md) | `tools/nizers_export.py` | записи, персоны, эпизоды, обложки |
| Kodi | `MyVideosNNN.db` | [docs/kodi.md](docs/kodi.md) | `tools/kodi_export.py` | фильмы, сериалы, эпизоды, актёры, идентификаторы |
| Ant Movie Catalog | `.amc` | [docs/ant-movie-catalog.md](docs/ant-movie-catalog.md) | `tools/amc_export.py` | версии 3.1-4.2, встроенные картинки, свои поля |
| Collectorz Book Collector | `.bkc` | [docs/collectorz.md](docs/collectorz.md) | `tools/bkc_export.py` | название, авторы, ISBN, аннотация, обложки |
| Collectorz Movie Collector | `.mvc` | [docs/collectorz.md](docs/collectorz.md) | `tools/clz_tokens.py` | раскладка описана, экспортёр пока не написан |
| Plex, Emby, Jellyfin | SQLite | [docs/media-servers.md](docs/media-servers.md) | - | заметки по схемам |

## Быстрый старт

Нужен Python 3.8 или новее. Пакет требуется только для форматов Bolide:

```
pip install access-parser
```

```
python tools/amm_export.py "C:\Users\me\Documents\Мои фильмы.amm" --covers
python tools/amb_export.py "Мои книги.amb" --covers
python tools/nizers_export.py "Фильмы.dmo" --covers
python tools/kodi_export.py "%APPDATA%\Kodi\userdata\Database\MyVideos131.db"
python tools/amc_export.py catalog.amc --pictures --encoding cp1251
python tools/bkc_export.py "Documents\Book Collector\MyCollection.bkc" --covers
```

Каждый скрипт создаёт рядом с файлом папку `<имя>_export` (или `--out`) с
CSV в UTF-8 (открываются в Excel и LibreOffice как есть), JSON с теми же
данными и папками картинок, если они запрошены. Параметры - по ключу `-h`.

## Почему для .amm и .amb нужна библиотека

Это базы Microsoft Jet 4 (формат Access 2000). Страницы зашифрованы
встроенной в Jet опцией «Encrypt Database» (это не пароль, но страницы
перемешаны RC4), а текстовые поля хранятся со «сжатием Unicode», которое
большинство открытых читателей разбирает неверно для кириллицы.
`tools/jetdb.py` решает обе задачи поверх пакета `access-parser`, так что
файлы читаются на Windows, macOS и Linux без движка Jet. На Windows также
работает 32-битный ADO с `Provider=Microsoft.Jet.OLEDB.4.0`.

## О проекте

Поддерживается [Bolide Software](https://www.bolidesoft.com/index_ru.html),
разработчиком [All My Movies](https://www.bolidesoft.com/allmymovies_ru.html)
и [All My Books](https://www.bolidesoft.com/allmybooks_ru.html). Обе
программы импортируют все перечисленные форматы напрямую (с обложками,
актёрами и эпизодами), а формат их собственных баз описан здесь, чтобы ваши
данные оставались вашими, чем бы вы ни пользовались дальше.

Лицензия: MIT.
