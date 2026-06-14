#!/usr/bin/env sh
set -eu

html_file="${1:-chart.html}"

if [ ! -f "$html_file" ]; then
  echo "$html_file 파일이 없습니다. 먼저 python3 plot_chart.py --no-open 을 실행하세요." >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin)
    open "$html_file"
    ;;
  Linux)
    xdg-open "$html_file"
    ;;
  *)
    echo "브라우저 열기 명령을 알 수 없습니다: $(uname -s)" >&2
    echo "$html_file" >&2
    exit 1
    ;;
esac
