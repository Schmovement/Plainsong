# Plainsong

A browser-based music library and player for your local collection, with online discovery and thoughtful library tools.

Plainsong keeps your music library close at hand: import songs, build playlists, browse online catalogs, and customize song details, artwork, and ratings.

## Features

- **Import and play music** from individual audio files or folders, with an up-next queue and persistent playback controls.
- **Discover music online** through search alongside your library, including Audius and the Internet Archive.
- **Organize your collection** with playlists, likes, search, and library sorting and filters.
- **Edit song details** such as title, artist, album, and genre. Original metadata is retained so edits can be reverted.
- **Customize cover art** for library songs. Preview, replace, or restore the original cover; images are checked and resized before saving.
- **Rate songs from 1 to 5 stars**, sort and filter by rating, and keep ratings independent from likes.
- **Back up and restore your library**, including binary media. Restore validates the backup and offers a preview before applying it.
- **Use keyboard-accessible controls** for ratings and common player actions.

## Getting started

Plainsong is a static website and does not need a build step.

1. Clone or download this repository.
2. From the repository folder, start a local web server:

   ```bash
   python3 -m http.server 8000
   ```

3. Open [http://localhost:8000](http://localhost:8000) in your browser.
4. Choose **Import music** or **Import folder** to add songs.

A local web server is recommended so browser storage behaves consistently. Online discovery requires an internet connection.

## Your library and backups

Plainsong stores library data in your browser using IndexedDB. That data stays in the browser profile where you imported it; it does not automatically sync to another browser or device. Use **Back up library** before moving to another device or browser profile, then use **Restore from backup** there.

Restore checks the archive before changing your library and shows a preview. Keep an extra copy of important backups somewhere safe.

## Technology

Plainsong is built with HTML, CSS, and JavaScript, using browser storage and media capabilities. It has no required package installation or server-side account.

## Project status

The current verified release includes the backup and restore flow, song metadata editing, custom cover editing, and five-star ratings with rating sort and filters. Smart playlists and later roadmap features are not part of this release yet.
