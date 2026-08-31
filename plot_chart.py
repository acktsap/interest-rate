import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

parser = argparse.ArgumentParser(description='한국 국채 및 금융채 금리 차트 HTML 생성')
parser.add_argument('--data', default='rate.csv', help='읽을 CSV 데이터 파일')
parser.add_argument('--no-open', action='store_true', help='chart.html 생성 후 브라우저를 열지 않음')
args = parser.parse_args()

data_path = Path(args.data)

SERIES_DEFINITIONS = [
    {'key': 'bank_6m', 'label': '금융채 6월', 'cols': ['금융채 6월', '6월'], 'color': '#2962FF', 'group': '금융채', 'default_on': True},
    {'key': 'bank_5y', 'label': '금융채 5년', 'cols': ['금융채 5년', '5년'], 'color': '#FF6D00', 'group': '금융채', 'default_on': True},
    {'key': 'gov_1y',  'label': '국채 1년',   'cols': ['국채 1년'],           'color': '#00E676', 'group': '국채',   'default_on': False},
    {'key': 'gov_3y',  'label': '국채 3년',   'cols': ['국채 3년'],           'color': '#E040FB', 'group': '국채',   'default_on': True},
    {'key': 'gov_5y',  'label': '국채 5년',   'cols': ['국채 5년'],           'color': '#00E5FF', 'group': '국채',   'default_on': False},
    {'key': 'gov_10y', 'label': '국채 10년',  'cols': ['국채 10년'],          'color': '#FFD600', 'group': '국채',   'default_on': True},
]

rows = []
with data_path.open('r', encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            day = datetime.strptime(row['일자'], '%Y/%m/%d')
        except (KeyError, ValueError):
            continue

        item = {'day': day}
        for s_def in SERIES_DEFINITIONS:
            val = None
            for cname in s_def['cols']:
                raw = row.get(cname)
                if raw and raw.strip() and raw.strip() != '-':
                    try:
                        val = float(raw.strip())
                        break
                    except ValueError:
                        pass
            item[s_def['key']] = val

        rows.append(item)

rows.sort(key=lambda r: r['day'])

if len(rows) < 2:
    raise RuntimeError(f'{data_path}에 차트를 만들 데이터가 부족합니다.')

# Build data series array for each series
series_data_map = {}
series_info_map = {}

for s_def in SERIES_DEFINITIONS:
    s_key = s_def['key']
    data_points = [
        {'time': r['day'].strftime('%Y-%m-%d'), 'value': r[s_key]}
        for r in rows
        if r[s_key] is not None
    ]
    series_data_map[s_key] = data_points

    if len(data_points) >= 2:
        last_val = data_points[-1]['value']
        prev_val = data_points[-2]['value']
        change_val = last_val - prev_val
    elif len(data_points) == 1:
        last_val = data_points[-1]['value']
        change_val = 0.0
    else:
        last_val = None
        change_val = None

    series_info_map[s_key] = {
        'key': s_key,
        'label': s_def['label'],
        'color': s_def['color'],
        'group': s_def['group'],
        'last': last_val,
        'change': change_val,
    }

# HTML Template with Lightweight Charts & Dropdown Selection UI
html_template = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>한국 국채 & 금융채 금리 차트</title>
    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            margin: 0;
            padding: 0;
            background: #131722;
            color: #d1d4dc;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif;
            overflow-x: hidden;
        }}
        #header {{
            background: #1e222d;
            padding: 10px 20px;
            border-bottom: 1px solid #2a2e39;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            height: 56px;
        }}
        .brand-section {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        #title {{
            color: #ffffff;
            font-size: 17px;
            font-weight: 700;
            letter-spacing: -0.3px;
        }}
        .badge {{
            background: #2a2e39;
            color: #9db2c6;
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 12px;
            font-weight: 500;
        }}
        
        /* Dropdown Styling */
        .dropdown-wrapper {{
            position: relative;
        }}
        .dropdown-btn {{
            background: #131722;
            border: 1px solid #2a2e39;
            color: #d1d4dc;
            padding: 7px 14px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
            user-select: none;
        }}
        .dropdown-btn:hover {{
            background: #191e2b;
            border-color: #434651;
            color: #ffffff;
        }}
        .count-badge {{
            background: #2962FF;
            color: #ffffff;
            font-size: 11px;
            padding: 2px 7px;
            border-radius: 10px;
            font-weight: 700;
        }}
        .caret-icon {{
            font-size: 10px;
            color: #787b86;
            transition: transform 0.2s ease;
        }}
        .dropdown-wrapper.open .caret-icon {{
            transform: rotate(180deg);
        }}
        
        .dropdown-menu {{
            position: absolute;
            top: calc(100% + 8px);
            right: 0;
            width: 320px;
            background: rgba(30, 34, 45, 0.96);
            backdrop-filter: blur(12px);
            border: 1px solid #2a2e39;
            border-radius: 12px;
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5);
            z-index: 1000;
            display: none;
            overflow: hidden;
            animation: fadeIn 0.15s ease-out;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(-6px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .dropdown-wrapper.open .dropdown-menu {{
            display: block;
        }}
        
        .dropdown-header {{
            padding: 12px 14px;
            border-bottom: 1px solid #2a2e39;
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(19, 23, 34, 0.5);
        }}
        .dropdown-title {{
            font-size: 12px;
            font-weight: 700;
            color: #787b86;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .filter-btn-group {{
            display: flex;
            gap: 2px;
            background: #131722;
            padding: 2px;
            border-radius: 6px;
            border: 1px solid #2a2e39;
        }}
        .filter-btn {{
            background: transparent;
            border: none;
            color: #787b86;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 600;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .filter-btn:hover {{
            color: #d1d4dc;
        }}
        .filter-btn.active {{
            background: #2a2e39;
            color: #ffffff;
        }}
        
        .dropdown-body {{
            padding: 10px;
            max-height: 420px;
            overflow-y: auto;
        }}
        .group-title {{
            font-size: 11px;
            font-weight: 700;
            color: #9db2c6;
            padding: 6px 8px 4px;
            letter-spacing: 0.3px;
        }}
        .group-items {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}
        
        .checklist-item {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 10px;
            border-radius: 8px;
            cursor: pointer;
            user-select: none;
            transition: background 0.15s ease;
        }}
        .checklist-item:hover {{
            background: #2a2e39;
        }}
        .item-left {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .checklist-item input[type="checkbox"] {{
            appearance: none;
            -webkit-appearance: none;
            width: 16px;
            height: 16px;
            border: 1.5px solid #434651;
            border-radius: 4px;
            outline: none;
            cursor: pointer;
            position: relative;
            margin: 0;
            transition: background 0.15s ease, border-color 0.15s ease;
        }}
        .checklist-item input[type="checkbox"]:checked {{
            background-color: var(--series-color);
            border-color: var(--series-color);
        }}
        .checklist-item input[type="checkbox"]:checked::after {{
            content: '';
            position: absolute;
            left: 4px;
            top: 1px;
            width: 4px;
            height: 8px;
            border: solid #ffffff;
            border-width: 0 2px 2px 0;
            transform: rotate(45deg);
        }}
        .series-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }}
        .series-label {{
            font-size: 13px;
            font-weight: 600;
            color: #d1d4dc;
        }}
        .item-right {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .series-price {{
            font-size: 13px;
            font-weight: 700;
        }}
        .series-change {{
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 600;
        }}
        .positive-bg {{ background: rgba(38, 166, 154, 0.15); color: #26a69a; }}
        .negative-bg {{ background: rgba(239, 83, 80, 0.15); color: #ef5350; }}
        .neutral-bg {{ background: rgba(120, 123, 134, 0.15); color: #787b86; }}

        #chart-container {{
            position: relative;
            width: 100%;
            height: calc(100vh - 56px);
        }}
        #chart {{
            width: 100%;
            height: 100%;
        }}
        #legend {{
            position: absolute;
            top: 16px;
            left: 20px;
            color: #d1d4dc;
            font-size: 13px;
            z-index: 10;
            background: rgba(30, 34, 45, 0.85);
            backdrop-filter: blur(8px);
            padding: 8px 14px;
            border-radius: 8px;
            border: 1px solid rgba(42, 46, 57, 0.8);
            pointer-events: none;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 4px;
        }}
    </style>
</head>
<body>
    <div id="header">
        <div class="brand-section">
            <div id="title">금리 차트</div>
            <span class="badge">국채 & 금융채 AAA</span>
        </div>
        
        <div class="dropdown-wrapper" id="dropdown-wrapper">
            <button class="dropdown-btn" id="dropdown-btn">
                <span>📊</span>
                <span>금리 항목 선택</span>
                <span class="count-badge" id="selected-count-badge">4/6</span>
                <span class="caret-icon">▾</span>
            </button>
            
            <div class="dropdown-menu" id="dropdown-menu">
                <div class="dropdown-header">
                    <span class="dropdown-title">표시 항목</span>
                    <div class="filter-btn-group">
                        <button class="filter-btn" id="btn-all" onclick="applyPreset('all')">전체</button>
                        <button class="filter-btn" id="btn-gov" onclick="applyPreset('gov')">국채만</button>
                        <button class="filter-btn" id="btn-bank" onclick="applyPreset('bank')">금융채만</button>
                    </div>
                </div>
                <div class="dropdown-body">
                    <div class="group-title">🏦 금융채 AAA</div>
                    <div class="group-items" id="group-bank"></div>
                    
                    <div class="group-title" style="margin-top: 8px;">🇰🇷 한국 국채</div>
                    <div class="group-items" id="group-gov"></div>
                </div>
            </div>
        </div>
    </div>
    
    <div id="chart-container">
        <div id="legend"></div>
        <div id="chart"></div>
    </div>

    <script>
        const seriesDefinitions = {json.dumps(SERIES_DEFINITIONS)};
        const seriesDataMap = {json.dumps(series_data_map)};
        const seriesInfoMap = {json.dumps(series_info_map)};

        const STORAGE_KEY = 'interest_rate_checklist_v2';

        function loadChecklistState() {{
            try {{
                const saved = localStorage.getItem(STORAGE_KEY);
                if (saved) return JSON.parse(saved);
            }} catch (e) {{
                console.error(e);
            }}
            const defaultState = {{}};
            seriesDefinitions.forEach(s => defaultState[s.key] = !!s.default_on);
            return defaultState;
        }}

        function saveChecklistState(state) {{
            try {{
                localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
            }} catch (e) {{
                console.error(e);
            }}
        }}

        const currentVisibilityState = loadChecklistState();

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

        const chartSeriesMap = {{}};

        seriesDefinitions.forEach(s => {{
            const isVisible = currentVisibilityState[s.key] !== false;
            const series = chart.addSeries(LightweightCharts.LineSeries, {{
                color: s.color,
                lineWidth: 2,
                title: s.label,
                visible: isVisible,
                priceFormat: {{
                    type: 'price',
                    precision: 3,
                    minMove: 0.001,
                }},
            }});
            series.setData(seriesDataMap[s.key] || []);
            chartSeriesMap[s.key] = series;
        }});

        // Build Dropdown Items
        const groupBankContainer = document.getElementById('group-bank');
        const groupGovContainer = document.getElementById('group-gov');

        seriesDefinitions.forEach(s => {{
            const info = seriesInfoMap[s.key] || {{}};
            const isChecked = currentVisibilityState[s.key] !== false;

            const item = document.createElement('label');
            item.className = 'checklist-item';
            item.style.setProperty('--series-color', s.color);

            const left = document.createElement('div');
            left.className = 'item-left';

            const chk = document.createElement('input');
            chk.type = 'checkbox';
            chk.checked = isChecked;
            chk.id = `chk-${{s.key}}`;

            chk.addEventListener('change', (e) => {{
                const checked = e.target.checked;
                currentVisibilityState[s.key] = checked;
                chartSeriesMap[s.key].applyOptions({{ visible: checked }});
                saveChecklistState(currentVisibilityState);
                updateUIState();
            }});

            const dot = document.createElement('span');
            dot.className = 'series-dot';
            dot.style.background = s.color;

            const label = document.createElement('span');
            label.className = 'series-label';
            label.textContent = s.label;

            left.appendChild(chk);
            left.appendChild(dot);
            left.appendChild(label);

            const right = document.createElement('div');
            right.className = 'item-right';

            if (info.last !== null && info.last !== undefined) {{
                const priceSpan = document.createElement('span');
                priceSpan.className = 'series-price';
                priceSpan.style.color = s.color;
                priceSpan.textContent = `${{info.last.toFixed(3)}}%`;
                right.appendChild(priceSpan);

                if (info.change !== null && info.change !== undefined) {{
                    const sign = info.change >= 0 ? '+' : '';
                    const cls = info.change > 0 ? 'positive-bg' : (info.change < 0 ? 'negative-bg' : 'neutral-bg');
                    const changeSpan = document.createElement('span');
                    changeSpan.className = `series-change ${{cls}}`;
                    changeSpan.textContent = `${{sign}}${{info.change.toFixed(3)}}`;
                    right.appendChild(changeSpan);
                }}
            }}

            item.appendChild(left);
            item.appendChild(right);

            if (s.group === '금융채') {{
                groupBankContainer.appendChild(item);
            }} else {{
                groupGovContainer.appendChild(item);
            }}
        }});

        // Dropdown toggle & click outside logic
        const dropdownWrapper = document.getElementById('dropdown-wrapper');
        const dropdownBtn = document.getElementById('dropdown-btn');

        dropdownBtn.addEventListener('click', (e) => {{
            e.stopPropagation();
            dropdownWrapper.classList.toggle('open');
        }});

        document.addEventListener('click', (e) => {{
            if (!dropdownWrapper.contains(e.target)) {{
                dropdownWrapper.classList.remove('open');
            }}
        }});

        function applyPreset(preset) {{
            seriesDefinitions.forEach(s => {{
                let targetState = true;
                if (preset === 'gov') {{
                    targetState = s.group === '국채';
                }} else if (preset === 'bank') {{
                    targetState = s.group === '금융채';
                }} else {{
                    targetState = true;
                }}
                currentVisibilityState[s.key] = targetState;
                const chk = document.getElementById(`chk-${{s.key}}`);
                if (chk) chk.checked = targetState;
                if (chartSeriesMap[s.key]) {{
                    chartSeriesMap[s.key].applyOptions({{ visible: targetState }});
                }}
            }});
            saveChecklistState(currentVisibilityState);
            updateUIState();
        }}

        function updateUIState() {{
            const totalCount = seriesDefinitions.length;
            const checkedCount = seriesDefinitions.filter(s => currentVisibilityState[s.key] !== false).length;

            document.getElementById('selected-count-badge').textContent = `${{checkedCount}}/${{totalCount}}`;

            const govKeys = seriesDefinitions.filter(s => s.group === '국채').map(s => s.key);
            const bankKeys = seriesDefinitions.filter(s => s.group === '금융채').map(s => s.key);

            const allGovChecked = govKeys.every(k => currentVisibilityState[k] !== false);
            const allGovUnchecked = govKeys.every(k => currentVisibilityState[k] === false);
            const allBankChecked = bankKeys.every(k => currentVisibilityState[k] !== false);
            const allBankUnchecked = bankKeys.every(k => currentVisibilityState[k] === false);

            document.getElementById('btn-all').classList.toggle('active', allGovChecked && allBankChecked);
            document.getElementById('btn-gov').classList.toggle('active', allGovChecked && allBankUnchecked);
            document.getElementById('btn-bank').classList.toggle('active', allGovUnchecked && allBankChecked);
        }}

        updateUIState();

        // Crosshair move handler to update floating legend
        chart.subscribeCrosshairMove((param) => {{
            const legend = document.getElementById('legend');
            if (param.time) {{
                let itemsHtml = `<div class="legend-item" style="color: #9db2c6; font-weight: 600; margin-right: 4px;">${{param.time}}</div>`;
                let visibleCount = 0;

                seriesDefinitions.forEach(s => {{
                    if (currentVisibilityState[s.key] !== false) {{
                        const price = param.seriesData.get(chartSeriesMap[s.key]);
                        if (price && price.value !== undefined) {{
                            visibleCount++;
                            itemsHtml += `
                                <div class="legend-item">
                                    <span style="color: ${{s.color}}">●</span>
                                    <span style="color: #787b86">${{s.label}}:</span>
                                    <span style="color: #ffffff; font-weight: 700;">${{price.value.toFixed(3)}}%</span>
                                </div>
                            `;
                        }}
                    }}
                }});
                legend.innerHTML = visibleCount > 0 ? itemsHtml : '';
            }} else {{
                legend.innerHTML = '';
            }}
        }});

        // Auto resize chart on window resize
        window.addEventListener('resize', () => {{
            const header = document.getElementById('header');
            const headerHeight = header ? header.offsetHeight : 56;
            chart.applyOptions({{
                width: window.innerWidth,
                height: window.innerHeight - headerHeight
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

