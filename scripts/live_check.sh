#!/usr/bin/env bash
# Poll the deployed FoodSafe Central page until it byte-matches the local build.
cd "$HOME/projects/foodsafe-central" || exit 1
T="$LOCALAPPDATA/Temp"
local_md5=$(tr -d '\r' < index.html | md5sum | cut -d' ' -f1)
echo "local md5: $local_md5"
for i in 1 2 3 4 5 6 7 8; do
  sleep 20
  curl -s -A "Mozilla/5.0" "https://nwfella.github.io/foodsafe-central/?v=$(date +%s)" -o "$T/fs_live2.html"
  live_md5=$(tr -d '\r' < "$T/fs_live2.html" | md5sum | cut -d' ' -f1)
  gen=$(grep -o '"generated_at": "[^"]*"' "$T/fs_live2.html" | head -1)
  if [ "$local_md5" = "$live_md5" ]; then echo "poll $i: CONVERGED $gen"; break; fi
  echo "poll $i: no match | size=$(wc -c < "$T/fs_live2.html") $gen"
done
