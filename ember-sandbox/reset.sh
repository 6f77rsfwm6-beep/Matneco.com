#!/usr/bin/env sh
# Put the sandbox back to its freshly seeded state.
#   ./reset.sh          wipe Stash's database and settings, keep the generated test videos (fast)
#   ./reset.sh --full   wipe everything, including the test videos
set -e
cd "$(dirname "$0")"

docker compose down
rm -rf volumes/config volumes/metadata volumes/cache volumes/blobs volumes/generated volumes/out
if [ "$1" = "--full" ]; then
  rm -rf volumes/media
fi
docker compose up -d --build
docker compose logs -f seed
