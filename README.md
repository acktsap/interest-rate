# Interest Rate

## Source

- [금융투자협회 채권정보센터](https://www.kofiabond.or.kr/)
    - 시가평가 -> 채권시가평가수익률
    - 금융채 I(은행채) / 무보증 / AAA (6월, 5년)
    - 국고채 (1년, 3년, 5년, 10년)
    - 나이스피앤아이 + 한국자산평가 2개사 평균

## Features

- **한국 국채 및 금융채 금리 통합 지원**: 국채 1년, 3년, 5년, 10년물 및 금융채 6월, 5년물
- **체크리스트(Checklist) 선택 기능**: 원하는 금리 시리즈만 선택하여 차트에 표시/숨김
- **빠른 필터 버튼**: `전체`, `국채만`, `금융채만` 간편 전환
- **설정 저장**: 선택한 체크리스트 상태가 `localStorage`에 자동 저장되어 브라우저 재방문 시 유지

## Usage

Python 3.10 이상이면 별도 패키지 설치 없이 실행된다.

```bash
python3 --version
```

Python이 없으면 설치한다.

```bash
# macOS
brew install python
```

데이터 원본은 `rate.csv`다. 누락 데이터만 추가하려면:

```bash
python3 update_rates.py
```

과거 국채/금융채 누락 데이터 전체를 백필하려면:

```bash
python3 update_rates.py --backfill
```

차트를 다시 만들려면:

```bash
python3 plot_chart.py --no-open
```

차트를 만들고 브라우저에서 바로 열려면:

```bash
python3 plot_chart.py
```

이미 만들어진 HTML만 브라우저에서 열려면:

```bash
./open_chart.sh
```

파일 변경 없이 확인만 하려면:

```bash
python3 update_rates.py --dry-run
```

## GitHub Pages

GitHub에서 `Settings` -> `Pages` -> `Source`를 `GitHub Actions`로 설정한다.

배포 후 차트는 아래 주소에서 볼 수 있다.

[https://acktsap.github.io/interest-rate/](https://acktsap.github.io/interest-rate/)
