import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import zipfile
import os
import json
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

HOOK_TYPE_OPTIONS    = ["—", "Kontrovers", "Mechanismus", "Regel + Zahl", "Beweis", "Vergleich"]
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


def smart_parse_dates(series):
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

    months = []
    for val in series.dropna():
        parts = str(val).strip().split()
        if len(parts) >= 2:
            _, m = extract_day_month(parts)
            if m: months.append(m)
    spans_year_boundary = (1 in months and 12 in months)

    def parse_one(date_str):
        if pd.isna(date_str) or str(date_str).strip() in ('undefined', ''):
            return pd.NaT
        parts = str(date_str).strip().split()
        if len(parts) < 2: return pd.NaT
        try:
            day, month = extract_day_month(parts)
            if day is None or month is None:
                return pd.NaT
            year = now.year
            if spans_year_boundary and month >= 10:
                year = now.year - 1
            parsed = datetime(year, month, day)
            if parsed > now + timedelta(days=60):
                parsed = datetime(year - 1, month, day)
            return parsed
        except:
            return pd.NaT
    return series.apply(parse_one)


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


def get_follower_growth(followers_df, period, now):
    if followers_df is None or len(followers_df) == 0:
        return 0, None, None, "—"
    fs = followers_df.sort_values('Date').dropna(subset=['Date'])
    if len(fs) == 0:
        return 0, None, None, "—"
    if period == 'Last 7 Days':
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


def apply_period_filter(content_df, period, now):
    if period == 'Last 7 Days':
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


def generate_insights(filtered_df, viewers_df, followers_df, period, now):
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
        growth, _, _, label = get_follower_growth(followers_df, period, now)
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

def build_callout(filtered_df, viewers_df, followers_df, activity_df, now, hook_types, video_manual=None):
    today     = now.strftime("%d.%m.%Y")
    avg_share     = filtered_df['Share Rate'].mean()
    avg_eng       = filtered_df['Engagement Rate'].mean()
    total_views   = int(filtered_df['Video Views'].sum())
    # Aggregate saves: prefer manual entries, fall back to TikTok export
    total_saves_agg = 0
    for _, row in filtered_df.iterrows():
        link = row.get('Video Link', '')
        tt_saves_export = int(row['Saves']) if 'Saves' in row and pd.notna(row['Saves']) else 0
        mv_saves = (video_manual or {}).get(link, {}).get('tt_saves', '')
        try:
            manual_saves = int(float(str(mv_saves or '0').replace(',', '')))
        except (ValueError, AttributeError):
            manual_saves = 0
        total_saves_agg += max(tt_saves_export, manual_saves)
    avg_save_rate = (total_saves_agg / total_views * 100) if total_saves_agg > 0 and total_views > 0 else None
    share_status = "✅" if avg_share >= 0.3 else "⚠️"
    eng_status   = "✅" if avg_eng   >= 4.0 else "⚠️"
    save_status  = ("✅" if avg_save_rate >= 1.5 else "⚠️") if avg_save_rate is not None else ""
    tt_save_str  = f"Ø {avg_save_rate:.2f}%" if avg_save_rate is not None else "___"

    # IG summary: aggregate from per-video manual entries
    ig_views_sum  = 0.0
    ig_saves_sum  = 0.0
    ig_shares_sum = 0.0
    ig_fol_sum    = 0.0
    for _, row in filtered_df.iterrows():
        mv_row = (video_manual or {}).get(row.get('Video Link', ''), {})
        def _parse(val):
            try:
                return float(str(val or '0').replace(',', '').replace('k','000').replace('K','000'))
            except (ValueError, AttributeError):
                return 0.0
        ig_views_sum  += _parse(mv_row.get('ig_views'))
        ig_saves_sum  += _parse(mv_row.get('ig_saves'))
        ig_shares_sum += _parse(mv_row.get('ig_shares'))
        ig_fol_sum    += _parse(mv_row.get('ig_followers'))
    ig_views_str       = f"{int(ig_views_sum):,}" if ig_views_sum > 0 else "___"
    ig_save_rate_str   = f"Ø {ig_saves_sum  / ig_views_sum * 100:.2f}%" if ig_views_sum > 0 else "___"
    ig_share_rate_str  = f"Ø {ig_shares_sum / ig_views_sum * 100:.2f}%" if ig_views_sum > 0 else "—"
    ig_share_status    = ("✅" if ig_shares_sum / ig_views_sum * 100 >= 0.3 else "⚠️") if ig_views_sum > 0 else ""
    ig_fol_weekly_str  = f"+{int(ig_fol_sum)}" if ig_fol_sum > 0 else "___"

    ret_str, ret_status = "—", ""
    if viewers_df is not None and len(viewers_df) > 0:
        total = viewers_df['Total'].sum()
        ret   = viewers_df['Returning'].sum()
        pct   = ret / total * 100 if total > 0 else 0
        ret_str    = f"{pct:.1f}%"
        ret_status = "✅" if pct >= 40 else "⚠️"

    fol_str = "—"
    if followers_df is not None:
        growth, _, _, _ = get_follower_growth(followers_df, 'Last 7 Days', now)
        if growth > 0: fol_str = f"+{growth}"

    post_time_str = "17:30"
    if activity_df is not None and 'Hour' in activity_df.columns:
        hourly        = activity_df.groupby('Hour')['Active'].mean()
        peak_hour     = int(hourly.idxmax())
        post_hour     = (peak_hour - 1) % 24
        post_time_str = f"{post_hour}:30"

    top  = filtered_df.nlargest(1,  'Video Views').iloc[0]
    flop = filtered_df.nsmallest(1, 'Video Views').iloc[0]

    vids = filtered_df.sort_values('Posted Date').copy()
    table_rows = []
    for _, row in vids.iterrows():
        raw_title = str(row['Video Title'])
        title     = (raw_title[:52] + "…") if len(raw_title) > 52 else raw_title
        cat       = row.get('Category', '—')
        link      = row.get('Video Link', '')
        hook      = hook_types.get(link, '')
        hook_tag  = f" [{hook}]" if hook and hook != "—" else ""
        wd        = WEEKDAY_DE.get(row['Posted Date'].weekday(), '') if pd.notna(row['Posted Date']) else ''
        views     = int(row['Video Views'])
        saves     = int(row['Saves']) if 'Saves' in row and pd.notna(row['Saves']) else 0
        mv        = (video_manual or {}).get(link, {})
        try:
            saves = max(saves, int(float(str(mv.get('tt_saves', '') or '0').replace(',', ''))))
        except (ValueError, AttributeError):
            pass
        save_rate = f"{saves / views * 100:.2f}%" if saves > 0 and views > 0 else "___"
        uhrzeit   = mv.get('uhrzeit',     '—:—')
        laenge    = mv.get('laenge',      '___')
        fyp       = mv.get('fyp',         '___')
        retention = mv.get('retention',   '___')
        watch     = mv.get('watch',       '___')
        tt_fol    = mv.get('tt_followers','___')
        ig_views  = mv.get('ig_views',    '___')
        ig_saves  = mv.get('ig_saves',    '___')
        ig_shares = mv.get('ig_shares',   '___')
        ig_fol    = mv.get('ig_followers','___')
        ig_watch  = mv.get('ig_watch',    '___')
        def _ig_num(val):
            try:
                return float(str(val or '0').replace(',', '').replace('k','000').replace('K','000'))
            except (ValueError, AttributeError):
                return 0.0
        ig_views_num  = _ig_num(ig_views)
        ig_sr         = f"{_ig_num(ig_saves)  / ig_views_num * 100:.2f}%" if ig_views_num > 0 else '___'
        ig_share_rate = f"{_ig_num(ig_shares) / ig_views_num * 100:.2f}%" if ig_views_num > 0 else '___'
        table_rows.append(f"> | {title}{hook_tag} | {cat} | {wd} {uhrzeit} | {laenge} | {fyp} | {views:,} → ___ | {saves:,} → ___ | {save_rate} | {retention} → ___ | {watch} → ___ | {tt_fol} → ___ | {ig_views} → ___ | {ig_saves} → ___ | {ig_shares} → ___ | {ig_sr} | {ig_share_rate} | {ig_fol} → ___ | {ig_watch} |")

    table = "\n".join(table_rows)
    top_title  = str(top['Video Title'])[:60]
    flop_title = str(flop['Video Title'])[:60]

    return (
        f"> [!tiktok]+ {today}\n"
        f">\n"
        f"> | Metrik | TikTok | IG | Status |\n"
        f"> | --- | --- | --- | --- |\n"
        f"> | Views | {total_views:,} | {ig_views_str} | |\n"
        f"> | New Followers | {fol_str} | {ig_fol_weekly_str} | |\n"
        f"> | Save Rate | {tt_save_str} | {ig_save_rate_str} | {save_status} |\n"
        f"> | Share Rate | {avg_share:.2f}% | {ig_share_rate_str} | {share_status} |\n"
        f"> | Engagement | {avg_eng:.1f}% | — | {eng_status} |\n"
        f"> | Returning Viewers | {ret_str} | — | {ret_status} |\n"
        f"> | Optimale Postzeit | {post_time_str} | — | |\n"
        f">\n"
        f"> 🏆 **Top:** \"{top_title}…\"\n"
        f"> ↳ _\n"
        f"> 📉 **Flop:** \"{flop_title}…\"\n"
        f"> ↳ _\n"
        f">\n"
        f"> 📊 **Video-Details:**\n"
        f">\n"
        f"> | Video | Thema | Uhrzeit | Länge | FYP | TT Views | TT Saves | TT Save Rate | Retention | Ø Watch | TT New Followers | IG Views | IG Saves | IG Shares | IG Save Rate | IG Share Rate | IG New Followers | IG Ø Watch |\n"
        f"> | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        f"{table}\n"
        f">\n"
        f"> ↳ _Noch steigende Videos nächste Woche nachtragen_\n"
        f">\n"
        f"> 🧪 **Letzter Test:** \n"
        f"> 🔬 **Nächste Woche:** \n"
        f"> 🔗 **Muster:** _"
    )


def build_month_callout(filtered_df, viewers_df, followers_df, overview_df, now, hook_types):
    today = now.strftime("%d.%m.%Y")

    # Follower total + 30d growth
    fol_total_str = "—"
    fol_growth_str = "—"
    if followers_df is not None and len(followers_df) > 0:
        fs = followers_df.sort_values('Date').dropna(subset=['Date'])
        if len(fs) > 0:
            fol_total_str = f"{int(fs.iloc[-1]['Followers']):,}"
        growth, _, _, _ = get_follower_growth(followers_df, 'Last 30 Days', now)
        fol_growth_str = f"+{growth}" if growth > 0 else str(growth)

    # Total views + Ø daily views (30d)
    total_views = int(filtered_df['Video Views'].sum())
    avg_daily_str = "—"
    if overview_df is not None and len(overview_df) > 0:
        cutoff = now - timedelta(days=30)
        ov = overview_df[(overview_df['Date'] >= cutoff) & (overview_df['Views'] > 0)]
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

    # Blueprint table — grouped by hook type, sorted by Ø Views desc
    vids = filtered_df.copy()
    if 'Video Link' in vids.columns:
        vids['_hook'] = vids['Video Link'].map(hook_types).fillna('—')
    else:
        vids['_hook'] = '—'
    has_saves_month = 'Saves' in vids.columns and vids['Saves'].sum() > 0
    _bp_agg = {'count': ('Video Views', 'count'), 'avg_views': ('Video Views', 'mean')}
    if has_saves_month:
        _bp_agg['avg_save'] = ('Save Rate', 'mean')
    bp = (vids.groupby('_hook')
              .agg(**_bp_agg)
              .reset_index()
              .sort_values('avg_views', ascending=False))
    circled = "①②③④⑤⑥⑦⑧⑨"
    bp_rows = []
    for i, (_, r) in enumerate(bp.iterrows()):
        num  = circled[i] if i < len(circled) else f"{i+1}."
        hook = r['_hook']
        save_cell = f"{r['avg_save']:.2f}%" if has_saves_month and 'avg_save' in r.index else "___"
        bp_rows.append(
            f"> | {num} {hook} | {int(r['count'])} | {int(r['avg_views']):,} | {save_cell} | ___ | ___ |"
        )
    blueprint_table = "\n".join(bp_rows) if bp_rows else "> | — | — | — | — | — | — |"

    # Top category by avg views
    cat_avg = vids.groupby('Category')['Video Views'].mean()
    top_cat       = cat_avg.idxmax() if len(cat_avg) > 0 else "—"
    top_cat_views = f"{int(cat_avg.max()):,}" if len(cat_avg) > 0 else "—"

    return (
        f"> [!tiktok-month]+ {today}\n"
        f">\n"
        f"> 👥 **Follower:** {fol_total_str} ({fol_growth_str})\n"
        f"> 👁 **Views (30d):** {total_views:,}\n"
        f"> 📅 **Ø Daily Views:** {avg_daily_str}\n"
        f"> 🔄 **Returning Viewers:** {ret_str}\n"
        f"> 💬 **Ø Engagement:** {avg_eng:.1f}%\n"
        f"> 📤 **Ø Share Rate:** {avg_share:.2f}%\n"
        f"> 🔖 **Ø Save Rate:** ___\n"
        f"> 📸 **IG Views:** ___\n"
        f"> 💾 **IG Saves:** ___\n"
        f"> ⏱ **IG Ø Watch:** ___\n"
        f">\n"
        f"> | Blueprint | Videos | Ø Views | Ø Save Rate | Ø Watchtime | Ø FYP |\n"
        f"> | --- | --- | --- | --- | --- | --- |\n"
        f"{blueprint_table}\n"
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
                      ['All Time', 'Last 3 Months', 'Last 30 Days', 'Last 7 Days'],
                      horizontal=True)
    filtered_df, period_start, filter_hint = apply_period_filter(content_df, period, now)

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
    insights = generate_insights(filtered_df, viewers_df, followers_df, period, now)
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
            _, _, _, dl = get_follower_growth(followers_df, period, now)
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
    if period == 'Last 7 Days':
        _FIELDS_TT = [
            ('uhrzeit',      'Uhrzeit',      '17:30'),
            ('laenge',       'Länge',         '60s'),
            ('fyp',          'FYP%',          '45%'),
            ('tt_saves',     'TT Saves',      '450'),
            ('retention',    'Retention',     '35%'),
            ('watch',        'Ø Watch',       '28s'),
            ('tt_followers', 'TT Follower',   '+5'),
        ]
        _FIELDS_IG = [
            ('ig_views',     'IG Views',      '1.2k'),
            ('ig_saves',     'IG Saves',      '23'),
            ('ig_shares',    'IG Shares',     '15'),
            ('ig_followers', 'IG Follower',   '+3'),
            ('ig_watch',     'IG Ø Watch',    '22s'),
        ]
        vm_changed = False
        with st.expander("✏️ Manuelle Werte eintragen", expanded=True):
            for _, row in filtered_df.sort_values('Posted Date').iterrows():
                link  = row.get('Video Link', '')
                title = str(row.get('Video Title', ''))[:70]
                m     = video_manual.get(link, {})
                st.markdown(f"**{title}**")
                tt_cols = st.columns(len(_FIELDS_TT))
                for col, (key, label, ph) in zip(tt_cols, _FIELDS_TT):
                    with col:
                        val = st.text_input(label, value=m.get(key, ''), key=f"{key}_{link}",
                                            placeholder=ph, label_visibility="visible")
                        if val != m.get(key, ''):
                            video_manual.setdefault(link, {})[key] = val
                            vm_changed = True
                ig_cols = st.columns(len(_FIELDS_IG))
                for col, (key, label, ph) in zip(ig_cols, _FIELDS_IG):
                    with col:
                        val = st.text_input(label, value=m.get(key, ''), key=f"{key}_{link}",
                                            placeholder=ph, label_visibility="visible")
                        if val != m.get(key, ''):
                            video_manual.setdefault(link, {})[key] = val
                            vm_changed = True
                st.divider()
        if vm_changed:
            save_video_manual(video_manual)
            st.toast("✅ Gespeichert")

        callout = build_callout(filtered_df, viewers_df, followers_df, activity_df, now, hook_types, video_manual)
        st.caption("Top/Flop-Notiz und Muster-Zeile manuell befüllen. → ___ Werte nächste Woche nachtragen.")
        st.code(callout, language=None)
    elif period == 'Last 30 Days':
        callout = build_month_callout(filtered_df, viewers_df, followers_df, overview_df, now, hook_types)
        st.caption("Ø Watchtime und Ø FYP pro Blueprint manuell ergänzen. Bestätigt/Widerlegt/Hypothese selbst ausfüllen.")
        st.code(callout, language=None)
    else:
        st.info("💡 Wechsle zu **Last 7 Days** oder **Last 30 Days** für den Callout.")


# ── PROCESS UPLOADS ───────────────────────────────────────────────────────────

def _process_uploads(uploaded_files):
    all_content = []; all_overview = []; all_viewers = []
    all_followers = []; all_activity = []

    for uf in uploaded_files:
        ex = extract_csvs_from_zip(uf)
        if 'content'           in ex: all_content.append(ex['content'])
        if 'overview'          in ex: all_overview.append(ex['overview'])
        if 'viewers'           in ex: all_viewers.append(ex['viewers'])
        if 'followers'         in ex: all_followers.append(ex['followers'])
        if 'follower_activity' in ex: all_activity.append(ex['follower_activity'])

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
        df['Date'] = smart_parse_dates(df['Date'])
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
        df['Date'] = smart_parse_dates(df['Date'])
        for col in ['Total', 'New', 'Returning']:
            if col in df.columns: df[col] = clean_numeric(df[col])
        df = df[df['Total'] > 0].dropna(subset=['Date'])
        df = df.drop_duplicates(subset=['Date'], keep='last')
        df.to_csv(DATA_DIR / 'viewers.csv', index=False)
        st.sidebar.success(f"✅ Viewers: {len(df)} Tage")

    if all_followers:
        df = pd.concat(all_followers, ignore_index=True)
        df = df.rename(columns={'Difference in followers from previous day': 'Daily Growth'})
        df['Date'] = smart_parse_dates(df['Date'])
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

    st.sidebar.success("🎉 Fertig — Daten aktualisiert.")


if __name__ == "__main__":
    main()