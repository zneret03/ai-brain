#!/usr/bin/env bash
# Turns a recorded browser run into the .mp4 and .gif a Jira comment carries: cuts the blank page before
# each first paint, joins a media/ folder's videos in recording order, and can open on a title card.
# Usage: media.sh <video.webm | media-dir> <out-prefix> ["Title line" ["Second line"]]
set -euo pipefail

in="${1:?usage: media.sh <video.webm | media-dir> <out-prefix> [title [subtitle]]}"
out="${2:?usage: media.sh <video.webm | media-dir> <out-prefix> [title [subtitle]]}"
title="${3:-}"
subtitle="${4:-}"
font=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf

if [ -d "$in" ]; then
  mapfile -t inputs < <(ls -tr "$in"/*.webm)
else
  inputs=("$in")
fi
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

size=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "${inputs[0]}")
encode=(-an -c:v libx264 -preset veryfast -crf 22 -pix_fmt yuv420p -r 25)

: > "$work/list.txt"
if [ -n "$title" ]; then
  # Single quotes and colons are drawtext syntax, so strip them from the visible text.
  t=${title//[\':]/}
  s=${subtitle//[\':]/}
  ffmpeg -hide_banner -loglevel error -y -f lavfi -i "color=c=0x1f2937:s=$size:d=3" \
    -vf "drawtext=fontfile=$font:text='$t':fontcolor=white:fontsize=h/20:x=(w-text_w)/2:y=h/2-text_h,drawtext=fontfile=$font:text='$s':fontcolor=0xd1d5db:fontsize=h/32:x=(w-text_w)/2:y=h/2+text_h" \
    "${encode[@]}" "$work/title.mp4"
  echo "file '$work/title.mp4'" >> "$work/list.txt"
fi

for i in "${!inputs[@]}"; do
  # A blank frame is pure white, so negated it is black and blackdetect finds the lead-in. The app's
  # grey background stays above pix_th, which keeps rendered frames out of it.
  lead=$(ffmpeg -hide_banner -nostats -i "${inputs[$i]}" -vf "negate,blackdetect=d=0.1:pic_th=0.995:pix_th=0.02" -an -f null - 2>&1 \
    | awk -F'[: ]+' '/black_start/ {
        for (j = 1; j <= NF; j++) { if ($j == "black_start") s = $(j + 1); if ($j == "black_end") e = $(j + 1) }
        if (s + 0 < 0.05) print e
        exit
      }')
  ffmpeg -hide_banner -loglevel error -y -ss "${lead:-0}" -i "${inputs[$i]}" "${encode[@]}" "$work/part$i.mp4"
  echo "file '$work/part$i.mp4'" >> "$work/list.txt"
  echo "segment $((i + 1)): cut ${lead:-0}s of blank lead-in"
done

ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$work/list.txt" -c copy -movflags +faststart "$out.mp4"

# A long walkthrough at full rate makes a GIF too heavy to embed, so it drops frames instead of detail.
duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out.mp4")
fps=$(awk -v d="$duration" 'BEGIN { print (d > 60) ? 5 : 8 }')
ffmpeg -hide_banner -loglevel error -y -i "$out.mp4" \
  -vf "fps=$fps,scale=800:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  -loop 0 "$out.gif"

echo "size $size, ${duration%.*}s"
ls -lh "$out.mp4" "$out.gif" | awk '{ print $5, $NF }'
