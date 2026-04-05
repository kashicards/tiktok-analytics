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

HOOK_TYPE_OPTIONS    = ["—", "Kontrovers", "Zahl", "Mechanismus", "Vergleich", "Regel", "Beweis"]
CATEGORIES_AVAILABLE = ["Color", "Typography", "Layout", "Psychology", "Packaging", "Components", "Performance", "Other"]
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
        'September': 9, 'Oktober': 10, 'November': 11, 'Dezember': 12
    }
    now = datetime.now()
    months = []
    for val in series.dropna():
        parts = str(val).strip().replace('.', '').split()
        if len(parts) >= 2:
            m = month_map.get(parts[1])
            if m: months.append(m)
    spans_year_boundary = (1 in months and 12 in months)

    def parse_one(date_str):
        if pd.isna(date_str) or str(date_str).strip() in ('undefined', ''):
            return pd.NaT
        parts = str(date_str).strip().replace('.', '').split()
        if len(parts) < 2: return pd.NaT
        try:
            day   = int(parts[0])
            month = month_map.get(parts[1], 1)
            year  = now.year
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
    """
    Fixed priority order. Key changes vs old version:
    - 'emphasis', 'visual weight', 'hierarchy', 'focal', 'signal' removed from Psychology
      → moved to Typography / Layout where they belong semantically
    - Psychology only covers actual cognitive/behavioral concepts
    - 'bold', 'italic', 'emphasis', 'legib', 'readab' → Typography
    - 'visual weight', 'hierarchy', 'focal', 'asymmetric', 'balance' → Layout
    """
    if pd.isna(title): return 'Other'
    t = str(title).lower()
    keyword_map = {
        'Packaging':   ['packaging', 'bleed', 'dieline', 'print file', 'shelf',
                        'regal', 'mockup', 'print design', 'label', 'barcode'],
        'Color':       ['color', 'colour', 'hue', 'palette', 'hsl', 'contrast',
                        'luminan', 'lightness', 'oklch', 'cielab', 'saturati',
                        'colorblind', 'colour blind', 'color blind',
                        'simultaneous', 'cmyk', 'rgb', 'icc', 'wcag'],
        'Typography':  ['typography', 'font', 'typeface', 'line height', 'kerning',
                        'tracking', 'baseline', 'serif', 'sans', 'bold', 'italic',
                        'emphasis', 'legib', 'readab', 'type scale', 'text weight',
                        'letter spacing', 'x-height'],
        'Layout':      ['grid', 'layout', 'spacing', 'whitespace', 'white space',
                        'optical', 'centering', 'center', 'alignment', 'align',
                        'margin', 'padding', 'composition', 'visual weight',
                        'hierarchy', 'focal', 'asymmetric', 'balance', 'proportion',
                        'golden ratio', 'rule of thirds', 'negative space',
                        'signal', 'visual scanning', 'scanning'],
        'Psychology':  ['subitiz', 'von restorff', 'restorff', 'decoy', 'anchoring',
                        'priming', 'scarcity', 'social proof', 'reciprocity',
                        'loss aversion', 'framing', 'nudge', 'mental model',
                        'heuristic', 'choice architecture', 'paradox of choice',
                        'inattentional', 'blindness', 'pre-selection',
                        'cognitive load', 'cognitive bias', 'cognitive',
                        'perception', 'gestalt', 'fitts', "fitts'",
                        'hick', 'jakob', 'miller', 'psychology', 'psycholog',
                        'bias', ' law', 'attention span'],
        'Components':  ['card', 'radius', 'icon', 'modal', 'tooltip', 'button',
                        'input', 'form', 'navigation', 'tabs', 'menu', 'breadcrumb'],
        'Performance': ['loading', 'skeleton', 'progress', 'performance'],
    }
    for category, words in keyword_map.items():
        if any(word in t for word in words):
            return category
    return 'Other'


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
        cutoff_24h   = datetime.now() - timedelta(hours=24)
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
        filtered = base.sort_values('Posted Date', ascending=False).head(4)
        hint = "<strong>Letzte 4 Videos (>24h)</strong>"
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
    """Last 4 videos vs. the 4 before that — independent of period filter."""
    cutoff_24h = datetime.now() - timedelta(hours=24)
    valid = content_df[
        content_df['Posted Date'].notna() &
        (content_df['Posted Date'] <= cutoff_24h)
    ].sort_values('Posted Date', ascending=False)
    if len(valid) < 5:
        return None
    this_4 = valid.head(4)
    prev_4 = valid.iloc[4:8]
    if len(prev_4) == 0:
        return None
    return {
        'this': {'views': this_4['Video Views'].mean(),
                 'share': this_4['Share Rate'].mean(),
                 'eng':   this_4['Engagement Rate'].mean()},
        'prev': {'views': prev_4['Video Views'].mean(),
                 'share': prev_4['Share Rate'].mean(),
                 'eng':   prev_4['Engagement Rate'].mean()},
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

def build_callout(filtered_df, viewers_df, followers_df, activity_df, now, hook_types):
    today     = now.strftime("%d.%m.%Y")
    avg_share = filtered_df['Share Rate'].mean()
    avg_eng   = filtered_df['Engagement Rate'].mean()
    share_status = "✅" if avg_share >= 0.3 else "⚠️"
    eng_status   = "✅" if avg_eng   >= 4.0 else "⚠️"

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

    # Video rows sorted oldest → newest (chronological like the callout format)
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
        table_rows.append(f"> | {title}{hook_tag} | {cat} | {wd} —:— | | {views:,} | |")

    table = "\n".join(table_rows)
    top_title  = str(top['Video Title'])[:60]
    flop_title = str(flop['Video Title'])[:60]

    return (
        f"> [!tiktok]+ {today}\n"
        f">\n"
        f"> | Metrik | Wert | Status |\n"
        f"> | --- | --- | --- |\n"
        f"> | Share Rate | {avg_share:.2f}% | {share_status} |\n"
        f"> | Engagement | {avg_eng:.1f}% | {eng_status} |\n"
        f"> | Returning Viewers | {ret_str} | {ret_status} |\n"
        f"> | Neue Follower | {fol_str} | |\n"
        f"> | Optimale Postzeit | {post_time_str} | |\n"
        f">\n"
        f"> 🏆 **Top:** \"{top_title}…\"\n"
        f"> ↳ _\n"
        f"> 📉 **Flop:** \"{flop_title}…\"\n"
        f"> ↳ _\n"
        f">\n"
        f"> 📊 **Video-Details:**\n"
        f">\n"
        f"> | Video | Thema | Uhrzeit | FYP | Views | Retention |\n"
        f"> | --- | --- | --- | --- | --- | --- |\n"
        f"{table}\n"
        f">\n"
        f"> ↳ _Noch steigende Videos nächste Woche nachtragen_\n"
        f">\n"
        f"> 🧪 **Letzter Test:** \n"
        f"> 🔬 **Nächste Woche:** \n"
        f"> 🔗 **Muster:** _"
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
    overview_df  = pd.read_csv(overview_path)  if overview_path.exists()  else None
    viewers_df   = pd.read_csv(viewers_path)   if viewers_path.exists()   else None
    followers_df = pd.read_csv(followers_path) if followers_path.exists() else None
    activity_df  = pd.read_csv(activity_path)  if activity_path.exists()  else None

    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    content_df['Posted Date'] = pd.to_datetime(content_df['Posted Date'], errors='coerce')
    if overview_df  is not None:
        overview_df['Date']  = pd.to_datetime(overview_df['Date'],  errors='coerce')
        overview_df = overview_df[overview_df['Date'] <= now]
    if followers_df is not None:
        followers_df['Date'] = pd.to_datetime(followers_df['Date'], errors='coerce')
        followers_df = followers_df[followers_df['Date'] <= now]
    if viewers_df   is not None:
        viewers_df['Date']   = pd.to_datetime(viewers_df['Date'],   errors='coerce')

    # Apply persistent overrides
    overrides  = load_cat_overrides()
    content_df = apply_cat_overrides(content_df, overrides)
    hook_types = load_hook_types()

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
        st.subheader("↕️ Letzte 4 Videos vs. 4 davor")
        c1, c2, c3 = st.columns(3)

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
    st.divider()

    # ── INSIGHTS ──────────────────────────────────────────────────────────────
    st.subheader("🔍 Diese Woche")
    insights = generate_insights(filtered_df, viewers_df, followers_df, period, now)
    st.markdown("<div class='insight-box'>" + "<br>".join(insights) + "</div>", unsafe_allow_html=True)
    st.divider()

    # ── METRICS ───────────────────────────────────────────────────────────────
    st.subheader("🎯 Performance")
    col_m1, col_m2 = st.columns(2)

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

    st.divider()

    # ── OVERVIEW ──────────────────────────────────────────────────────────────
    st.subheader("📊 Overview")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        label = "Total Views (4 Videos)" if period == 'Last 7 Days' else "Total Views"
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
    st.subheader("📈 Share Rate Trend (alle Videos chronologisch)")
    cutoff_trend = datetime.now() - timedelta(hours=24)
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
            mode='lines', name='Ø 4 Videos',
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
        cutoff_24h_day = datetime.now() - timedelta(hours=24)
        all_valid = content_df[
            content_df['Posted Date'].notna() &
            (content_df['Posted Date'] <= cutoff_24h_day)
        ].copy()
        if all_valid['Posted Date'].notna().sum() > 3:
            all_valid['Weekday'] = all_valid['Posted Date'].dt.dayofweek.map(
                {0:'Mo', 1:'Di', 2:'Mi', 3:'Do', 4:'Fr', 5:'Sa', 6:'So'}
            )
            day_stats = (all_valid.groupby('Weekday')['Video Views'].mean()
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
        if activity_df is not None and 'Hour' in activity_df.columns:
            hourly    = activity_df.groupby('Hour')['Active'].mean().reset_index()
            hourly.columns = ['Hour', 'Avg Active']
            peak_hour = int(hourly.loc[hourly['Avg Active'].idxmax(), 'Hour'])
            post_hour = (peak_hour - 1) % 24
            post_str  = f"{post_hour}:30"
            st.caption(f"📌 Follower-Peak: **{peak_hour}:00** → optimaler Post: **{post_str}** (30 Min. vor Peak)")
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
        'Last 7 Days':   '🏆 Analysierte Videos (letzte 4, >24h)',
        'Last 30 Days':  '🏆 Top Videos — letzte 30 Tage',
        'Last 3 Months': '🏆 Top Videos — letztes Quartal',
        'All Time':      '🏆 Top Videos — All Time',
    }.get(period, '🏆 Top Videos')
    st.subheader(top_label)

    top_n = filtered_df.sort_values('Video Views', ascending=False).head(
        4 if period == 'Last 7 Days' else 5
    )[['Video Title', 'Posted Date', 'Video Views', 'Share Rate', 'Engagement Rate', 'Category']].copy()
    top_n['Posted Date']     = top_n['Posted Date'].apply(lambda d: fmt_date(d, 'weekday'))
    top_n['Video Views']     = top_n['Video Views'].apply(lambda x: f"{int(x):,}")
    top_n['Share Rate']      = top_n['Share Rate'].apply(lambda x: f"{x:.2f}%")
    top_n['Engagement Rate'] = top_n['Engagement Rate'].apply(lambda x: f"{x:.1f}%")
    top_n['Video Title']     = top_n['Video Title'].str[:60] + '…'
    st.dataframe(top_n, use_container_width=True, hide_index=True)

    # ── HOOK-TYP EDITOR ───────────────────────────────────────────────────────
    with st.expander("🏷️ Hook-Typ taggen", expanded=False):
        st.caption("Tags werden lokal gespeichert und erscheinen im Callout und in der Hook-Analyse.")
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
    if 'Video Link' in content_df.columns:
        ct = content_df.copy()
        ct['Hook Type'] = ct['Video Link'].map(hook_types).fillna('—')
        tagged = ct[ct['Hook Type'].isin(HOOK_TYPE_OPTIONS[1:])]  # exclude "—"
        if len(tagged) >= 3:
            st.subheader("🏷️ Hook-Typ Performance")
            hook_stats = (tagged.groupby('Hook Type')
                                .agg(Avg_Views=('Video Views', 'mean'),
                                     Avg_Share=('Share Rate',  'mean'),
                                     Count=('Video Title',    'count'))
                                .round(2).reset_index()
                                .sort_values('Avg_Views', ascending=False))
            ch1, ch2 = st.columns(2)
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
    if period != 'Last 7 Days':
        st.info("💡 Wechsle zu **Last 7 Days** für den Wochenrückblick-Callout.")
    else:
        callout = build_callout(filtered_df, viewers_df, followers_df, activity_df, now, hook_types)
        st.caption("Uhrzeit (z.B. 'Mo 17:34'), FYP% und Retention manuell ergänzen. "
                   "Top/Flop-Notiz und Muster-Zeile manuell befüllen.")
        st.code(callout, language=None)


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
            'Post time':    'Posted Date',
        })
        for col in ['Video Views', 'Likes', 'Comments', 'Shares']:
            df[col] = clean_numeric(df[col])
        df = df.sort_values('Video Views', ascending=False)
        df = df.drop_duplicates(subset=['Video Link'], keep='first')
        df['Posted Date']     = smart_parse_dates(df['Posted Date'])
        df['Share Rate']      = (df['Shares'] / df['Video Views'].replace(0, 1) * 100).clip(0, 100)
        df['Engagement Rate'] = ((df['Likes'] + df['Comments'] + df['Shares']) /
                                  df['Video Views'].replace(0, 1) * 100).clip(0, 100)
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