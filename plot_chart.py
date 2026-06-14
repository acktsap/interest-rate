import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

parser = argparse.ArgumentParser(description='금융채 금리 차트 HTML 생성')
parser.add_argument('--data', default='rate.csv', help='읽을 CSV 데이터 파일')
parser.add_argument('--no-open', action='store_true', help='chart.html 생성 후 브라우저를 열지 않음')
args = parser.parse_args()

data_path = Path(args.data)

rows = []
with data_path.open('r', encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            day = datetime.strptime(row['일자'], '%Y/%m/%d')
            rate_6m = float(row['6월'])
            rate_5y = float(row['5년'])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append((day, rate_6m, rate_5y))

rows.sort(key=lambda item: item[0])
if len(rows) < 2:
    raise RuntimeError(f'{data_path}에 차트를 만들 데이터가 부족합니다.')

data_6m = [
    {'time': day.strftime('%Y-%m-%d'), 'value': rate_6m}
    for day, rate_6m, _ in rows
]
data_5y = [
    {'time': day.strftime('%Y-%m-%d'), 'value': rate_5y}
    for day, _, rate_5y in rows
]

# 최신/전일 데이터
last_6m = data_6m[-1]['value']
prev_6m = data_6m[-2]['value']
change_6m = last_6m - prev_6m

last_5y = data_5y[-1]['value']
prev_5y = data_5y[-2]['value']
change_5y = last_5y - prev_5y

# HTML 템플릿 (TradingView lightweight-charts)
html_template = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>금융채 금리 차트</title>
    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: #131722;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}
        #header {{
            background: #1e222d;
            padding: 12px 20px;
            border-bottom: 1px solid #2a2e39;
            display: flex;
            align-items: center;
            gap: 24px;
        }}
        #title {{
            color: #d1d4dc;
            font-size: 16px;
            font-weight: 600;
        }}
        .series-info {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .series-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }}
        .series-label {{
            color: #787b86;
            font-size: 13px;
        }}
        .series-price {{
            font-size: 20px;
            font-weight: 700;
        }}
        .series-change {{
            font-size: 12px;
            padding: 2px 6px;
            border-radius: 4px;
        }}
        .positive {{ color: #26a69a; }}
        .negative {{ color: #ef5350; }}
        .positive-bg {{ background: #26a69a22; color: #26a69a; }}
        .negative-bg {{ background: #ef535022; color: #ef5350; }}
        #chart {{
            width: 100%;
            height: calc(100vh - 60px);
        }}
        #legend {{
            position: absolute;
            top: 80px;
            left: 20px;
            color: #d1d4dc;
            font-size: 12px;
            z-index: 10;
        }}
    </style>
</head>
<body>
    <div id="header">
        <div id="title">금융채 AAA 무보증</div>
        <div class="series-info">
            <span class="series-dot" style="background: #2962FF;"></span>
            <span class="series-label">6월</span>
            <span class="series-price" style="color: #2962FF;">{last_6m:.3f}%</span>
            <span class="series-change {'positive-bg' if change_6m >= 0 else 'negative-bg'}">{'+' if change_6m >= 0 else ''}{change_6m:.3f}</span>
        </div>
        <div class="series-info">
            <span class="series-dot" style="background: #FF6D00;"></span>
            <span class="series-label">5년</span>
            <span class="series-price" style="color: #FF6D00;">{last_5y:.3f}%</span>
            <span class="series-change {'positive-bg' if change_5y >= 0 else 'negative-bg'}">{'+' if change_5y >= 0 else ''}{change_5y:.3f}</span>
        </div>
    </div>
    <div id="legend"></div>
    <div id="chart"></div>

    <script>
        const data6m = {json.dumps(data_6m)};
        const data5y = {json.dumps(data_5y)};

        const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
            layout: {{
                background: {{ type: 'solid', color: '#131722' }},
                textColor: '#d1d4dc',
            }},
            grid: {{
                vertLines: {{ color: '#1e222d' }},
                horzLines: {{ color: '#1e222d' }},
            }},
            crosshair: {{
                mode: LightweightCharts.CrosshairMode.Normal,
                vertLine: {{
                    width: 1,
                    color: '#758696',
                    style: LightweightCharts.LineStyle.Dashed,
                    labelBackgroundColor: '#2a2e39',
                }},
                horzLine: {{
                    width: 1,
                    color: '#758696',
                    style: LightweightCharts.LineStyle.Dashed,
                    labelBackgroundColor: '#2a2e39',
                }},
            }},
            rightPriceScale: {{
                borderColor: '#2a2e39',
                scaleMargins: {{
                    top: 0.1,
                    bottom: 0.1,
                }},
            }},
            timeScale: {{
                borderColor: '#2a2e39',
                timeVisible: true,
                secondsVisible: false,
            }},
            handleScroll: {{
                mouseWheel: true,
                pressedMouseMove: true,
                horzTouchDrag: true,
                vertTouchDrag: true,
            }},
            handleScale: {{
                axisPressedMouseMove: true,
                mouseWheel: true,
                pinch: true,
            }},
        }});

        // 6월물 시리즈 (파란색)
        const series6m = chart.addSeries(LightweightCharts.AreaSeries, {{
            lineColor: '#2962FF',
            topColor: 'rgba(41, 98, 255, 0.3)',
            bottomColor: 'rgba(41, 98, 255, 0.0)',
            lineWidth: 2,
            priceFormat: {{
                type: 'price',
                precision: 3,
                minMove: 0.001,
            }},
        }});
        series6m.setData(data6m);

        // 5년물 시리즈 (주황색)
        const series5y = chart.addSeries(LightweightCharts.LineSeries, {{
            color: '#FF6D00',
            lineWidth: 2,
            priceFormat: {{
                type: 'price',
                precision: 3,
                minMove: 0.001,
            }},
        }});
        series5y.setData(data5y);

        // 크로스헤어 이동 시 값 표시
        chart.subscribeCrosshairMove((param) => {{
            const legend = document.getElementById('legend');
            if (param.time) {{
                const price6m = param.seriesData.get(series6m);
                const price5y = param.seriesData.get(series5y);
                let html = '';
                if (price6m) {{
                    html += `<span style="color: #2962FF">●</span> 6월: ${{price6m.value.toFixed(3)}}%&nbsp;&nbsp;`;
                }}
                if (price5y) {{
                    html += `<span style="color: #FF6D00">●</span> 5년: ${{price5y.value.toFixed(3)}}%`;
                }}
                legend.innerHTML = html;
            }} else {{
                legend.innerHTML = '';
            }}
        }});

        // 차트 크기 자동 조절
        window.addEventListener('resize', () => {{
            chart.applyOptions({{
                width: window.innerWidth,
                height: window.innerHeight - 60
            }});
        }});

        chart.timeScale().fitContent();
    </script>
</body>
</html>'''

# HTML 파일 저장
with open('chart.html', 'w', encoding='utf-8') as f:
    f.write(html_template)

print('차트가 chart.html로 저장되었습니다.')

# 브라우저에서 열기
if not args.no_open:
    import webbrowser
    webbrowser.open('chart.html')
