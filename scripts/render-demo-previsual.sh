#!/usr/bin/env bash
set -euo pipefail

entry_image="${1:?entry screenshot path required}"
report_image="${2:?report screenshot path required}"
output_path="${3:-artifacts/demo-previsual/groundloop-previsual.mp4}"
asset_dir="artifacts/demo-previsual"

mkdir -p "$(dirname "$output_path")"
magick -background none "$asset_dir/title.svg" "$asset_dir/title.png"
magick -background none "$asset_dir/outro.svg" "$asset_dir/outro.png"

ffmpeg -y \
  -loop 1 -framerate 30 -t 4 -i "$asset_dir/title.png" \
  -loop 1 -framerate 30 -t 9 -i "$entry_image" \
  -loop 1 -framerate 30 -t 12 -i "$report_image" \
  -loop 1 -framerate 30 -t 4 -i "$asset_dir/outro.png" \
  -filter_complex "
    [0:v]scale=1280:720,setsar=1[title];
    [1:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=#fcfdfb,setsar=1[entry];
    [2:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=#fcfdfb,setsar=1[report];
    [3:v]scale=1280:720,setsar=1[outro];
    [title][entry]xfade=transition=fade:duration=0.55:offset=3.45[a];
    [a][report]xfade=transition=fade:duration=0.55:offset=11.9[b];
    [b][outro]xfade=transition=fade:duration=0.55:offset=23.35[final]
  " \
  -map "[final]" -t 27 -r 30 -pix_fmt yuv420p -movflags +faststart "$output_path"
