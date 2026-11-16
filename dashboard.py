import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import zipfile
import os
import json
import re
from pathlib import Path

st.set_page_config(page_title="DesignParser Analytics", page_icon="📊", layout="wide")

st.markdown("""<style>
.metric-critical  { color: #FF3B30; font-size: 2.5rem; font-weight: bold; }
.metric-warning   { color: #FF9500; font-size: 2.5rem; font-weight: bold; }
.metric-good      { color: #34C759; font-size: 2.5rem; font-weight: bold; }
.metric-excellent { color: #00C7BE; font-size: 2.5rem; font-weight: bold; }
.metric-label     { color: #8E8E93; font-size: 0.9rem; margin-top: -10px; }
.action-critical  { background: #FF3B301A; padding: 12px; border-radius: 8px; border-left: 4px solid #FF3B30; margin: 8px 0; }
.action-warning   { background: #FF95001A; padding: 12px; border-radius: 8px; border-left: 4px solid #FF9500; margin: 8px 0; }
.action-good      { background: #34C7591A; padding: 12px; border-radius: 8px; border-left: 4px solid #34C759; margin: 8px 0; }
.insight-box      { background: #1C1C2E; padding: 16px; border-radius: 10px; border-left: 4px solid #007AFF; margin: 8px 0; line-height: 1.9; }
.upload-hero      { background: #1C1C2E; padding: 24px; border-radius: 12px; border: 1px solid #2C2C3E; margin-bottom: 24px; }
.filter-info      { background: #1C1C2E; padding: 10px 16px; border-radius: 8px; border-left: 4px solid #007AFF;
                    font-size: 0.85rem; color: #8E8E93; margin-bottom: 16px; }
</style>""", unsafe_allow_html=True)

BASE_DIR = Path.home() / "tiktok-analytics"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

HOOK_TYPES_FILE    = DATA_DIR / "hook_types.json"
CAT_OVERRIDES_FILE = DATA_DIR / "category_overrides.json"
VIDEO_MANUAL_FILE  = DATA_DIR / "video_manual.json"

HOOK_TYPE_OPTIONS    = ["—", "Statement", "Kontrovers", "Mechanismus", "Regel + Zahl", "Beweis", "Vergleich"]
CATEGORIES_AVAILABLE = ["Color", "Typography", "Layout", "Psychology", "Brand", "Packaging", "Components", "Performance", "Other"]
WEEKDAY_DE           = {0: "Mo", 1: "Di", 2: "Mi", 3: "Do", 4: "Fr", 5: "Sa", 6: "So"}

UPLOAD_GUIDE_MD = """
**TikTok Studio → Analytics → rechts oben „Exportieren"**

| # | Datei | Tab | Zeitraum |
|---|---|---|---|
| 1 | Content (7 Tage) | Content | Letzte 7 Tage |
| 2 | Content (28 Tage) | Content | Letzte 28 Tage |
| 3 | Content (365 Tage) | Content | Letzte 365 Tage |
| 4 | Overview (365 Tage) | Übersicht | Letzte 365 Tage |
| 5 | Viewers (365 Tage) | Übersicht | Letzte 365 Tage |
| 6 | Followers (365 Tage) | Follower | Letzte 365 Tage |

**→ Alle 6 ZIPs gleichzeitig hochladen, alten Bestand ersetzen.**

💡 **Wo findest du Viewers?**
TikTok Studio → Analytics → Tab „Übersicht" → Scroll runter zu „Zuschauer" → Exportieren (365 Tage)
"""


# ── HELPERS ──────────────────────────────────────────────────────────────────

def extract_csvs_from_zip(zip_file):
    extracted = {}
    try:
        with zipfile.ZipFile(zip_file, 'r') as z:
            for file in z.namelist():
                if file.lower().endswith('.csv'):
                    filename = os.path.basename(file).lower()
                    with z.open(file) as f:
                        try:
                            df = pd.read_csv(f, encoding='utf-8-sig', quotechar='"',
                                             skipinitialspace=True, on_bad_lines='skip', engine='python')
                            if   'content'           in filename: extracted['content']           = df
                            elif 'overview'          in filename: extracted['overview']          = df
                            elif 'viewer'            in filename: extracted['viewers']           = df
                            elif 'followerhistory'   in filename: extracted['followers']         = df
                            elif 'followeractivity'  in filename: extracted['follower_activity'] = df
                            elif 'followergender'    in filename: extracted['gender']            = df
                            elif 'territor'          in filename: extracted['territories']       = df
                        except:
                            continue
    except:
        pass
    return extracted


def clean_numeric(series):
    return pd.to_numeric(series.replace('undefined', pd.NA), errors='coerce').fillna(0)


def fmt_date(dt, fmt='short'):
    if dt is None or pd.isna(dt): return '?'
    try:
        wd = WEEKDAY_DE.get(dt.weekday(), '')
        if fmt == 'short':   return f"{dt.day}. {dt.strftime('%b')}"
        if fmt == 'weekday': return f"{wd} {dt.day}. {dt.strftime('%b')}"
        if fmt == 'numeric': return f"{dt.day}.{dt.month:02d}"
        if fmt == 'full':    return f"{dt.day}. {dt.strftime('%b %Y')}"
    except:
        return str(dt)[:10]
    return str(dt)[:10]


def smart_parse_dates(series, chronological=False):
    month_map = {
        'Januar': 1, 'Februar': 2, 'März': 3, 'April': 4,
        'Mai': 5, 'Juni': 6, 'Juli': 7, 'August': 8,
        'September': 9, 'Oktober': 10, 'November': 11, 'Dezember': 12,
        'January': 1, 'February': 2, 'March': 3,
        'May': 5, 'June': 6, 'July': 7,
        'October': 10, 'November': 11, 'December': 12,
        'August': 8, 'September': 9,
    }
    now = datetime.now()

    def extract_day_month(parts):
        """Returns (day, month_int) for both 'April 23' and '23. April' formats."""
        p0_clean = parts[0].replace('.', '')
        p1_clean = parts[1].replace('.', '')
        if p0_clean.isdigit():
            return int(p0_clean), month_map.get(p1_clean)
        else:
            m = month_map.get(p0_clean)
            if m and p1_clean.isdigit():
                return int(p1_clean), m
        return None, None

    def day_month(date_str):
        if pd.isna(date_str) or str(date_str).strip() in ('undefined', ''):
            return None, None
        parts = str(date_str).strip().split()
        if len(parts) < 2: return None, None
        return extract_day_month(parts)

    def most_recent(day, month):
        # Exporte haben kein Jahr → jüngstes Vorkommen, das nicht in der Zukunft liegt
        try:
            parsed = datetime(now.year, month, day)
        except ValueError:  # 29. Feb in Nicht-Schaltjahr
            return datetime(now.year - 1, month, day)
        if parsed > now + timedelta(days=1):
            parsed = datetime(now.year - 1, month, day)
        return parsed

    if not chronological:
        def parse_one(date_str):
            day, month = day_month(date_str)
            if day is None or month is None:
                return pd.NaT
            try:
                return most_recent(day, month)
            except ValueError:
                return pd.NaT
        return series.apply(parse_one)

    # Tagesexporte (Overview/Viewers/Followers) decken 365 Tage lückenlos ab und
    # sind alt → neu sortiert. Letzte Zeile = jüngstes Datum; rückwärts laufend
    # springt das Jahr eins zurück, sobald das Datum im Kalender "größer" wird.
    result = pd.Series(pd.NaT, index=series.index, dtype='datetime64[ns]')
    year, prev = None, None
    for idx in reversed(series.index):
        day, month = day_month(series[idx])
        if day is None or month is None:
            continue
        try:
            if year is None:
                year = most_recent(day, month).year
            elif (month, day) > prev:
                year -= 1
            result[idx] = datetime(year, month, day)
            prev = (month, day)
        except ValueError:
            continue
    return result


def categorize_topic(title):
    if pd.isna(title): return 'Other'
    t = str(title).lower()
    keyword_map = {
        'Packaging':   ['packaging', 'bleed', 'dieline', 'print file', 'shelf',
                        'regal', 'mockup', 'print design', 'label', 'barcode'],
        'Color':       ['color palette', 'colour palette', 'color theory', 'colour theory',
                        'color contrast', 'colour contrast', 'color grading',
                        'hue', 'hsl', 'luminan', 'lightness', 'oklch', 'cielab',
                        'saturati', 'colorblind', 'colour blind', 'color blind',
                        'simultaneous contrast', 'cmyk', 'rgb', 'icc profile', 'wcag',
                        'color psychology', 'color mode', 'hex value', 'tint', 'shade',
                        'warm color', 'cool color', 'complementary color',
                        'dark mode', 'chroma', 'hue shift', 'color vibration',
                        'metamerism', 'bezold', 'color constancy', 'simultaneous',
                        'vibration', 'adjacent color', 'optical mix'],
        'Typography':  ['typography', 'typeface', 'line height', 'kerning',
                        'baseline grid', 'serif', 'sans-serif', 'bold text',
                        'italic text', 'text emphasis', 'legibility', 'readability',
                        'type scale', 'text weight', 'letter spacing', 'x-height',
                        'text hierarchy', 'font pairing', 'font size', 'font weight',
                        'variable font', 'display font', 'body text', 'caption text',
                        'small caps', 'smcp', 'fake small caps', 'optical size',
                        'tabular', 'lining figures', 'leading', 'measure', 'tracking'],
        'Layout':      ['grid', 'layout', 'spacing scale', 'whitespace', 'white space',
                        'optical alignment', 'centering', 'alignment', 'margin',
                        'padding', 'composition', 'visual weight', 'visual hierarchy',
                        'focal point', 'asymmetric', 'balance', 'proportion',
                        'golden ratio', 'rule of thirds', 'negative space',
                        'z-pattern', 'z-layout', 'f-pattern', 'f-layout',
                        'scan path', 'visual flow', 'reading flow',
                        'proximity', 'repetition', 'contrast layout',
                        'anchor', 'axial', 'edge tension', 'broken grid',
                        'border radius', 'corner radius', 'entry point',
                        'manuscript grid', 'modular grid', 'van de graaf',
                        'column grid', 'hierarchical grid'],
        'Psychology':  ['subitiz', 'von restorff', 'restorff', 'decoy', 'anchoring',
                        'priming', 'scarcity', 'social proof', 'reciprocity',
                        'loss aversion', 'framing effect', 'nudge', 'mental model',
                        'heuristic', 'choice architecture', 'paradox of choice',
                        'inattentional', 'visual scanning', 'scanning pattern',
                        'pre-selection', 'cognitive load', 'cognitive bias', 'cognitive',
                        'perception', 'gestalt', 'fitts', "fitts'",
                        'hick', 'jakob', 'miller', 'psychology', 'psycholog',
                        'attention span', 'eye tracking', 'pattern recognition',
                        'decision fatigue', 'confirmation bias', 'visual perception',
                        'bouba', 'kiki', 'sound symbolism', 'easing', 'linear motion',
                        'contour bias', 'figure ground', 'stroop', 'closure',
                        'change blindness', 'serial position'],
        'Brand':       ['logo', 'clearspace', 'clear space', 'brand', 'branding',
                        'identity', 'icon system', 'shape language', 'squircle',
                        'icon centering', 'logo format', 'logo clearspace',
                        'wordmark', 'logomark', 'brand system'],
        'Components':  ['card component', 'icon set', 'modal',
                        'tooltip', 'button design', 'input field', 'form design',
                        'navigation bar', 'tab bar', 'menu design', 'breadcrumb'],
        'Performance': ['loading time', 'skeleton screen', 'progress bar', 'performance'],
    }
    scores = {cat: sum(1 for w in words if w in t) for cat, words in keyword_map.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'Other'


def get_metric_color_status(value, metric_type):
    if metric_type == 'share_rate':
        if value >= 0.5:   return 'metric-excellent', 'EXCEPTIONAL'
        elif value >= 0.3: return 'metric-good',      'VERY GOOD'
        elif value >= 0.1: return 'metric-warning',   'LOW'
        else:              return 'metric-critical',   'CRITICAL'
    elif metric_type == 'engagement_rate':
        if value >= 6.0:   return 'metric-excellent', 'EXCELLENT'
        elif value >= 4.0: return 'metric-good',      'GOOD'
        elif value >= 2.0: return 'metric-warning',   'LOW'
        else:              return 'metric-critical',   'CRITICAL'
    elif metric_type == 'save_rate':
        if value >= 3.0:   return 'metric-excellent', 'EXCEPTIONAL'
        elif value >= 1.5: return 'metric-good',      'GOOD'
        elif value >= 0.8: return 'metric-warning',   'LOW'
        else:              return 'metric-critical',   'CRITICAL'
    return 'metric-warning', 'UNKNOWN'


def get_actions(metric_type, status):
    actions = {
        'share_rate': {
            'CRITICAL':    ['🔴 "Send this to a designer who does X" — konkreter Adressat im CTA',
                            '🔴 Zahl in Sekunde 2 → sofortige Datenpunkt-Hook, nicht als Fazit',
                            '🔴 Kontraintuitive These die Mainstream widerlegt'],
            'LOW':         ['🟡 CTA-Formulierungen testen: "Send this to your developer"',
                            '🟡 Framework mit konkreter Zahl → Leute teilen als Referenz'],
            'VERY GOOD':   ['✅ CTA-Struktur beibehalten — was diese Woche funktioniert hat?'],
            'EXCEPTIONAL': ['🟢 EXCEPTIONAL — Video-Struktur exakt dokumentieren & replizieren'],
        },
        'engagement_rate': {
            'CRITICAL':  ['🔴 Frage am Videoende: "Which would you use?"',
                          '🔴 Caption mit polarisierender These'],
            'LOW':       ['🟡 Stärkere Caption mit Meinungsfrage',
                          '🟡 Controversial Hook testen'],
            'GOOD':      ['✅ Solide Engagement Rate — Community reagiert aktiv'],
            'EXCELLENT': ['🟢 EXCELLENT — diesen Content-Typ weiter skalieren'],
        },
    }
    return actions.get(metric_type, {}).get(status, [])


def get_follower_growth(followers_df, period, now, custom_range=None):
    if followers_df is None or len(followers_df) == 0:
        return 0, None, None, "—"
    fs = followers_df.sort_values('Date').dropna(subset=['Date'])
    if len(fs) == 0:
        return 0, None, None, "—"
    if period == 'Custom' and custom_range:
        start, end = custom_range
        window = fs[(fs['Date'] >= start) & (fs['Date'] <= end)]
        growth = int(window['Daily Growth'].sum())
        label  = f"+{growth} ({fmt_date(start,'numeric')}–{fmt_date(end,'numeric')})"
        d_from, d_to = window['Date'].min(), window['Date'].max()
    elif period == 'Last 7 Days':
        max_date = fs['Date'].max()
        cutoff   = max_date - timedelta(days=7)
        window   = fs[fs['Date'] > cutoff]
        growth   = int(window['Daily Growth'].sum())
        d_from, d_to = window['Date'].min(), window['Date'].max()
        label = f"+{growth} ({fmt_date(d_from,'numeric')}–{fmt_date(d_to,'numeric')})"
    elif period == 'Last 30 Days':
        cutoff = now - timedelta(days=30)
        window = fs[fs['Date'] >= cutoff]
        growth = int(window['Daily Growth'].sum())
        label  = f"+{growth} (30d)"
        d_from, d_to = window['Date'].min(), window['Date'].max()
    elif period == 'Last 3 Months':
        cutoff = now - timedelta(days=90)
        window = fs[fs['Date'] >= cutoff]
        growth = int(window['Daily Growth'].sum())
        label  = f"+{growth} (3 Monate)"
        d_from, d_to = window['Date'].min(), window['Date'].max()
    else:
        first  = int(fs.iloc[0]['Followers'])
        last   = int(fs.iloc[-1]['Followers'])
        growth = last - first
        d_from, d_to = fs['Date'].min(), fs['Date'].max()
        label  = f"+{growth} (gesamt)"
    return growth, d_from, d_to, label


def get_avg_daily_views(overview_df, period_filter_start=None):
    if overview_df is None or len(overview_df) == 0: return 0
    real = overview_df[overview_df['Views'] > 0].dropna(subset=['Date'])
    if period_filter_start is not None:
        real = real[real['Date'] >= period_filter_start]
    if len(real) == 0: return 0
    return int(real['Views'].mean())


def apply_period_filter(content_df, period, now, custom_range=None):
    if period == 'Custom' and custom_range:
        start, end = custom_range
        end_of_day = end.replace(hour=23, minute=59, second=59)
        filtered = content_df[content_df['Posted Date'].notna() &
                              (content_df['Posted Date'] >= start) &
                              (content_df['Posted Date'] <= end_of_day)].copy()
        return filtered, start, None
    elif period == 'Last 7 Days':
        cutoff_24h   = now - timedelta(hours=24)
        period_start = now - timedelta(days=7)
        base = content_df[
            content_df['Posted Date'].notna() &
            (content_df['Posted Date'] >= period_start) &
            (content_df['Posted Date'] <= cutoff_24h)
        ].copy()
        n_excluded = len(content_df[
            content_df['Posted Date'].notna() &
            (content_df['Posted Date'] > cutoff_24h)
        ])
        filtered = base.sort_values('Posted Date', ascending=False).head(3)
        hint = "<strong>Letzte 3 Videos (>24h)</strong>"
        if n_excluded > 0:
            hint += f" · {n_excluded} Video(s) <24h ausgeschlossen"
        return filtered, period_start, hint
    elif period == 'Last 30 Days':
        period_start = now - timedelta(days=30)
        filtered = content_df[content_df['Posted Date'].notna() &
                              (content_df['Posted Date'] >= period_start)].copy()
        return filtered, period_start, None
    elif period == 'Last 3 Months':
        period_start = now - timedelta(days=90)
        filtered = content_df[content_df['Posted Date'].notna() &
                              (content_df['Posted Date'] >= period_start)].copy()
        return filtered, period_start, None
    else:
        return content_df.copy(), None, None


def get_week_over_week(content_df, now):
    """Last 3 videos vs. the 3 before that — independent of period filter."""
    cutoff_24h = now - timedelta(hours=24)
    valid = content_df[
        content_df['Posted Date'].notna() &
        (content_df['Posted Date'] <= cutoff_24h)
    ].sort_values('Posted Date', ascending=False)
    if len(valid) < 4:
        return None
    this_3 = valid.head(3)
    prev_3 = valid.iloc[3:6]
    if len(prev_3) == 0:
        return None
    return {
        'this': {'views': this_3['Video Views'].mean(),
                 'share': this_3['Share Rate'].mean(),
                 'eng':   this_3['Engagement Rate'].mean(),
                 'save':  this_3['Save Rate'].mean() if 'Save Rate' in this_3.columns and this_3['Saves'].sum() > 0 else None},
        'prev': {'views': prev_3['Video Views'].mean(),
                 'share': prev_3['Share Rate'].mean(),
                 'eng':   prev_3['Engagement Rate'].mean(),
                 'save':  prev_3['Save Rate'].mean() if 'Save Rate' in prev_3.columns and prev_3['Saves'].sum() > 0 else None},
    }


def generate_insights(filtered_df, viewers_df, followers_df, period, now, custom_range=None):
    insights = []
    if len(filtered_df) > 0:
        top = filtered_df.nlargest(1, 'Video Views').iloc[0]
        insights.append(
            f"🏆 <strong>Top:</strong> \"{str(top['Video Title'])[:55]}…\" — "
            f"<strong>{int(top['Video Views']):,} Views</strong>, {top['Share Rate']:.2f}% Share Rate"
        )
        if len(filtered_df) > 1:
            bot = filtered_df.nsmallest(1, 'Video Views').iloc[0]
            insights.append(
                f"📉 <strong>Flop:</strong> \"{str(bot['Video Title'])[:55]}…\" — "
                f"<strong>{int(bot['Video Views']):,} Views</strong>, {bot['Share Rate']:.2f}% Share Rate"
            )
    avg_share = filtered_df['Share Rate'].mean()
    if avg_share >= 0.3:
        insights.append(f"✅ <strong>Share Rate {avg_share:.2f}%</strong> — über Ziel (0.3%).")
    else:
        insights.append(f"⚠️ <strong>Share Rate {avg_share:.2f}%</strong> — unter Ziel. Hook + CTA prüfen.")
    avg_eng = filtered_df['Engagement Rate'].mean()
    if avg_eng >= 4.0:
        insights.append(f"✅ <strong>Engagement {avg_eng:.1f}%</strong> — Community reagiert aktiv.")
    else:
        insights.append(f"⚠️ <strong>Engagement {avg_eng:.1f}%</strong> — Caption-Frage würde helfen.")
    if len(filtered_df) >= 2:
        cat_avg = filtered_df.groupby('Category')['Video Views'].mean()
        if len(cat_avg) > 1:
            best  = cat_avg.idxmax()
            worst = cat_avg.idxmin()
            if best != worst:
                insights.append(
                    f"📊 <strong>Beste Kategorie: {best}</strong> ({int(cat_avg[best]):,} avg Views) · "
                    f"Schwächste: {worst} ({int(cat_avg[worst]):,})"
                )
    if followers_df is not None:
        growth, _, _, label = get_follower_growth(followers_df, period, now, custom_range)
        if growth > 0:
            insights.append(f"👥 <strong>{label} Follower</strong>")
    return insights


# ── STORAGE ──────────────────────────────────────────────────────────────────

def load_hook_types():
    if HOOK_TYPES_FILE.exists():
        with open(HOOK_TYPES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_hook_types(data):
    with open(HOOK_TYPES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_cat_overrides():
    if CAT_OVERRIDES_FILE.exists():
        with open(CAT_OVERRIDES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_cat_overrides(data):
    with open(CAT_OVERRIDES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_video_manual():
    if VIDEO_MANUAL_FILE.exists():
        with open(VIDEO_MANUAL_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_video_manual(data):
    with open(VIDEO_MANUAL_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def apply_cat_overrides(df, overrides):
    if not overrides or 'Video Link' not in df.columns:
        return df
    df = df.copy()
    for idx, row in df.iterrows():
        link = row.get('Video Link', '')
        if link in overrides:
            df.at[idx, 'Category'] = overrides[link]
    return df


# ── CALLOUT GENERATOR ────────────────────────────────────────────────────────

def _mnum(val):
    """Parse manual entries like '1.2k', '1,121', '+5', '33.8%', '21.87s', '0:21', '33,8 %' → float (None if empty)."""
    s = str(val if val is not None else '').strip().lower()
    for ch in ('+', '%', ' ', 'sek', 's', '~', '≈'):
        s = s.replace(ch, '')
    if not s or s in ('—', '-', '___'):
        return None
    if ':' in s:
        try:
            m, sec = s.split(':', 1)
            return float(m) * 60 + float(sec)
        except ValueError:
            return None
    mult = 1
    if s.endswith('k'):
        mult, s = 1000, s[:-1]
    if re.fullmatch(r'\d+,\d{1,2}', s):
        s = s.replace(',', '.')
    else:
        s = s.replace(',', '')
    try:
        return float(s) * mult
    except ValueError:
        return None


def _short_name(raw_title, mv):
    if (mv.get('kurz') or '').strip():
        return mv['kurz'].strip()
    words = re.sub(r'[^\w\s\-]', '', str(raw_title)).split()
    return " ".join(words[:3]) if words else "Video"


def _ratio_arrow(ratio):
    if ratio is None:
        return "—"
    return "⬆️" if ratio >= 1.2 else ("⬇️" if ratio <= 0.8 else "➖")


def _trend(cur, prev, rel=0.10):
    if cur is None or prev is None or prev == 0:
        return "➖"
    change = (cur - prev) / abs(prev)
    return "⬆️" if change >= rel else ("⬇️" if change <= -rel else "➖")


def _pct_change(cur, prev):
    if cur is None or prev is None or prev == 0:
        return ""
    return f" ({(cur - prev) / prev * 100:+.1f} %)"


def _fmt_int(x):
    return f"{int(round(x)):,}" if x is not None else "___"


def _sum_manual(df, video_manual, key):
    """Sum a manual field over df; None if no video has a value."""
    vals = [_mnum((video_manual or {}).get(r.get('Video Link', ''), {}).get(key)) for _, r in df.iterrows()]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def _tt_saves(row, mv):
    export = int(row['Saves']) if 'Saves' in row and pd.notna(row['Saves']) else 0
    manual = _mnum(mv.get('tt_saves')) or 0
    return int(max(export, manual))


def _territory_str(territories_df, n=5):
    if territories_df is None or len(territories_df) == 0:
        return None
    df = territories_df[~territories_df['Territory'].astype(str).str.lower().isin(['others', 'other'])]
    df = df.sort_values('Share', ascending=False).head(n)
    return " / ".join(f"{t} {s * 100:.1f}" for t, s in zip(df['Territory'], df['Share'])) + " %"


def _gender_str(gender_df):
    if gender_df is None or len(gender_df) == 0:
        return None
    labels = {'male': 'Männer', 'female': 'Frauen', 'other': 'divers'}
    parts = []
    for _, r in gender_df.sort_values('Share', ascending=False).iterrows():
        if r['Share'] > 0:
            parts.append(f"{r['Share'] * 100:.1f} % {labels.get(str(r['Gender']).lower(), r['Gender'])}")
    return " · ".join(parts) if parts else None


def build_callout(filtered_df, viewers_df, followers_df, activity_df, now, hook_types, video_manual=None,
                  custom_range=None, content_df=None, gender_df=None, territories_df=None):
    video_manual = video_manual or {}
    today = now.strftime("%d.%m.%Y")

    # ── Zeitfenster: diese Woche + Vorwoche ──────────────────────────────────
    if custom_range:
        week_start = custom_range[0]
        week_end   = custom_range[1].replace(hour=23, minute=59, second=59)
    else:
        week_start = now - timedelta(days=7)
        week_end   = now.replace(hour=23, minute=59, second=59)
    span       = week_end - week_start
    prev_start = week_start - span
    vids = filtered_df.sort_values('Posted Date').copy()
    n_vids = len(vids)

    prev_vids = None
    if content_df is not None:
        prev_vids = content_df[content_df['Posted Date'].notna() &
                               (content_df['Posted Date'] >= prev_start) &
                               (content_df['Posted Date'] < week_start)]

    def _week_stats(df):
        if df is None or len(df) == 0:
            return None
        views    = float(df['Video Views'].sum())
        saves    = float(sum(_tt_saves(r, video_manual.get(r.get('Video Link', ''), {})) for _, r in df.iterrows()))
        shares   = float(df['Shares'].sum()) if 'Shares' in df.columns else 0.0
        likes    = float(df['Likes'].sum()) if 'Likes' in df.columns else 0.0
        comments = float(df['Comments'].sum()) if 'Comments' in df.columns else 0.0
        ig_views = _sum_manual(df, video_manual, 'ig_views')
        ig = {k: _sum_manual(df, video_manual, f'ig_{k}') for k in ('saves', 'shares', 'likes', 'comments', 'followers')}
        rate = lambda num, den: (num / den * 100) if (num is not None and den) else None
        return {
            'n': len(df), 'views': views, 'saves': saves, 'shares': shares, 'likes': likes, 'comments': comments,
            'save_rate': rate(saves, views) if saves > 0 else None,
            'share_rate': rate(shares, views),
            'eng': rate(likes + comments + shares, views),
            'tt_fol_videos': _sum_manual(df, video_manual, 'tt_followers'),
            'ig_views': ig_views, 'ig': ig,
            'ig_save_rate': rate(ig['saves'], ig_views),
            'ig_share_rate': rate(ig['shares'], ig_views),
            'ig_eng': rate(sum(v or 0 for v in (ig['likes'], ig['comments'], ig['shares'])), ig_views)
                      if ig_views and ig['likes'] is not None else None,
        }

    cur  = _week_stats(vids)
    prev = _week_stats(prev_vids)

    # ── Konto-Werte TikTok ───────────────────────────────────────────────────
    def _fol_growth(start, end):
        if followers_df is None or len(followers_df) == 0 or 'Daily Growth' not in followers_df.columns:
            return None
        w = followers_df[(followers_df['Date'] > start) & (followers_df['Date'] <= end)]
        return int(w['Daily Growth'].sum()) if len(w) else None

    def _returning(start, end):
        if viewers_df is None or len(viewers_df) == 0:
            return None, None
        w = viewers_df[(viewers_df['Date'] > start) & (viewers_df['Date'] <= end)]
        total = w['Total'].sum()
        if total <= 0:
            return None, None
        return w['Returning'].sum() / total * 100, w['New'].sum() / total * 100

    fol_cur, fol_prev = _fol_growth(week_start, week_end), _fol_growth(prev_start, week_start)
    ret_cur, new_cur  = _returning(week_start, week_end)
    ret_prev, _       = _returning(prev_start, week_start)

    post_time_str = "___"
    if activity_df is not None and 'Hour' in activity_df.columns and len(activity_df):
        hourly        = activity_df.groupby('Hour')['Active'].mean()
        post_time_str = f"{(int(hourly.idxmax()) - 1) % 24}:30"

    pct = lambda v: f"{v:.2f}%" if v is not None else "___"
    star = lambda v: f"{v:.2f}%*" if v is not None else "___"

    tt_fol_cell = (f"{fol_cur:+d}" if fol_cur is not None else "___")
    if cur['tt_fol_videos'] is not None:
        tt_fol_cell += f" · Σ Videos {int(cur['tt_fol_videos'])}"
    ig_fol_cell = "netto ___ (+___ / −___)"
    if cur['ig']['followers'] is not None:
        ig_fol_cell += f" · Σ Reels {int(cur['ig']['followers'])}"

    fol_status = _trend(fol_cur, fol_prev)
    if fol_cur is not None and cur['tt_fol_videos'] is not None and abs(fol_cur - cur['tt_fol_videos']) >= max(5, 0.5 * abs(fol_cur)):
        fol_status = "⚠️"

    ig_views_cell = f"{_fmt_int(cur['ig_views'])} (Σ Reels) · Konto ___" if cur['ig_views'] else "___"
    prev_ig = prev['ig_views'] if prev else None

    rows = [
        ("Views", f"{int(cur['views']):,}", ig_views_cell, _trend(cur['views'], prev['views'] if prev else None)),
        ("New Followers", tt_fol_cell, ig_fol_cell, fol_status),
        ("Save Rate", pct(cur['save_rate']), star(cur['ig_save_rate']),
         _trend(cur['save_rate'], prev['save_rate'] if prev else None, 0.15)),
        ("Share Rate", pct(cur['share_rate']), star(cur['ig_share_rate']),
         _trend(cur['share_rate'], prev['share_rate'] if prev else None, 0.15)),
        ("Engagement", pct(cur['eng']), star(cur['ig_eng']),
         _trend(cur['eng'], prev['eng'] if prev else None, 0.15)),
        ("Returning Viewers", f"{ret_cur:.1f}%" if ret_cur is not None else "—", "—", _trend(ret_cur, ret_prev)),
        ("Optimale Postzeit", post_time_str, "___ (Follower-Aktivität)", ""),
    ]
    konto_table = "\n".join(f"> | {a} | {b} | {c} | {d} |" for a, b, c, d in rows)

    ig_src = ""
    if cur['ig_views']:
        ig = cur['ig']
        ig_src = (f" · IG-Werte mit * aus Σ der {n_vids} Reels ({_fmt_int(ig['saves'])} Saves, {_fmt_int(ig['shares'])} Shares, "
                  f"{_fmt_int(ig['likes'])} Likes, {_fmt_int(ig['comments'])} Kommentare ÷ {_fmt_int(cur['ig_views'])} Views)")
    konto_note = (
        f"> _Save Rate = Saves ÷ Views · Share Rate = Shares ÷ Views · Engagement = (Likes+Comments+Shares) ÷ Views · "
        f"Returning Viewers = wiederkehrende ÷ alle Zuschauer · Status = Trend vs. Vorwoche (⬆️/⬇️ ab ±10 % bzw. ±15 % bei Raten, ⚠️ = Werte passen nicht zusammen) · "
        f"TT aus Σ der {n_vids} Videos ({int(cur['saves']):,} Saves, {int(cur['shares']):,} Shares, {int(cur['likes']):,} Likes, "
        f"{int(cur['comments']):,} Kommentare ÷ {int(cur['views']):,} Views){ig_src} · "
        f"IG-Konto: ___ Betrachter, ___ % Nicht-Follower, ___ Profilaufrufe, ___ Link-Taps, Follower gesamt ____"
    )

    # ── Konsistenzcheck ──────────────────────────────────────────────────────
    checks = []
    if fol_cur is not None and cur['tt_fol_videos'] is not None:
        diff = fol_cur - int(cur['tt_fol_videos'])
        if diff > 0:
            checks.append(f"TT New Followers: Σ Videos {int(cur['tt_fol_videos'])} vs. Konto {fol_cur:+d} → {diff} über ältere Videos/Profil")
        elif diff < 0:
            checks.append(f"TT New Followers: Σ Videos {int(cur['tt_fol_videos'])} > Konto {fol_cur:+d} → {-diff} Entfolgungen gegengerechnet")
    missing = {}
    labels = {'laenge': 'Länge', 'watch': 'Ø Watch', 'fyp': 'FYP', 'ig_views': 'IG Views', 'tt_followers': 'TT Follower'}
    for _, r in vids.iterrows():
        mv = video_manual.get(r.get('Video Link', ''), {})
        gaps = [lab for key, lab in labels.items() if _mnum(mv.get(key)) is None]
        if gaps:
            missing[_short_name(r['Video Title'], mv)] = gaps
    for name, gaps in missing.items():
        checks.append(f"{name}: fehlt noch {', '.join(gaps)}")
    checks.append("_")
    check_lines = "\n".join(f"> - {c}" for c in checks)

    # ── Einordnung vs. Durchschnitt ──────────────────────────────────────────
    base_tt, base_ig, base_n = None, None, 0
    if content_df is not None and n_vids:
        first_post = vids['Posted Date'].min()
        before = content_df[content_df['Posted Date'].notna() & (content_df['Posted Date'] < first_post)] \
            .sort_values('Posted Date', ascending=False).head(8)
        base_n = len(before)
        if base_n:
            base_tt = float(before['Video Views'].median())
            ig_hist = [_mnum(video_manual.get(l, {}).get('ig_views')) for l in before['Video Link']]
            ig_hist = [v for v in ig_hist if v]
            if len(ig_hist) >= 3:
                base_ig = float(pd.Series(ig_hist).median())
    base_label = f"TT: Median der {base_n} Videos vor der Woche = {_fmt_int(base_tt)}" if base_tt else "TT: ___"
    base_label += f" · IG: Median = {_fmt_int(base_ig)}" if base_ig else " · IG: \"Deine üblichen Reels\"-Linie"

    # ── Pro-Video-Teile ──────────────────────────────────────────────────────
    einord, details, table_rows, extra_tt, audience_rows, drop_rows, vo_lines = [], [], [], [], [], [], []
    for _, row in vids.iterrows():
        link      = row.get('Video Link', '')
        mv        = video_manual.get(link, {})
        raw_title = str(row['Video Title'])
        name      = _short_name(raw_title, mv)
        title     = (raw_title[:45] + "…") if len(raw_title) > 45 else raw_title
        posted    = row['Posted Date']
        wd        = WEEKDAY_DE.get(posted.weekday(), '') if pd.notna(posted) else ''
        date_str  = f"{wd} {posted.strftime('%d.%m.')}" if pd.notna(posted) else '—'
        views     = int(row['Video Views'])
        saves     = _tt_saves(row, mv)
        shares    = int(row['Shares']) if 'Shares' in row and pd.notna(row['Shares']) else 0
        laenge, watch = _mnum(mv.get('laenge')), _mnum(mv.get('watch'))
        retention = _mnum(mv.get('retention'))
        if retention is None and laenge and watch:
            retention = watch / laenge * 100
        ig_views  = _mnum(mv.get('ig_views'))
        ig_saves, ig_shares = _mnum(mv.get('ig_saves')), _mnum(mv.get('ig_shares'))
        ig_rate   = lambda x: f"{x / ig_views * 100:.2f}%" if (x is not None and ig_views) else "___"
        fmt_s     = lambda x: f"{x:g} s" if x is not None else "___"
        ret_str   = f"{retention:.1f} %" if retention is not None else "___"
        sr_str    = f"{saves / views * 100:.2f} %" if saves and views else "___"

        r_tt = views / base_tt if base_tt else None
        r_ig = ig_views / base_ig if (ig_views and base_ig) else None
        tt_part = f"TT {_ratio_arrow(r_tt)} {r_tt:.2f}×" if r_tt is not None else "TT ___"
        ig_part = f"IG {_ratio_arrow(r_ig)} {r_ig:.2f}×" if r_ig is not None else "IG ___×"
        einord.append(f"> - {name} · {tt_part} · {ig_part}")

        extra = " · ".join(x for x in (
            f"Serie: {mv['serie']}" if (mv.get('serie') or '').strip() else '',
        ) if x)
        tt_bits = [f"TT {views:,} Views", f"Retention {ret_str} ({fmt_s(watch)} / {fmt_s(laenge)})",
                   f"Save Rate {sr_str}", f"{mv.get('tt_followers') or '___'} Follower", f"FYP {mv.get('fyp') or '___'}"]
        ig_bits = [f"IG {_fmt_int(ig_views)} Views", f"Skip {mv.get('ig_skip') or '___'}",
                   f"{_fmt_int(ig_saves)} Saves ({ig_rate(ig_saves)})", f"{_fmt_int(ig_shares)} Shares ({ig_rate(ig_shares)})",
                   f"Ø {mv.get('ig_watch') or '___'}"]
        note = (mv.get('notiz') or '').strip()
        note = f" {note}_" if note else "_ ___"
        details.append(f"> ↳ **{name}** _({date_str}{', ' + extra if extra else ''})_: _{', '.join(tt_bits)}. {', '.join(ig_bits)}.{note}")

        table_rows.append(
            f"> | {title} | {mv.get('blueprint') or '—'} | {hook_types.get(link, '—')} | {mv.get('einstieg') or '—'} | "
            f"{row.get('Category', '—')} | {wd} {mv.get('uhrzeit') or '—:—'} | {fmt_s(laenge).replace(' ', '')} | {mv.get('fyp') or '___'} | "
            f"{views:,} | {f'{saves:,}' if saves else '___'} | {sr_str.replace(' ', '')} | {ret_str.replace(' ', '')} | {fmt_s(watch).replace(' ', '')} | "
            f"{mv.get('tt_followers') or '___'} | {_fmt_int(ig_views)} | {_fmt_int(ig_saves)} | {_fmt_int(ig_shares)} | "
            f"{ig_rate(ig_saves)} | {ig_rate(ig_shares)} | {mv.get('ig_followers') or '___'} | {mv.get('ig_watch') or '___'} |"
        )
        extra_tt.append(f"{name} {shares} Shares ({row['Share Rate']:.2f} %), Engagement {row['Engagement Rate']:.2f} %")

        audience_rows.append(
            f"> | {name} | {mv.get('tt_laender') or '___'} | {mv.get('tt_quellen') or '___'} | "
            f"{mv.get('tt_zuschauer') or '___'} | {mv.get('ig_laender') or '___'} | {mv.get('ig_quellen') or '___'} |"
        )

        if mv.get('absprung') or mv.get('absprung_text'):
            drop_rows.append(f"> | {name} | {mv.get('absprung') or '___'} | {mv.get('absprung_text') or '___'} |")

        vo = [l.strip() for l in (mv.get('voiceover') or '').splitlines() if l.strip()]
        vo_lines.append(f"> - {name}: " + (f"_\"{' / '.join(vo)}\"_" if vo else "_(fehlt noch)_"))

    # ── Publikum & Länder (Konto) ────────────────────────────────────────────
    terr = _territory_str(territories_df)
    gend = _gender_str(gender_df)
    aud_konto = (
        f"> | Ebene | TikTok | IG |\n"
        f"> | --- | --- | --- |\n"
        f"> | Follower-Länder (Konto) | {terr or '___'} | ___ |\n"
        f"> | Geschlecht (Konto) | {gend or '___'} | ___ |\n"
        f"> | Zuschauer neu / wiederkehrend | "
        f"{f'{new_cur:.1f} / {ret_cur:.1f} %' if ret_cur is not None else '—'} | — |\n"
        f"> | Nicht-Follower-Anteil | — | ___ |\n"
        f"> | Sprachen | — | ___ |"
    )

    # ── Auto-Beobachtungen ───────────────────────────────────────────────────
    circled = "①②③④⑤⑥⑦⑧⑨⑩"
    obs = []
    if prev:
        ig_prev_str = f", IG {_fmt_int(prev_ig)} → {_fmt_int(cur['ig_views'])}{_pct_change(cur['ig_views'], prev_ig)}" \
            if (prev_ig and cur['ig_views']) else ""
        obs.append(f"Vorwoche → diese Woche: TT {int(prev['views']):,} → {int(cur['views']):,}"
                   f"{_pct_change(cur['views'], prev['views'])}{ig_prev_str} ({prev['n']} → {n_vids} Videos).")
    rets = [(_short_name(r['Video Title'], video_manual.get(r.get('Video Link', ''), {})),
             _mnum(video_manual.get(r.get('Video Link', ''), {}).get('watch'))) for _, r in vids.iterrows()]
    rets = [(n, w) for n, w in rets if w is not None]
    if rets:
        obs.append("TT Ø Watch: " + " · ".join(f"{n} {w:g} s" for n, w in rets) + ".")
    if fol_cur is not None and fol_prev is not None:
        obs.append(f"TT-Follower-Zuwachs {fol_prev:+d} → {fol_cur:+d}.")
    obs_lines = "\n".join(f"> _{circled[i]} {o}_" for i, o in enumerate(obs))
    obs_lines += ("\n" if obs else "") + f"> {circled[len(obs)]} ___"

    drop_section = (
        f"> 🔻 **Absprungmomente**\n"
        f">\n"
        f"> | Video | Absprung-Sek | Text/Szene an dem Punkt |\n"
        f"> | --- | --- | --- |\n"
        + "\n".join(drop_rows) + "\n>\n"
    ) if drop_rows else ""

    plural = 's' if n_vids != 1 else ''
    return (
        f"> [!tiktok]+ {today}\n"
        f"> _📅 Kontoweit, Ø/Summe aller Videos dieser Woche (nicht einzelne Videos)_\n"
        f">\n"
        f"> | Metrik | TikTok | IG | Status |\n"
        f"> | --- | --- | --- | --- |\n"
        f"{konto_table}\n"
        f"{konto_note}\n"
        f">\n"
        f"> ⚠️ **Konsistenzcheck:**\n"
        f"{check_lines}\n"
        f">\n"
        f"> 🎯 **Einordnung vs. Durchschnitt** _({base_label})_\n"
        f"{chr(10).join(einord)}\n"
        f">\n"
        f"{chr(10).join(details)}\n"
        f">\n"
        f"> 📊 **Video-Details** _(pro Video, {n_vids} Video{plural} diese Woche):_\n"
        f">\n"
        f"> | Video | Blueprint | Hook-Typ | Einstieg | Thema | Uhrzeit | Länge | FYP | TT Views | TT Saves | TT Save Rate | Retention | Ø Watch | TT New Followers | IG Views | IG Saves | IG Shares | IG Save Rate | IG Share Rate | IG New Followers | IG Ø Watch |\n"
        f"> | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        f"{chr(10).join(table_rows)}\n"
        f"> _FYP = Anteil For-You-Page-Traffic · Save/Share Rate je Video = Saves bzw. Shares ÷ Views dieses Videos · "
        f"Retention = Ø Watch ÷ Länge · Einstieg ✅ = Kamerafahrt/Zoom, — = Bewegung im Bild ohne Ausschnittwechsel_\n"
        f">\n"
        f"> ↳ _TT Shares/Engagement je Video: {' · '.join(extra_tt)}_\n"
        f">\n"
        f"> 🌍 **Publikum & Länder**\n"
        f">\n"
        f"{aud_konto}\n"
        f">\n"
        f"> | Video | TT-Länder | TT-Quellen | TT-Zuschauer | IG-Länder | IG-Quellen |\n"
        f"> | --- | --- | --- | --- | --- | --- |\n"
        f"{chr(10).join(audience_rows)}\n"
        f"> _Länder als Top 5 in % (z.B. US 13.3 / DE 6.2 / …) · Quellen = FYP / Gefolgt / Profil / Suche bzw. Feed / Reels-Tab / Stories · "
        f"TT-Zuschauer = neu / wiederkehrend, Nicht-Follower-Anteil · TT-Follower-Länder/Geschlecht aus dem Follower-Export_\n"
        f">\n"
        f"{drop_section}"
        f"> 📝 **Voiceover-Texte**\n"
        f"{chr(10).join(vo_lines)}\n"
        f">\n"
        f"> 🧪 **Letzter Test:** _\n"
        f"> 🔬 **Nächste Woche:** _\n"
        f">\n"
        f"{obs_lines}"
    )


def build_month_callout(filtered_df, viewers_df, followers_df, overview_df, now, hook_types, video_manual=None, custom_range=None):
    today = now.strftime("%d.%m.%Y")

    # Follower total + growth (30d, or custom range if given)
    fol_total_str = "—"
    fol_growth_str = "—"
    if followers_df is not None and len(followers_df) > 0:
        fs = followers_df.sort_values('Date').dropna(subset=['Date'])
        if len(fs) > 0:
            fol_total_str = f"{int(fs.iloc[-1]['Followers']):,}"
        if custom_range:
            growth, _, _, _ = get_follower_growth(followers_df, 'Custom', now, custom_range)
        else:
            growth, _, _, _ = get_follower_growth(followers_df, 'Last 30 Days', now)
        fol_growth_str = f"+{growth}" if growth > 0 else str(growth)

    # Total views + Ø daily views (30d, or custom range if given)
    total_views = int(filtered_df['Video Views'].sum())
    avg_daily_str = "—"
    if overview_df is not None and len(overview_df) > 0:
        cutoff = custom_range[0] if custom_range else now - timedelta(days=30)
        end    = custom_range[1] if custom_range else now
        ov = overview_df[(overview_df['Date'] >= cutoff) & (overview_df['Date'] <= end) & (overview_df['Views'] > 0)]
        if len(ov) > 0:
            avg_daily_str = f"{int(ov['Views'].mean()):,}"

    # Returning viewers
    ret_str = "—"
    if viewers_df is not None and len(viewers_df) > 0:
        total = viewers_df['Total'].sum()
        ret   = viewers_df['Returning'].sum()
        if total > 0:
            ret_str = f"{ret / total * 100:.1f}%"

    # Engagement + Share
    avg_eng   = filtered_df['Engagement Rate'].mean()
    avg_share = filtered_df['Share Rate'].mean()

    # Manuelle Werte (aus den weekly Callouts gepflegt) über den Monats-Zeitraum aggregieren,
    # statt sie erneut als Platzhalter abzufragen — video_manual ist bereits pro Video/Woche befüllt.
    def _parse_num(val):
        try:
            return float(str(val or '0').replace(',', '').replace('k', '000').replace('K', '000'))
        except (ValueError, AttributeError):
            return 0.0

    def _parse_unit(val):
        s = str(val or '').strip().rstrip('%s')
        try:
            return float(s.replace(',', '.'))
        except ValueError:
            return None

    total_saves_agg = 0
    ig_views_sum = 0.0
    ig_saves_sum = 0.0
    ig_watch_vals = []
    per_video_watch = {}
    per_video_fyp = {}
    for _, row in filtered_df.iterrows():
        link = row.get('Video Link', '')
        mv = (video_manual or {}).get(link, {})
        tt_saves_export = int(row['Saves']) if 'Saves' in row and pd.notna(row['Saves']) else 0
        try:
            manual_saves = int(float(str(mv.get('tt_saves', '') or '0').replace(',', '')))
        except (ValueError, AttributeError):
            manual_saves = 0
        total_saves_agg += max(tt_saves_export, manual_saves)
        ig_views_sum += _parse_num(mv.get('ig_views'))
        ig_saves_sum += _parse_num(mv.get('ig_saves'))
        w = _parse_unit(mv.get('ig_watch'))
        if w is not None:
            ig_watch_vals.append(w)
        per_video_watch[link] = _parse_unit(mv.get('watch'))
        per_video_fyp[link]   = _parse_unit(mv.get('fyp'))

    avg_save_rate_month = (total_saves_agg / total_views * 100) if total_saves_agg > 0 and total_views > 0 else None
    save_rate_str = f"Ø {avg_save_rate_month:.2f}%" if avg_save_rate_month is not None else "___"
    ig_views_str  = f"{int(ig_views_sum):,}" if ig_views_sum > 0 else "___"
    ig_saves_str  = f"{int(ig_saves_sum):,}" if ig_saves_sum > 0 else "___"
    ig_watch_str  = f"Ø {sum(ig_watch_vals) / len(ig_watch_vals):.0f}s" if ig_watch_vals else "___"

    # Blueprint table — grouped by hook type, sorted by Ø Views desc
    vids = filtered_df.copy()
    if 'Video Link' in vids.columns:
        vids['_hook'] = vids['Video Link'].map(hook_types).fillna('—')
        vids['_watch'] = vids['Video Link'].map(per_video_watch)
        vids['_fyp']   = vids['Video Link'].map(per_video_fyp)
    else:
        vids['_hook'] = '—'
        vids['_watch'] = None
        vids['_fyp']   = None
    has_saves_month = 'Saves' in vids.columns and vids['Saves'].sum() > 0
    has_watch_month = vids['_watch'].notna().any()
    has_fyp_month   = vids['_fyp'].notna().any()
    _bp_agg = {'count': ('Video Views', 'count'), 'avg_views': ('Video Views', 'mean')}
    if has_saves_month:
        _bp_agg['avg_save'] = ('Save Rate', 'mean')
    if has_watch_month:
        _bp_agg['avg_watch'] = ('_watch', 'mean')
    if has_fyp_month:
        _bp_agg['avg_fyp'] = ('_fyp', 'mean')
    bp = (vids.groupby('_hook')
              .agg(**_bp_agg)
              .reset_index()
              .sort_values('avg_views', ascending=False))
    circled = "①②③④⑤⑥⑦⑧⑨"
    bp_rows = []
    for i, (_, r) in enumerate(bp.iterrows()):
        num  = circled[i] if i < len(circled) else f"{i+1}."
        hook = r['_hook']
        save_cell  = f"{r['avg_save']:.2f}%" if has_saves_month and pd.notna(r.get('avg_save')) else "___"
        watch_cell = f"{r['avg_watch']:.0f}s" if has_watch_month and pd.notna(r.get('avg_watch')) else "___"
        fyp_cell   = f"{r['avg_fyp']:.0f}%" if has_fyp_month and pd.notna(r.get('avg_fyp')) else "___"
        bp_rows.append(
            f"> | {num} {hook} | {int(r['count'])} | {int(r['avg_views']):,} | {save_cell} | {watch_cell} | {fyp_cell} |"
        )
    blueprint_table = "\n".join(bp_rows) if bp_rows else "> | — | — | — | — | — | — |"

    # Top category by avg views
    cat_avg = vids.groupby('Category')['Video Views'].mean()
    top_cat       = cat_avg.idxmax() if len(cat_avg) > 0 else "—"
    top_cat_views = f"{int(cat_avg.max()):,}" if len(cat_avg) > 0 else "—"

    return (
        f"> [!tiktok-month]+ {today}\n"
        f"> _📆 Kontoweit, Ø/Summe aller Videos im gewählten Monatszeitraum_\n"
        f">\n"
        f"> 👥 **Follower:** {fol_total_str} ({fol_growth_str})\n"
        f"> 👁 **Views (30d):** {total_views:,}\n"
        f"> 📅 **Ø Daily Views:** {avg_daily_str}\n"
        f"> 🔄 **Returning Viewers:** {ret_str}\n"
        f"> 💬 **Ø Engagement:** {avg_eng:.1f}%\n"
        f"> 📤 **Ø Share Rate:** {avg_share:.2f}%\n"
        f"> 🔖 **Ø Save Rate:** {save_rate_str}\n"
        f"> 📸 **IG Views:** {ig_views_str}\n"
        f"> 💾 **IG Saves:** {ig_saves_str}\n"
        f"> ⏱ **IG Ø Watch:** {ig_watch_str}\n"
        f"> _Engagement = (Likes+Comments+Shares) ÷ Views · Share/Save Rate = Shares bzw. Saves ÷ Views · Returning Viewers = wiederkehrende ÷ alle Zuschauer_\n"
        f">\n"
        f"> | Blueprint | Videos | Ø Views | Ø Save Rate | Ø Watchtime | Ø FYP |\n"
        f"> | --- | --- | --- | --- | --- | --- |\n"
        f"{blueprint_table}\n"
        f"> _Blueprint = Videos gruppiert nach Hook-Typ, sortiert nach Ø Views · FYP = Anteil For-You-Page-Traffic_\n"
        f">\n"
        f"> 📊 **Top-Kategorie:** {top_cat} — Ø {top_cat_views} Views\n"
        f">\n"
        f"> ✅ **Bestätigt:** _\n"
        f"> ❌ **Widerlegt / offen:** _\n"
        f"> 🎯 **Hypothese nächster Monat:** _"
    )


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    st.title("📊 DesignParser TikTok Analytics 2026")
    st.caption("Educational Content Benchmarks")

    content_path   = DATA_DIR / 'content.csv'
    overview_path  = DATA_DIR / 'overview.csv'
    viewers_path   = DATA_DIR / 'viewers.csv'
    followers_path = DATA_DIR / 'followers.csv'
    activity_path  = DATA_DIR / 'activity.csv'

    if not content_path.exists():
        st.markdown("## 👆 So startest du")
        st.markdown(
            "<div class='upload-hero'>" + UPLOAD_GUIDE_MD.replace("\n", "<br>") + "</div>",
            unsafe_allow_html=True
        )
        st.info("Lade die ZIPs in der Sidebar hoch und klicke auf **Process Data**.")
        st.sidebar.header("📂 Upload Data")
        uploaded_files = st.sidebar.file_uploader("TikTok ZIP files", type=['zip'], accept_multiple_files=True)
        if uploaded_files and st.sidebar.button("🔄 Process Data"):
            _process_uploads(uploaded_files)
            st.rerun()
        return

    # ── SIDEBAR ───────────────────────────────────────────────────────────────
    st.sidebar.header("📂 Upload Data")
    uploaded_files = st.sidebar.file_uploader("TikTok ZIP files", type=['zip'], accept_multiple_files=True)
    if uploaded_files:
        st.sidebar.success(f"✅ {len(uploaded_files)} files")
        if st.sidebar.button("🔄 Process Data"):
            _process_uploads(uploaded_files)
            st.rerun()
    with st.sidebar.expander("📋 Welche ZIPs?", expanded=False):
        st.markdown(UPLOAD_GUIDE_MD)

    # ── DATEN LADEN ───────────────────────────────────────────────────────────
    content_df   = pd.read_csv(content_path)
    if 'Saves' not in content_df.columns:
        content_df['Saves'] = 0
    if 'Save Rate' not in content_df.columns:
        content_df['Save Rate'] = (content_df['Saves'] / content_df['Video Views'].replace(0, 1) * 100).clip(0, 100)
    overview_df  = pd.read_csv(overview_path)  if overview_path.exists()  else None
    viewers_df   = pd.read_csv(viewers_path)   if viewers_path.exists()   else None
    followers_df = pd.read_csv(followers_path) if followers_path.exists() else None
    activity_df  = pd.read_csv(activity_path)  if activity_path.exists()  else None
    gender_df      = pd.read_csv(DATA_DIR / 'gender.csv')      if (DATA_DIR / 'gender.csv').exists()      else None
    territories_df = pd.read_csv(DATA_DIR / 'territories.csv') if (DATA_DIR / 'territories.csv').exists() else None

    content_df['Posted Date'] = pd.to_datetime(content_df['Posted Date'], errors='coerce')
    if overview_df  is not None:
        overview_df['Date']  = pd.to_datetime(overview_df['Date'],  errors='coerce')
    if followers_df is not None:
        followers_df['Date'] = pd.to_datetime(followers_df['Date'], errors='coerce')
    if viewers_df   is not None:
        viewers_df['Date']   = pd.to_datetime(viewers_df['Date'],   errors='coerce')

    # "now" wird aus dem Export selbst abgeleitet (letztes Datum mit echten Daten),
    # nicht vom System-Datum — sonst driftet "Last 7 Days" vom Stand des CSVs weg,
    # wenn das Dashboard erst Tage nach dem Export geöffnet wird.
    anchor_candidates = []
    if overview_df is not None and len(overview_df):
        anchor_candidates.append(overview_df['Date'].max())
    if followers_df is not None and len(followers_df):
        anchor_candidates.append(followers_df['Date'].max())
    if len(content_df):
        anchor_candidates.append(content_df['Posted Date'].max())
    anchor_candidates = [d for d in anchor_candidates if pd.notna(d)]
    now = max(anchor_candidates) if anchor_candidates else datetime.now()
    now = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if overview_df  is not None:
        overview_df = overview_df[overview_df['Date'] <= now]
    if followers_df is not None:
        followers_df = followers_df[followers_df['Date'] <= now]

    # Apply persistent overrides
    overrides     = load_cat_overrides()
    content_df    = apply_cat_overrides(content_df, overrides)
    hook_types    = load_hook_types()
    video_manual  = load_video_manual()

    # ── SIDEBAR STATUS ────────────────────────────────────────────────────────
    st.sidebar.divider()
    st.sidebar.write(f"✅ Videos gesamt: {len(content_df)}")
    if overview_df  is not None: st.sidebar.write(f"✅ Daily: {len(overview_df[overview_df['Views']>0])} Tage")
    if viewers_df   is not None: st.sidebar.write(f"✅ Viewers: {len(viewers_df)} Tage")
    else:                        st.sidebar.write("⚠️ Viewers: nicht geladen")
    if followers_df is not None: st.sidebar.write(f"✅ Followers bis {fmt_date(followers_df['Date'].max(), 'full')}")
    if activity_df  is not None: st.sidebar.write("✅ Activity: ✓")

    # ── PERIOD FILTER ─────────────────────────────────────────────────────────
    period = st.radio("📅 Period",
                      ['All Time', 'Last 3 Months', 'Last 30 Days', 'Last 7 Days', 'Custom'],
                      horizontal=True)

    custom_range = None
    if period == 'Custom':
        min_date = content_df['Posted Date'].min()
        min_date = min_date.date() if pd.notna(min_date) else now.date()
        max_date = now.date()
        default_start = max(min_date, (now - timedelta(days=7)).date())
        col_from, col_to = st.columns(2)
        with col_from:
            date_from = st.date_input("Von", value=default_start,
                                      min_value=min_date, max_value=max_date)
        with col_to:
            date_to = st.date_input("Bis", value=max_date,
                                    min_value=min_date, max_value=max_date)
        if date_from > date_to:
            st.warning("⚠️ 'Von' liegt nach 'Bis' — Daten wurden vertauscht.")
            date_from, date_to = date_to, date_from
        custom_range = (datetime.combine(date_from, datetime.min.time()),
                        datetime.combine(date_to, datetime.min.time()))

    filtered_df, period_start, filter_hint = apply_period_filter(content_df, period, now, custom_range)

    if len(filtered_df) == 0:
        st.warning(f"⚠️ Keine Videos im Zeitraum {period}")
        return
    if filter_hint:
        st.markdown(f"<div class='filter-info'>📌 {filter_hint}</div>", unsafe_allow_html=True)

    # ── WEEK-OVER-WEEK ────────────────────────────────────────────────────────
    wow = get_week_over_week(content_df, now)
    if wow:
        st.subheader("↕️ Letzte 3 Videos vs. 3 davor")
        c1, c2, c3, c4 = st.columns(4)

        def _delta(curr, prev, fmt, suffix=''):
            d    = curr - prev
            sign = '+' if d >= 0 else ''
            return f"{sign}{d:{fmt}}{suffix}"

        def _color(curr, prev):
            return "normal" if curr >= prev else "inverse"

        c1.metric("⌀ Views",       f"{wow['this']['views']:,.0f}",
                  _delta(wow['this']['views'], wow['prev']['views'], '.0f'),
                  delta_color=_color(wow['this']['views'], wow['prev']['views']))
        c2.metric("⌀ Share Rate",  f"{wow['this']['share']:.2f}%",
                  _delta(wow['this']['share'], wow['prev']['share'], '.2f', '%'),
                  delta_color=_color(wow['this']['share'], wow['prev']['share']))
        c3.metric("⌀ Engagement",  f"{wow['this']['eng']:.1f}%",
                  _delta(wow['this']['eng'], wow['prev']['eng'], '.1f', '%'),
                  delta_color=_color(wow['this']['eng'], wow['prev']['eng']))
        if wow['this']['save'] is not None and wow['prev']['save'] is not None:
            c4.metric("⌀ Save Rate", f"{wow['this']['save']:.2f}%",
                      _delta(wow['this']['save'], wow['prev']['save'], '.2f', '%'),
                      delta_color=_color(wow['this']['save'], wow['prev']['save']))
        else:
            c4.metric("⌀ Save Rate", "—")
    st.divider()

    # ── INSIGHTS ──────────────────────────────────────────────────────────────
    st.subheader("🔍 Diese Woche")
    insights = generate_insights(filtered_df, viewers_df, followers_df, period, now, custom_range)
    st.markdown("<div class='insight-box'>" + "<br>".join(insights) + "</div>", unsafe_allow_html=True)
    st.divider()

    # ── METRICS ───────────────────────────────────────────────────────────────
    st.subheader("🎯 Performance")
    col_m1, col_m2, col_m3 = st.columns(3)

    with col_m1:
        avg_share     = filtered_df['Share Rate'].mean()
        cc, status    = get_metric_color_status(avg_share, 'share_rate')
        st.markdown(f'<div class="{cc}">{avg_share:.2f}%</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-label">Share Rate · {status} · Ziel: 0.3–0.5%</div>', unsafe_allow_html=True)
        for a in get_actions('share_rate', status)[:2]:
            ac = 'action-critical' if '🔴' in a else 'action-warning' if '🟡' in a else 'action-good'
            st.markdown(f'<div class="{ac}">{a}</div>', unsafe_allow_html=True)

    with col_m2:
        avg_eng       = filtered_df['Engagement Rate'].mean()
        cc, status    = get_metric_color_status(avg_eng, 'engagement_rate')
        st.markdown(f'<div class="{cc}">{avg_eng:.1f}%</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-label">Engagement Rate · {status} · Ziel: 4–6%</div>', unsafe_allow_html=True)
        for a in get_actions('engagement_rate', status)[:2]:
            ac = 'action-critical' if '🔴' in a else 'action-warning' if '🟡' in a else 'action-good'
            st.markdown(f'<div class="{ac}">{a}</div>', unsafe_allow_html=True)

    with col_m3:
        if 'Saves' in filtered_df.columns and filtered_df['Saves'].sum() > 0:
            avg_save   = filtered_df['Save Rate'].mean()
            cc, status = get_metric_color_status(avg_save, 'save_rate')
            st.markdown(f'<div class="{cc}">{avg_save:.2f}%</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="metric-label">Save Rate · {status} · Ziel: 1.5–3%</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="metric-warning">—</div>', unsafe_allow_html=True)
            st.markdown('<div class="metric-label">Save Rate · nicht im TikTok-Export</div>', unsafe_allow_html=True)

    st.divider()

    # ── OVERVIEW ──────────────────────────────────────────────────────────────
    st.subheader("📊 Overview")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        label = "Total Views (3 Videos)" if period == 'Last 7 Days' else "Total Views"
        st.metric(label, f"{int(filtered_df['Video Views'].sum()):,}")
    with col2:
        if followers_df is not None:
            fs_latest   = followers_df.sort_values('Date').dropna(subset=['Date'])
            latest_fol  = int(fs_latest.iloc[-1]['Followers']) if len(fs_latest) > 0 else 0
            _, _, _, dl = get_follower_growth(followers_df, period, now, custom_range)
            st.metric("Followers", f"{latest_fol:,}", dl)
        else:
            st.metric("Followers", "—")
    with col3:
        avg_daily = get_avg_daily_views(overview_df, period_start)
        if avg_daily > 0:
            st.metric("Avg Daily Views", f"{avg_daily:,}")
        else:
            st.metric("Avg Views/Video", f"{int(filtered_df['Video Views'].mean()):,}")
    with col4:
        if viewers_df is not None:
            total_v = viewers_df['Total'].sum()
            ret_v   = viewers_df['Returning'].sum()
            ret_pct = ret_v / total_v * 100 if total_v > 0 else 0
            st.metric("Returning Viewers", f"{ret_pct:.1f}%",
                      "✅ Healthy" if ret_pct >= 40 else "⚠️ Low")
        else:
            st.metric("Videos analysiert", len(filtered_df))

    st.divider()

    # ── SHARE RATE TREND ──────────────────────────────────────────────────────
    # Intentionally uses all videos — shows full chronological trend line
    st.subheader("📈 Share Rate Trend (alle Videos chronologisch)")
    cutoff_trend = now - timedelta(hours=24)
    trend_df = content_df[
        content_df['Posted Date'].notna() &
        (content_df['Posted Date'] <= cutoff_trend)
    ].sort_values('Posted Date').copy()

    if len(trend_df) >= 4:
        trend_df['Label']         = trend_df['Posted Date'].apply(lambda d: fmt_date(d, 'short'))
        trend_df['Rolling_Share'] = trend_df['Share Rate'].rolling(4, min_periods=2).mean()
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=trend_df['Label'], y=trend_df['Share Rate'],
            mode='markers', name='Share Rate pro Video',
            marker=dict(color='#007AFF', size=9, opacity=0.65),
            hovertemplate='%{x}<br>Share Rate: %{y:.2f}%<extra></extra>'
        ))
        fig.add_trace(go.Scatter(
            x=trend_df['Label'], y=trend_df['Rolling_Share'],
            mode='lines', name='Ø 3 Videos',
            line=dict(color='#FF9500', width=2.5),
            hovertemplate='Ø 4: %{y:.2f}%<extra></extra>'
        ))
        fig.add_hline(y=0.3, line_dash='dash', line_color='#34C759',
                      annotation_text="Ziel 0.3%", annotation_position="top right")
        fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0),
                          legend=dict(orientation='h', y=1.12),
                          xaxis=dict(tickangle=-45, tickfont=dict(size=9)))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nicht genug Daten für Trend-Chart (min. 4 Videos).")

    # ── BEST DAY + BEST TIME ──────────────────────────────────────────────────
    col_day, col_time = st.columns(2)

    with col_day:
        st.subheader("📅 Best Day to Post")
        cutoff_24h_day = now - timedelta(hours=24)

        # FIX: Use filtered_df for period-sensitive analysis.
        # Last 7 Days only has 3 videos max → not enough per weekday → fall back to All Time.
        MIN_VIDEOS_FOR_DAY_CHART = 7
        if period == 'Last 7 Days' or len(filtered_df) < MIN_VIDEOS_FOR_DAY_CHART:
            day_source_df = content_df.copy()
            st.caption("📌 Zu wenig Videos im gewählten Zeitraum — zeigt All Time Daten.")
        else:
            day_source_df = filtered_df.copy()

        day_valid = day_source_df[
            day_source_df['Posted Date'].notna() &
            (day_source_df['Posted Date'] <= cutoff_24h_day)
        ].copy()

        if day_valid['Posted Date'].notna().sum() > 3:
            day_valid['Weekday'] = day_valid['Posted Date'].dt.dayofweek.map(
                {0:'Mo', 1:'Di', 2:'Mi', 3:'Do', 4:'Fr', 5:'Sa', 6:'So'}
            )
            day_stats = (day_valid.groupby('Weekday')['Video Views'].mean()
                           .reindex(['Mo','Di','Mi','Do','Fr','Sa','So'])
                           .fillna(0).reset_index())
            day_stats.columns = ['Day', 'Avg Views']
            fig = px.bar(day_stats, x='Day', y='Avg Views',
                         color='Avg Views', color_continuous_scale=['#1C1C1E', '#007AFF'],
                         text='Avg Views')
            fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
            fig.update_layout(height=300, showlegend=False, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nicht genug Videos für Wochentag-Auswertung.")

    with col_time:
        st.subheader("🕐 Best Time to Post")
        # NOTE: activity_df is aggregate follower-activity data (when your audience is online).
        # It does not change with period filter — this is correct by design.
        if activity_df is not None and 'Hour' in activity_df.columns:
            hourly    = activity_df.groupby('Hour')['Active'].mean().reset_index()
            hourly.columns = ['Hour', 'Avg Active']
            peak_hour = int(hourly.loc[hourly['Avg Active'].idxmax(), 'Hour'])
            post_hour = (peak_hour - 1) % 24
            post_str  = f"{post_hour}:30"
            st.caption(
                f"📌 Follower-Peak: **{peak_hour}:00** → optimaler Post: **{post_str}** "
                f"(30 Min. vor Peak) · _Basiert auf Follower-Aktivität, unabhängig vom Period-Filter_"
            )
            fig = px.bar(hourly, x='Hour', y='Avg Active',
                         color='Avg Active', color_continuous_scale=['#1C1C1E', '#FF9500'])
            fig.add_vline(x=post_hour, line_dash='dash', line_color='#FF9500',
                          annotation_text=f"~{post_str}", annotation_position="top right")
            fig.update_layout(height=300, showlegend=False, margin=dict(l=0, r=0, t=30, b=0),
                              xaxis=dict(tickmode='linear', dtick=2))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Lade das Followers-ZIP hoch — enthält FollowerActivity.csv mit Stunden-Daten.")

    # ── DAILY VIEWS ───────────────────────────────────────────────────────────
    if overview_df is not None:
        st.subheader("📈 Daily Views")
        ov = overview_df[overview_df['Views'] > 0].sort_values('Date')
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ov['Date'], y=ov['Views'], mode='lines+markers',
                                 line=dict(color='#007AFF', width=3)))
        fig.update_layout(height=270, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

    # ── FOLLOWERS ─────────────────────────────────────────────────────────────
    if followers_df is not None:
        st.subheader("👥 Follower Growth")
        col1, col2 = st.columns(2)
        fs = followers_df[followers_df['Followers'] > 0].sort_values('Date')
        with col1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=fs['Date'], y=fs['Followers'], mode='lines+markers',
                                     fill='tozeroy', line=dict(color='#34C759', width=2)))
            fig.update_layout(height=230, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=fs['Date'], y=fs['Daily Growth'], marker_color='#34C759'))
            fig.update_layout(height=230, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

    # ── TOP VIDEOS ────────────────────────────────────────────────────────────
    top_label = {
        'Last 7 Days':   '🏆 Analysierte Videos (letzte 3, >24h)',
        'Last 30 Days':  '🏆 Top Videos — letzte 30 Tage',
        'Last 3 Months': '🏆 Top Videos — letztes Quartal',
        'All Time':      '🏆 Top Videos — All Time',
        'Custom':        f"🏆 Top Videos — {fmt_date(custom_range[0],'numeric')}–{fmt_date(custom_range[1],'numeric')}" if custom_range else '🏆 Top Videos',
    }.get(period, '🏆 Top Videos')
    st.subheader(top_label)

    _top_cols = ['Video Title', 'Posted Date', 'Video Views', 'Share Rate', 'Engagement Rate',
                 'Saves', 'Save Rate', 'Category']
    _top_cols = [c for c in _top_cols if c in filtered_df.columns]
    top_n = filtered_df.sort_values('Video Views', ascending=False).head(
        4 if period == 'Last 7 Days' else 5
    )[_top_cols].copy()
    top_n['Posted Date']     = top_n['Posted Date'].apply(lambda d: fmt_date(d, 'weekday'))
    top_n['Video Views']     = top_n['Video Views'].apply(lambda x: f"{int(x):,}")
    top_n['Share Rate']      = top_n['Share Rate'].apply(lambda x: f"{x:.2f}%")
    top_n['Engagement Rate'] = top_n['Engagement Rate'].apply(lambda x: f"{x:.1f}%")
    has_saves_top = 'Saves' in filtered_df.columns and filtered_df['Saves'].sum() > 0
    if 'Saves' in top_n.columns:
        top_n['Saves']     = top_n['Saves'].apply(lambda x: int(x) if has_saves_top else "—")
    if 'Save Rate' in top_n.columns:
        top_n['Save Rate'] = top_n['Save Rate'].apply(lambda x: f"{x:.2f}%" if has_saves_top else "—")
    top_n['Video Title']     = top_n['Video Title'].str[:60] + '…'
    st.dataframe(top_n, use_container_width=True, hide_index=True)

    # ── HOOK-TYP EDITOR ───────────────────────────────────────────────────────
    with st.expander("🏷️ Hook-Typ taggen", expanded=False):
        st.caption("Tags werden lokal gespeichert und erscheinen im Callout und in der Hook-Analyse.")
        # Editor always shows last 12 videos regardless of filter — intentional for tagging workflow
        edit_df  = filtered_df if period == 'Last 7 Days' else \
                   content_df.sort_values('Posted Date', ascending=False).head(12)
        ht_changed = False
        for _, row in edit_df.iterrows():
            link    = row.get('Video Link', '')
            title   = str(row.get('Video Title', ''))[:68]
            current = hook_types.get(link, '—')
            c_t, c_s = st.columns([4, 2])
            with c_t: st.text(title)
            with c_s:
                idx = HOOK_TYPE_OPTIONS.index(current) if current in HOOK_TYPE_OPTIONS else 0
                new_val = st.selectbox("", HOOK_TYPE_OPTIONS, index=idx,
                                       key=f"ht_{link}", label_visibility="collapsed")
                if new_val != current:
                    hook_types[link] = new_val
                    ht_changed = True
        if ht_changed:
            save_hook_types(hook_types)
            st.success("✅ Gespeichert")

    # ── KATEGORIE-EDITOR ──────────────────────────────────────────────────────
    with st.expander("✏️ Kategorien korrigieren", expanded=False):
        st.caption("Überschreibt die automatische Erkennung dauerhaft (category_overrides.json).")
        cat_changed = False
        for _, row in filtered_df.iterrows():
            link    = row.get('Video Link', '')
            title   = str(row.get('Video Title', ''))[:68]
            current = overrides.get(link, row.get('Category', 'Other'))
            c_t, c_s = st.columns([4, 2])
            with c_t: st.text(title)
            with c_s:
                idx = CATEGORIES_AVAILABLE.index(current) \
                      if current in CATEGORIES_AVAILABLE else len(CATEGORIES_AVAILABLE) - 1
                new_cat = st.selectbox("", CATEGORIES_AVAILABLE, index=idx,
                                       key=f"cat_{link}", label_visibility="collapsed")
                if new_cat != current:
                    overrides[link] = new_cat
                    cat_changed = True
        if cat_changed:
            save_cat_overrides(overrides)
            st.success("✅ Gespeichert — wird beim nächsten Reload angewendet")

    # ── HOOK-TYP ANALYSE ──────────────────────────────────────────────────────
    # FIX: Use filtered_df instead of content_df so the analysis respects the period filter.
    # Falls back to content_df if filtered period has fewer than 3 tagged videos.
    if 'Video Link' in filtered_df.columns:
        ct = filtered_df.copy()
        ct['Hook Type'] = ct['Video Link'].map(hook_types).fillna('—')
        tagged = ct[ct['Hook Type'].isin(HOOK_TYPE_OPTIONS[1:])]

        # If the current period has too few tagged videos, fall back to all-time
        if len(tagged) < 3 and period != 'All Time':
            ct_all = content_df.copy()
            ct_all['Hook Type'] = ct_all['Video Link'].map(hook_types).fillna('—')
            tagged = ct_all[ct_all['Hook Type'].isin(HOOK_TYPE_OPTIONS[1:])]
            hook_fallback = True
        else:
            hook_fallback = False

        if len(tagged) >= 3:
            st.subheader("🏷️ Hook-Typ Performance")
            if hook_fallback:
                st.caption("📌 Zu wenig getaggte Videos im gewählten Zeitraum — zeigt All Time Daten.")
            has_saves_tagged = 'Saves' in tagged.columns and tagged['Saves'].sum() > 0
            _agg = {'Avg_Views': ('Video Views', 'mean'),
                    'Avg_Share': ('Share Rate',  'mean'),
                    'Count':     ('Video Title', 'count')}
            if has_saves_tagged:
                _agg['Avg_Save'] = ('Save Rate', 'mean')
            hook_stats = (tagged.groupby('Hook Type')
                                .agg(**_agg)
                                .round(2).reset_index()
                                .sort_values('Avg_Views', ascending=False))
            ch1, ch2, ch3 = st.columns(3)
            with ch1:
                fig = px.bar(hook_stats, x='Hook Type', y='Avg_Views',
                             text='Avg_Views', color='Avg_Views',
                             color_continuous_scale=['#1C1C1E', '#007AFF'], title='Avg Views')
                fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                fig.update_layout(height=270, showlegend=False, margin=dict(l=0,r=0,t=30,b=0))
                st.plotly_chart(fig, use_container_width=True)
            with ch2:
                fig = px.bar(hook_stats, x='Hook Type', y='Avg_Share',
                             text='Avg_Share', color='Avg_Share',
                             color_continuous_scale=['#1C1C1E', '#FF9500'], title='Avg Share Rate %')
                fig.update_traces(texttemplate='%{text:.2f}%', textposition='outside')
                fig.update_layout(height=270, showlegend=False, margin=dict(l=0,r=0,t=30,b=0))
                st.plotly_chart(fig, use_container_width=True)
            with ch3:
                if 'Avg_Save' in hook_stats.columns:
                    fig = px.bar(hook_stats, x='Hook Type', y='Avg_Save',
                                 text='Avg_Save', color='Avg_Save',
                                 color_continuous_scale=['#1C1C1E', '#34C759'], title='Avg Save Rate %')
                    fig.update_traces(texttemplate='%{text:.2f}%', textposition='outside')
                    fig.update_layout(height=270, showlegend=False, margin=dict(l=0,r=0,t=30,b=0))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Keine Save-Daten verfügbar.")

    # ── CATEGORY PERFORMANCE ──────────────────────────────────────────────────
    st.subheader("📁 Category Performance")
    cat_stats = (filtered_df.groupby('Category')
                             .agg(Avg_Views=('Video Views',     'mean'),
                                  Avg_Eng   =('Engagement Rate','mean'),
                                  Count     =('Video Title',    'count'))
                             .round(1).reset_index()
                             .sort_values('Avg_Views', ascending=False))
    fig = px.bar(cat_stats, x='Category', y='Avg_Views',
                 color='Avg_Eng', color_continuous_scale=['red', 'yellow', 'green'],
                 text='Avg_Views',
                 labels={'Avg_Views': 'Avg Views', 'Avg_Eng': 'Avg Engagement %'})
    fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    fig.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    # ── CALLOUT GENERATOR ─────────────────────────────────────────────────────
    st.divider()
    st.subheader("📋 Obsidian Callout generieren")
    callout_mode = None
    if period == 'Last 7 Days':
        callout_mode = 'weekly'
    elif period == 'Last 30 Days':
        callout_mode = 'monthly'
    elif period == 'Custom' and custom_range:
        span_days = (custom_range[1] - custom_range[0]).days
        callout_mode = 'weekly' if span_days <= 10 else 'monthly'
        st.caption(f"📌 Custom-Zeitraum ({span_days} Tage) → "
                   f"{'Wochen' if callout_mode == 'weekly' else 'Monats'}-Callout verwendet.")

    if callout_mode == 'weekly':
        _FIELDS_TT = [
            ('uhrzeit',      'Uhrzeit',      '17:30'),
            ('laenge',       'Länge',         '60s'),
            ('fyp',          'FYP%',          '45%'),
            ('tt_saves',     'TT Saves',      '450'),
            ('retention',    'Retention',     '35%'),
            ('watch',        'Ø Watch',       '28s'),
            ('tt_followers', 'TT Follower',   '+5'),
            ('absprung',     'Absprung-Sek',  '0:03'),
        ]
        _FIELDS_IG = [
            ('ig_views',     'IG Views',      '1.2k'),
            ('ig_saves',     'IG Saves',      '23'),
            ('ig_shares',    'IG Shares',     '15'),
            ('ig_likes',     'IG Likes',      '120'),
            ('ig_comments',  'IG Kommentare', '3'),
            ('ig_followers', 'IG Follower',   '+3'),
            ('ig_watch',     'IG Ø Watch',    '6s'),
            ('ig_skip',      'IG Skip',       '66.2%'),
        ]
        _FIELDS_META = [
            ('kurz',         'Kurzname',      'Font Roles'),
            ('blueprint',    'Blueprint',     'R / M'),
            ('einstieg',     'Einstieg',      '✅ / —'),
        ]
        _FIELDS_AUD = [
            ('tt_laender',   'TT-Länder',     'US 13.3 / DE 6.2 / BR 4.9'),
            ('tt_quellen',   'TT-Quellen',    'FYP 88.6 / Gefolgt 7.0 / Profil 3.2'),
            ('tt_zuschauer', 'TT-Zuschauer',  '4 % neu / 96 % wiederk., 25 % Nicht-Follower'),
            ('ig_laender',   'IG-Länder',     'DE 8.0 / IN 7.7 / US 6.7'),
            ('ig_quellen',   'IG-Quellen',    'Feed 51.7 / Reels-Tab 24.4 / Stories 15.7'),
        ]
        vm_changed = False
        ht_changed_weekly = False
        with st.expander("✏️ Manuelle Werte eintragen", expanded=True):
            for _, row in filtered_df.sort_values('Posted Date').iterrows():
                link  = row.get('Video Link', '')
                title = str(row.get('Video Title', ''))[:70]
                m     = video_manual.get(link, {})
                c_title, c_hook = st.columns([5, 2])
                with c_title:
                    st.markdown(f"**{title}**")
                with c_hook:
                    current_hook = hook_types.get(link, '—')
                    hook_idx = HOOK_TYPE_OPTIONS.index(current_hook) if current_hook in HOOK_TYPE_OPTIONS else 0
                    new_hook = st.selectbox("Hook-Typ", HOOK_TYPE_OPTIONS, index=hook_idx,
                                            key=f"ht_weekly_{link}", label_visibility="collapsed")
                    if new_hook != current_hook:
                        hook_types[link] = new_hook
                        ht_changed_weekly = True
                tt_cols = st.columns(len(_FIELDS_TT))
                for col, (key, label, ph) in zip(tt_cols, _FIELDS_TT):
                    with col:
                        val = st.text_input(label, value=m.get(key, ''), key=f"{key}_{link}",
                                            placeholder=ph, label_visibility="visible")
                        if val != m.get(key, ''):
                            video_manual.setdefault(link, {})[key] = val
                            vm_changed = True
                for fields in (_FIELDS_IG, _FIELDS_META, _FIELDS_AUD):
                    cols = st.columns(len(fields))
                    for col, (key, label, ph) in zip(cols, fields):
                        with col:
                            val = st.text_input(label, value=m.get(key, ''), key=f"{key}_{link}",
                                                placeholder=ph, label_visibility="visible")
                            if val != m.get(key, ''):
                                video_manual.setdefault(link, {})[key] = val
                                vm_changed = True
                val = st.text_input("Notiz zum Video (erscheint im ↳-Absatz unter der Einordnung)",
                                    value=m.get('notiz', ''), key=f"notiz_{link}",
                                    placeholder="z.B. 75 % Follower trotz 88.6 % FYP → fast nur an Bestandspublikum ausgespielt")
                if val != m.get('notiz', ''):
                    video_manual.setdefault(link, {})['notiz'] = val
                    vm_changed = True
                drop_cols = st.columns(2)
                with drop_cols[0]:
                    val = st.text_input("Text/Szene bei Absprung", value=m.get('absprung_text', ''),
                                        key=f"absprung_text_{link}", placeholder="z.B. 'abstrakter Begriff X' / Szenenwechsel")
                    if val != m.get('absprung_text', ''):
                        video_manual.setdefault(link, {})['absprung_text'] = val
                        vm_changed = True
                with drop_cols[1]:
                    val = st.text_area("Voiceover-Text (für Musteranalyse über Zeit)", value=m.get('voiceover', ''),
                                       key=f"voiceover_{link}", height=68,
                                       placeholder="Kompletter VO-Text, um später Absprung mit Formulierungen zu korrelieren")
                    if val != m.get('voiceover', ''):
                        video_manual.setdefault(link, {})['voiceover'] = val
                        vm_changed = True
                st.divider()
        if vm_changed:
            save_video_manual(video_manual)
            st.toast("✅ Gespeichert")
        if ht_changed_weekly:
            save_hook_types(hook_types)
            st.toast("✅ Hook-Typ gespeichert")

        callout = build_callout(filtered_df, viewers_df, followers_df, activity_df, now, hook_types, video_manual,
                                custom_range=custom_range if period == 'Custom' else None,
                                content_df=content_df, gender_df=gender_df, territories_df=territories_df)
        st.caption("___ = noch nachtragen (IG-Kontowerte, Notizen, Test). Status-Pfeile = Trend vs. Vorwoche.")
        st.code(callout, language=None)
    elif callout_mode == 'monthly':
        callout = build_month_callout(filtered_df, viewers_df, followers_df, overview_df, now, hook_types, video_manual,
                                      custom_range=custom_range if period == 'Custom' else None)
        st.caption("Werte ohne weekly-Eintrag bleiben ___ (in Last 7 Days nachtragen). Bestätigt/Widerlegt/Hypothese selbst ausfüllen.")
        st.code(callout, language=None)
    else:
        st.info("💡 Wechsle zu **Last 7 Days** oder **Last 30 Days** für den Callout.")


# ── PROCESS UPLOADS ───────────────────────────────────────────────────────────

def _process_uploads(uploaded_files):
    all_content = []; all_overview = []; all_viewers = []
    all_followers = []; all_activity = []
    gender_df = None; territories_df = None

    for uf in uploaded_files:
        ex = extract_csvs_from_zip(uf)
        # Pro Datei datieren, solange die Zeilenreihenfolge noch die des Exports ist
        for key in ('overview', 'viewers', 'followers'):
            if key in ex and 'Date' in ex[key].columns:
                ex[key]['Date'] = smart_parse_dates(ex[key]['Date'], chronological=True)
        if 'content'           in ex: all_content.append(ex['content'])
        if 'overview'          in ex: all_overview.append(ex['overview'])
        if 'viewers'           in ex: all_viewers.append(ex['viewers'])
        if 'followers'         in ex: all_followers.append(ex['followers'])
        if 'follower_activity' in ex: all_activity.append(ex['follower_activity'])
        if 'gender'            in ex: gender_df      = ex['gender']
        if 'territories'       in ex: territories_df = ex['territories']

    if all_content:
        df = pd.concat(all_content, ignore_index=True)
        df = df.rename(columns={
            'Video title':  'Video Title', 'Video link': 'Video Link',
            'Total views':  'Video Views', 'Total likes': 'Likes',
            'Total comments': 'Comments', 'Total shares': 'Shares',
            'Total saves':  'Saves',
            'Post time':    'Posted Date',
        })
        for col in ['Video Views', 'Likes', 'Comments', 'Shares']:
            df[col] = clean_numeric(df[col])
        if 'Saves' in df.columns:
            df['Saves'] = clean_numeric(df['Saves']).astype(int)
        else:
            df['Saves'] = 0
        df = df.sort_values('Video Views', ascending=False)
        df = df.drop_duplicates(subset=['Video Link'], keep='first')
        df['Posted Date']     = smart_parse_dates(df['Posted Date'])
        df['Share Rate']      = (df['Shares'] / df['Video Views'].replace(0, 1) * 100).clip(0, 100)
        df['Engagement Rate'] = ((df['Likes'] + df['Comments'] + df['Shares']) /
                                  df['Video Views'].replace(0, 1) * 100).clip(0, 100)
        df['Save Rate']       = (df['Saves'] / df['Video Views'].replace(0, 1) * 100).clip(0, 100)
        df['Category']        = df['Video Title'].apply(categorize_topic)
        df.to_csv(DATA_DIR / 'content.csv', index=False)
        st.sidebar.success(f"✅ {len(df)} unique videos")

    if all_overview:
        df = pd.concat(all_overview, ignore_index=True)
        df = df.rename(columns={'Video Views': 'Views'})
        for col in ['Views', 'Profile Views', 'Likes', 'Comments', 'Shares']:
            if col in df.columns: df[col] = clean_numeric(df[col])
        df = df[df['Views'] > 0].dropna(subset=['Date'])
        df = df.drop_duplicates(subset=['Date'], keep='last')
        df.to_csv(DATA_DIR / 'overview.csv', index=False)
        st.sidebar.success(f"✅ Overview: {len(df)} Tage")

    if all_viewers:
        df = pd.concat(all_viewers, ignore_index=True)
        df = df.rename(columns={
            'Total Viewers': 'Total', 'New Viewers': 'New', 'Returning Viewers': 'Returning'
        })
        for col in ['Total', 'New', 'Returning']:
            if col in df.columns: df[col] = clean_numeric(df[col])
        df = df[df['Total'] > 0].dropna(subset=['Date'])
        df = df.drop_duplicates(subset=['Date'], keep='last')
        df.to_csv(DATA_DIR / 'viewers.csv', index=False)
        st.sidebar.success(f"✅ Viewers: {len(df)} Tage")

    if all_followers:
        df = pd.concat(all_followers, ignore_index=True)
        df = df.rename(columns={'Difference in followers from previous day': 'Daily Growth'})
        for col in ['Followers', 'Daily Growth']:
            if col in df.columns: df[col] = clean_numeric(df[col])
        df = df[df['Followers'] > 0].dropna(subset=['Date'])
        df = df.drop_duplicates(subset=['Date'], keep='last')
        df.to_csv(DATA_DIR / 'followers.csv', index=False)
        st.sidebar.success(f"✅ Followers bis {fmt_date(df['Date'].max(), 'full')}")

    if all_activity:
        df = pd.concat(all_activity, ignore_index=True)
        df.columns = [c.strip() for c in df.columns]
        rename_map = {}
        for c in df.columns:
            cl = c.lower()
            if 'hour'   in cl: rename_map[c] = 'Hour'
            elif 'active' in cl: rename_map[c] = 'Active'
        df = df.rename(columns=rename_map)
        if 'Hour' in df.columns and 'Active' in df.columns:
            df['Hour']   = clean_numeric(df['Hour']).astype(int)
            df['Active'] = clean_numeric(df['Active'])
            df = df[df['Active'] > 0]
            df.to_csv(DATA_DIR / 'activity.csv', index=False)
            st.sidebar.success("✅ Activity: ✓")

    for df, cols, name in ((gender_df, ['Gender', 'Share'], 'gender.csv'),
                           (territories_df, ['Territory', 'Share'], 'territories.csv')):
        if df is not None and len(df.columns) >= 2:
            df = df.iloc[:, :2].copy()
            df.columns = cols
            df['Share'] = pd.to_numeric(df['Share'], errors='coerce').fillna(0)
            df.to_csv(DATA_DIR / name, index=False)
    if gender_df is not None or territories_df is not None:
        st.sidebar.success("✅ Follower-Länder/Geschlecht: ✓")

    st.sidebar.success("🎉 Fertig — Daten aktualisiert.")


if __name__ == "__main__":
    main()