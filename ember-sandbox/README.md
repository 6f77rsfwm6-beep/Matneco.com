# Ember sandbox (Stash test server)

A throwaway [Stash](https://github.com/stashapp/stash) server with a small, fake, safe-for-work video library, for testing Ember. One `docker compose up` gives you:

- **12 generated test videos** (test patterns with a title and a running clock burned in), at 360p, 480p, 720p, 1080p, 4K and one vertical 720×1280
- **6 performers, 4 studios** (one is a sub-studio), **11 tags** (some nested), **2 groups** with ordered scenes, **5 scene markers**, ratings, dates and URLs
- Covers, hover previews, scrubber sprites and phashes, already generated
- Edge cases: a long Unicode/emoji title, an untouched scene with no metadata, and one scene with resume position and play history
- A login, plus an **API key for Ember**, printed when seeding finishes

Everything is fictional and generated locally. No real media is downloaded. The library is about 60 MB.

## Start it

```sh
cd ember-sandbox
cp .env.example .env
```

Edit `.env` and set `STASH_PASSWORD` (and `STASH_PUBLIC_URL` if testers reach it by another address), then:

```sh
docker compose up -d --build
```

```sh
docker compose logs -f seed
```

The first run takes about 5–10 minutes (it renders the videos, then Stash builds previews). It ends by printing the connection details, which are also saved to `volumes/out/ember-connection.txt`.

Ember sends the key in the `ApiKey` header:

```sh
curl -H "ApiKey: <key>" -H "Content-Type: application/json" \
  -d '{"query":"{ stats { scene_count } }"}' http://localhost:9999/graphql
```

## Reset after testing

Puts the server back to its freshly seeded state. The old API key stops working, and the reset prints a new one.

```sh
./reset.sh
```

`./reset.sh --full` also deletes and re-renders the test videos.

## Sharing it with testers

Stash has a single login. Every tester uses the same username, password and API key, so everyone sees the same library and any edits they make. Run `./reset.sh` between test rounds.

- **Tailscale (recommended for a few people):** run it on a machine on your tailnet and share that machine with each tester. They connect to `http://<machine-name>:9999`. Nothing is exposed to the internet.
- **Cloudflare Tunnel:** for testers without Tailscale. Create a tunnel in the Cloudflare Zero Trust dashboard that points a hostname (e.g. `stash-sandbox.matneco.com`) at `http://stash:9999`. Put its token in `CLOUDFLARE_TUNNEL_TOKEN` in `.env`, then:

  ```sh
  docker compose --profile tunnel up -d
  ```

  Consider adding a Cloudflare Access policy in front of it, so only your testers' emails can reach the login page.

## Files

| Path | What it is |
|------|------------|
| `docker-compose.yml` | Stash, the one-shot seeder, and the optional tunnel |
| `seed/seed.py` | Builds the videos and metadata through Stash's GraphQL API. Edit the lists at the top to change the catalogue |
| `reset.sh` | Wipes state and re-seeds |
| `volumes/` | All data (git-ignored) |

To make sure all testers hit the same Stash version, pin `STASH_IMAGE_TAG` in `.env` (verified against `v0.31.1`).
