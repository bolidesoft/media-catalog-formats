# All My Books database format (*.amb)

`.amb` is the same container as All My Movies' `.amm`: a **Microsoft Jet 4**
database, page-encrypted with Jet's "Encrypt Database" option, TEXT columns
stored as compressed Unicode. Everything in
[allmymovies-amm.md](allmymovies-amm.md) about opening the file, the
encryption key, the text compression, the `settings` blob and the picture
folders (`<name>_images2\NN\`, `<name>_thumbs2\NN\`) applies unchanged.
Exporter: [`tools/amb_export.py`](../tools/amb_export.py).

## Tables

```
books           the book records
Authors         persons: authors, editors, translators, illustrators (one table)
AuthorsLink     book <-> author, Role text, Sorter
EditorsLink, TranslatorsLink, IllustratorsLink   book <-> AuthorID, Sorter
Subjects / SubjectsLink       genres and topics
Bindings        Hardcover, Paperback, E-book...   (books.BindID)
Location        shelves                          (books.locationID)
images          covers and extra pictures: BookID, cover (bit), Sorter, hint, image (blob)
AuthorImages    author photos: AuthorID, Sorter, image
friends, FriendImages, LoanHistory (BookID, FriendID, Loan, Overdue, return)
CustomFields / CustomFieldsLink (Value text), CustomFlags / CustomFlagsLink (Value bit)
FileLinks       attached files (Title, Filename)
settings        per-profile blob with database options
```

### `books`

| column | meaning |
|---|---|
| `BookID` | primary key |
| `booknum` | number shown in the list |
| `title`, `originaltitle` | |
| `serie`, `Series2`, `Volume` | series names and volume |
| `ISBN` | text as typed (with or without dashes) |
| `year` | long, -1 = unknown |
| `pages` | long, -1 = unknown |
| `publisher`, `language` | text |
| `BindID`, `locationID` | lookups, -1 = none |
| `dimensions`, `circulation` | text, long |
| `rating`, `myrating` | x10 (94 = 9.4) |
| `unread` | bit; `dateread` date when finished |
| `wishlist` | bit |
| `price` | single |
| `synopsis`, `contents`, `comments` | memo |
| `url`, `LocalPath`, `FSize`, `playtime` | link, e-book file, its size, audiobook length |
| `loc`, `dewey` | Library of Congress / Dewey classification |
| `adddate`, `modified` | date/time |
| `loan`, `LoanFriendID`, `returndate`, `BorrowFriendID` | loans, as in AMM |

### `Authors`

`AuthorID, Name, AltName, BirthDay (text), BirthYear, DeathYear, BirthPlace,
Country (text, not an id), URL, biography, bibliography, Comments`.

Picture file names outside the database: `m<images.ID>.jpg` (covers and
extra pictures), `a<AuthorImages.ID>.jpg`, `f<FriendImages.ID>.jpg`.

Product page: <https://www.bolidesoft.com/allmybooks.html>.
