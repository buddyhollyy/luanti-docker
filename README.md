# Luanti in Docker:  Mineclonia + Webclient + Seedmap

A small Compose stack that runs:
- [Luanti](https://www.luanti.org/) server
with [Mineclonia](https://content.luanti.org/packages/ryvnf/mineclonia/),
- Luanti browser client: [minetest-wasm](https://github.com/Kaesual/minetest-wasm) (Anyone can play without installing anything!)
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

You need Docker, Docker Compose, curl, unzip and git, and your user has to
be in the `docker` group. Start by cloning this repo; every step below runs
inside the folder it creates.

    git clone https://github.com/buddyhollyy/luanti-docker
    cd luanti-docker

### Step 1 — get the three projects this stack uses

They are not copied into this repo, so you clone them yourself. The folder
names matter: `compose.yml` and `Dockerfile.proxy` look for them.

    git clone https://github.com/Kaesual/minetest-wasm
    git clone https://github.com/paradust7/minetest-wasm-sample-proxy proxy-src
    git clone https://github.com/buddyhollyy/Antichunk antichunk

### Step 2 — install the game

Mineclonia is the game the server runs. It has to end up in
`games/mineclonia`, because `compose.yml` starts the server with
`--gameid mineclonia`.

    curl -L -o mineclonia.zip https://content.luanti.org/packages/ryvnf/mineclonia/download/
    mkdir -p games
    unzip -q mineclonia.zip -d games
    mv games/mineclonia* games/mineclonia

### Step 3 — build the browser client

`minetest-wasm` is Luanti compiled to run in a web browser. There are two
halves to it: the engine itself, compiled with emscripten, and the launcher
page in front of it. One script builds both.

Apply the patch first, so the launcher is built with it already in place.
Without the patch the site has one address, a launcher screen where you
pick a game from a list and press "Start Game". With it there are two:

- `/` — that same launcher screen, unchanged.
- `/mineclonia` — picks Mineclonia, waits for it to load and presses Start
  for you, so the page opens straight on Luanti's main menu.

    cd minetest-wasm
    git apply ../patches/minetest-wasm-autostart.patch

Now build. This is the long step: it compiles Luanti inside a container,
and on the first run it installs emscripten too. Your user needs to be in
the `docker` group and to own this folder.

    ./build_all_with_docker.sh

The finished client lands in `minetest-wasm/www/`. Copy it into the `www/`
folder this stack serves:

    cd ..
    mkdir -p www
    cp -a minetest-wasm/www/. www/

If you later change only the launcher, `./update_build_static.sh` rebuilds
that part on its own, and you copy it across the same way. The engine does
not need rebuilding for launcher changes.

### Step 4 — set your server options

`minetest.conf.example` is a starting point. Copy it into `config/` and edit
it: the admin name, what the server is called, and what new players are
allowed to do.

    mkdir -p config
    cp minetest.conf.example config/minetest.conf

Your own `config/minetest.conf` is never committed to git, so the `config`
folder does not exist until you make it.

### Step 5 — start everything

The server runs as user and group 30000 inside its container, and writes
the world to `data/`. Make that folder yourself first and give it to that
user, otherwise Docker creates it owned by root and the server cannot save
anything:

    mkdir -p data/.minetest/worlds/world www
    sudo chown -R 30000:30000 data

    docker compose up -d

### Step 6 — check it

Open the site in a browser. `/` is the launcher, `/mineclonia` starts the
game by itself, and `/antichunk/` is the map. Desktop Luanti clients can
connect on `<your server>` port 30000, which `compose.yml` publishes over
UDP.

## The seed map

Antichunk shows your world as a map. From the seed alone it can draw the
terrain, and if it can also read the world's `map.sqlite` it draws what
players have really explored and built.

To let it do that, two files from the world folder are published next to
Antichunk:

- `map_meta.txt` — tiny, holds the world's seed and map generator.
- `map.sqlite` — the explored map itself.

`nginx.conf` lists those two by their exact names, so nothing else in the
world folder can be fetched. That matters: the same folder holds
`auth.sqlite`, which contains your players' password hashes.

    location = /antichunk/world/map_meta.txt { alias /usr/share/nginx/world/map_meta.txt; }
    location = /antichunk/world/map.sqlite   { alias /usr/share/nginx/world/map.sqlite; }

Anyone who can open those two addresses can download your entire explored
map. If your site is reachable from the internet, limit them to your own
network on whatever proxy sits in front of this stack. With nginx that
looks like this, with your own address range and host:

    location /antichunk/world/ {
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://192.0.2.10:8081;
    }

The map page itself stays public. Only those two files are restricted, so
visitors still see the terrain from the seed, just not where anyone has
been.

## Gotcha

The proxy shares the luanti container's network namespace, so recreating or
restarting **luanti** leaves the proxy without a network and every browser
client gets a 502. Always follow with:

    docker compose up -d --force-recreate proxy
