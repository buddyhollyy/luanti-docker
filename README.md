# Luanti in Docker:  Mineclonia + Webclient + Seedmap

A small Compose stack that runs:
- [Luanti](https://www.luanti.org/) server
with [Mineclonia](https://content.luanti.org/packages/ryvnf/mineclonia/),
- Luanti browser client (Anyone can play without installing anything!)
- Luanti/Mineclonia seedmap: [Antichunk](https://github.com/buddyhollyy/Antichunk)

## What runs

- **luanti** — the game server. Pinned to 5.16.1: 5.18 segfaults a few
  seconds after a player joins a Mineclonia world
  ([luanti#17732](https://github.com/luanti-org/luanti/issues/17732)).
- **proxy** — a WebSocket-to-UDP bridge, so a browser can talk to the
  server. Shares the luanti container's network namespace.
- **web** — nginx. Serves the browser client, Antichunk, and proxies
  `/proxy` to the bridge.

## Setting it up

Three repositories are cloned next to this one:

    git clone https://github.com/Kaesual/minetest-wasm
    git clone https://github.com/paradust7/minetest-wasm-sample-proxy proxy-src
    git clone https://github.com/buddyhollyy/Antichunk antichunk

The game itself goes in `games/mineclonia`, and the folder name has to match
the `--gameid mineclonia` in `compose.yml`:

    curl -L -o mineclonia.zip https://content.luanti.org/packages/ryvnf/mineclonia/download/
    mkdir -p games
    unzip -q mineclonia.zip -d games
    mv games/mineclonia* games/mineclonia

Build the browser client and put it where nginx serves it. The patch in
`patches/` makes `/mineclonia` skip the launcher screen and start the game
on its own, while `/` still shows the normal launcher:

    cd minetest-wasm
    git apply ../patches/minetest-wasm-autostart.patch
    cd app
    ./docker.sh npm run build
    cp -a build/. ../../www/

Your own server settings:

    cp minetest.conf.example config/minetest.conf   # then edit it
    docker compose up -d

## The seed map

Antichunk draws the world from its seed, and will also draw what has really
been explored if it can read the world's `map.sqlite`. `nginx.conf` serves
two files out of the world folder for that, by exact name, so nothing else
in there (`auth.sqlite` holds password hashes) is reachable:

    location = /antichunk/world/map_meta.txt { alias /usr/share/nginx/world/map_meta.txt; }
    location = /antichunk/world/map.sqlite   { alias /usr/share/nginx/world/map.sqlite; }

Those two files let anyone who can reach them download the whole explored
map, so restrict them to your own network at whatever sits in front of this
stack. With nginx that is `allow` and `deny` in the matching location.

## Gotcha

The proxy shares the luanti container's network namespace, so recreating or
restarting **luanti** leaves the proxy without a network and every browser
client gets a 502. Always follow with:

    docker compose up -d --force-recreate proxy
