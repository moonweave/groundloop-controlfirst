#!/usr/bin/env bash
set -euo pipefail

entry_image="${1:?entry screenshot path required}"
report_image="${2:?report screenshot path required}"
output_path="${3:-artifacts/demo-previsual/groundloop-motion-previsual.mp4}"
asset_dir="artifacts/demo-previsual"

mkdir -p "$(dirname "$output_path")"
magick -background none "$asset_dir/title.svg" "$asset_dir/title.png"
magick -background none "$asset_dir/outro.svg" "$asset_dir/outro.png"
magick -background none "$asset_dir/mcp-proof.svg" "$asset_dir/mcp-proof.png"
magick -background none "$asset_dir/cursor.svg" "$asset_dir/cursor.png"

ffmpeg -y \
  -loop 1 -framerate 30 -t 3 -i "$asset_dir/title.png" \
  -loop 1 -framerate 30 -t 8 -i "$entry_image" \
  -loop 1 -framerate 30 -t 6 -i "$asset_dir/mcp-proof.png" \
  -loop 1 -framerate 30 -t 14 -i "$report_image" \
  -loop 1 -framerate 30 -t 4 -i "$asset_dir/outro.png" \
  -loop 1 -framerate 30 -t 8 -i "$asset_dir/cursor.png" \
  -filter_complex "
    [0:v]scale=1280:720,setsar=1[title];
    [1:v]scale=1600:852,setsar=1,crop=1280:720:160:66[entryraw];
    [5:v]scale=54:54[dot];
    [entryraw][dot]overlay=x='160+160*t':y='565-18*t':enable='between(t,1.1,4.2)'[entry];
    [2:v]scale=1280:720,setsar=1[mcp];
    [3:v]scale=1600:852,setsar=1,crop=1280:720:160:72[reportraw];
    [reportraw]zoompan=z='min(zoom+0.00045,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=420:s=1280x720:fps=30[report];
    [4:v]scale=1280:720,setsar=1[outro];
    [title][entry]xfade=transition=fade:duration=0.45:offset=2.55[a];
    [a][mcp]xfade=transition=fade:duration=0.45:offset=10.1[b];
    [b][report]xfade=transition=fade:duration=0.45:offset=15.65[c];
    [c][outro]xfade=transition=fade:duration=0.45:offset=29.2[final]
  " \
  -map "[final]" -t 33 -r 30 -pix_fmt yuv420p -movflags +faststart "$output_path"
