# beetsync

[Beets](http://beets.io/) plugin to sync music files in specified playlists to another directory

## Installation

```bash
$ git clone https://github.com/evanc577/beetsync.git
```

Add the following to your beets config.yaml

```yaml
pluginpath:
  - path/to/beetsync/beetsplug

relative_to: path/to/beets/library
playlists_dir: path/to/playlists/directory
sync:
  - output_dir: path/to/sync/directory1
    playlists: name_of_playlist1
  - output_dir: path/to/sync/directory2
    playlists: name_of_playlist2
```

## Usage

```bash
beet sync
```

or 

```bash
beet sync name_of_playlist1
```
