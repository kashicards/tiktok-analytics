import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import zipfile
import os
from pathlib import Path

st.set_page_config(page_title="DesignParser Analytics", page_icon="📊", layout="wide")

st.markdown("""
<style>
.metric-critical  { color: #FF3B30; font-size: 2.5rem; font-weight: bold; }
.metric-warning   { color: #FF9500; font-size: 2.5rem; font-weight: bold; }
.metric-good      { color: #34C759; font-size: 2.5rem; font-weight: bold; }
.metric-excellent { color: #00C7BE; font-size: 2.5rem; font-weight: bold; }
.metric-label     { color: #8E8E93; font-size: 0.9rem; margin-top: -10px; }
.action-critical  { background: #FF3B301A; padding: 12px; border-radius: 8px; border-left: 4px solid #FF3B30; margin: 8px 0; }
.action-warning   { background: #FF95001A; padding: 12px; border-radius: 8px; border-left: 4px solid #FF9500; margin: 8px 0; }
.action-good      { background: #34C7591A; padding: 12px; border-radius: 8px; border-left: 4px solid #34C759; margin: 8px 0; }
.insight-box      { background: #1C1C2E; padding: 16px; border-radius: 10px; border-left: 4px solid #007AFF; margin: 8px 0; line-height: 1.9; }
.upload-guide     { background: #1C1C2E; padding: 16px; border-radius: 10px; font-size: 0.88rem; line-height: 1.8; }
.upload-hero      { background: #1C1C2E; padding: 24px; border-radius: 12px; border: 1px solid #2C2C3E; margin-bottom: 24px; }
</style>
""", unsafe_allow_html=True)

BASE_DIR = Path.home() / "tiktok-analytics"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

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
Das Dashboard merged & dedupliziert automatisch.

💡 **Wo findest du Viewers?**
TikTok Studio → Analytics → Tab „Übersicht" → Scroll runter zu „Zuschauer" → Exportieren (365 Tage)
"""


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
                            if 'content'            in filename: extracted['content']           = df
                            elif 'overview'         in filename: extracted['overview']          = df
                            elif 'viewer'           in filename: extracted['viewers']           = df
                            elif 'followerhistory'  in filename: extracted['followers']         = df
                            elif 'followeractivity' in filename: extracted['follower_activity'] = df
                        except:
                            continue
    except:
        pass
    return extracted


def clean_numeric(series):
    return pd.to_numeric(series.replace('undefined', pd.NA), errors='coerce').fillna(0)


def fmt_date(dt, fmt='short'):
    """Windows-kompatibles Datumsformat — %-d funktioniert nur auf Linux/Mac."""
    if dt is None or pd.isna(dt): return '?'
    try:
        if fmt == 'short':   return f"{dt.day}. {dt.strftime('%b')}"
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
    if pd.isna(title): return 'Other'
    t = str(title).lower()
    # Reihenfolge wichtig — spezifischere Kategorien zuerst
    keywords = {
        'Packaging':   ['packaging', 'bleed', 'dieline', 'print file', 'cmyk', 'shelf',
                        'regal', 'mockup', 'print design', 'label', 'barcode'],
        'Color':       ['color', 'colour', 'hue', 'palette', 'hsl', 'contrast',
                        'luminan', 'lightness', 'oklch', 'cielab', 'saturati'],
        'Typography':  ['typography', 'font', 'typeface', 'line height', 'weight', 'scale',
                        'kerning', 'tracking', 'baseline', 'serif', 'sans'],
        'Layout':      ['grid', 'layout', 'spacing', 'whitespace', 'optical',
                        'centering', 'center', 'alignment', 'align',
                        'margin', 'padding', 'white space', 'composition'],
        'Psychology':  ['law', 'jakob', 'fitts', 'bias', 'hick', 'gestalt',
                        'attention', 'perception', 'cognitive', 'salienc', 'focal',
                        'emphasis', 'visual weight', 'hierarchy', 'inattentional',
                        'blindness', 'pre-selection', 'default', 'signal', 'consent'],
        'Components':  ['card', 'radius', 'icon', 'modal', 'tooltip', 'button',
                        'input', 'form', 'navigation', 'tabs', 'menu', 'breadcrumb'],
        'Performance': ['loading', 'skeleton', 'progress', 'performance'],
    }
    for category, words in keywords.items():
        if any(word in t for word in words): return category
    return 'Other'


def get_metric_color_status(value, metric_type):
    if metric_type == 'share_rate':
        if value >= 0.5: return 'metric-excellent', 'EXCEPTIONAL'
        elif value >= 0.3: return 'metric-good', 'VERY GOOD'
        elif value >= 0.1: return 'metric-warning', 'LOW'
        else: return 'metric-critical', 'CRITICAL'
    elif metric_type == 'engagement_rate':
        if value >= 6.0: return 'metric-excellent', 'EXCELLENT'
        elif value >= 4.0: return 'metric-good', 'GOOD'
        elif value >= 2.0: return 'metric-warning', 'LOW'
        else: return 'metric-critical', 'CRITICAL'
    return 'metric-warning', 'UNKNOWN'


def get_actions(metric_type, status):
    actions = {
        'share_rate': {
            'CRITICAL':    ['🔴 "Send to a designer friend" CTA direkt ins Video',
                            '🔴 Surprising Fact: "93% machen das falsch"',
                            '🔴 Shareable Frameworks mit konkreten Zahlen'],
            'LOW':         ['🟡 Verschiedene CTA-Formulierungen testen',
                            '🟡 Kontraintuitive Aussage als Hook'],
            'VERY GOOD':   ['✅ Solid Share Rate — CTA-Struktur beibehalten'],
            'EXCEPTIONAL': ['🟢 EXCEPTIONAL! Diese Video-Struktur replizieren'],
        },
        'engagement_rate': {
            'CRITICAL':  ['🔴 Frage am Ende des Videos', '🔴 Caption mit Frage an Community'],
            'LOW':       ['🟡 Stärkere Caption mit Meinungsfrage', '🟡 Controversial Hook testen'],
            'GOOD':      ['✅ Solide Engagement Rate'],
            'EXCELLENT': ['🟢 EXCELLENT! Diesen Content-Typ skalieren'],
        },
    }
    return actions.get(metric_type, {}).get(status, [])


def get_follower_weekly(followers_df):
    """
    Berechnet Follower-Wachstum der letzten 7 Datentage.
    Referenz = letzter verfügbarer Tag im Export (nicht datetime.now),
    weil TikTok-Exporte immer 1–2 Tage hinter dem aktuellen Datum liegen.
    Gibt (weekly_growth, date_from, date_to) zurück.
    """
    if followers_df is None or len(followers_df) == 0:
        return 0, None, None
    fs = followers_df.sort_values('Date')
    max_date = fs['Date'].max()
    cutoff   = max_date - timedelta(days=7)
    window   = fs[fs['Date'] > cutoff]
    weekly   = int(window['Daily Growth'].sum())
    date_from = window['Date'].min() if len(window) > 0 else None
    date_to   = window['Date'].max() if len(window) > 0 else None
    return weekly, date_from, date_to


def get_avg_daily_views(overview_df, period_filter_start=None):
    """
    Berechnet Avg Daily Views.
    Filtert Zukunftsdaten (Views == 0 wegen noch nicht vergangener Tage) heraus.
    Berücksichtigt optionalen Period-Filter.
    """
    if overview_df is None or len(overview_df) == 0:
        return 0
    # Nur Tage mit echten Views (keine Zukunfts-Nullwerte)
    real = overview_df[overview_df['Views'] > 0].dropna(subset=['Date'])
    if period_filter_start is not None:
        real = real[real['Date'] >= period_filter_start]
    if len(real) == 0:
        return 0
    return int(real['Views'].mean())


def generate_insights(filtered_df, viewers_df, followers_df):
    insights = []
    if len(filtered_df) > 0:
        top = filtered_df.nlargest(1, 'Video Views').iloc[0]
        insights.append(
            f"🏆 <strong>Stärkstes Video:</strong> \"{str(top['Video Title'])[:55]}…\" — "
            f"<strong>{int(top['Video Views']):,} Views</strong>, {top['Share Rate']:.2f}% Share Rate"
        )
        if len(filtered_df) > 1:
            bot = filtered_df.nsmallest(1, 'Video Views').iloc[0]
            insights.append(
                f"📉 <strong>Schwächstes Video:</strong> \"{str(bot['Video Title'])[:55]}…\" — "
                f"<strong>{int(bot['Video Views']):,} Views</strong>, {bot['Share Rate']:.2f}% Share Rate"
            )

    avg_share = filtered_df['Share Rate'].mean()
    if avg_share >= 0.3:
        insights.append(f"✅ <strong>Share Rate {avg_share:.2f}%</strong> — über Ziel (0.3%).")
    else:
        insights.append(f"⚠️ <strong>Share Rate {avg_share:.2f}%</strong> — unter Ziel. Shareable Hooks & direkterer CTA.")

    avg_eng = filtered_df['Engagement Rate'].mean()
    if avg_eng >= 4.0:
        insights.append(f"✅ <strong>Engagement {avg_eng:.1f}%</strong> — Community reagiert aktiv.")
    else:
        insights.append(f"⚠️ <strong>Engagement {avg_eng:.1f}%</strong> — Caption-Fragen würden das pushen.")

    if viewers_df is not None and len(viewers_df) > 0:
        total = viewers_df['Total'].sum()
        ret   = viewers_df['Returning'].sum()
        ret_pct = ret / total * 100 if total > 0 else 0
        if ret_pct >= 40:
            insights.append(f"✅ <strong>{ret_pct:.0f}% Returning Viewers</strong> — Audience kommt zurück.")
        else:
            insights.append(f"⚠️ <strong>{ret_pct:.0f}% Returning Viewers</strong> — Serie-Formate helfen.")

    if len(filtered_df) >= 3:
        cat_avg = filtered_df.groupby('Category')['Video Views'].mean()
        if len(cat_avg) > 1:
            best  = cat_avg.idxmax()
            worst = cat_avg.idxmin()
            if best != worst:
                insights.append(
                    f"📊 <strong>Beste Kategorie: {best}</strong> ({int(cat_avg[best]):,} avg Views) · "
                    f"Schwächste: {worst} ({int(cat_avg[worst]):,})"
                )

    if followers_df is not None and len(followers_df) > 0:
        weekly, date_from, date_to = get_follower_weekly(followers_df)
        if weekly > 0:
            label = f" ({fmt_date(date_from, 'numeric')}–{fmt_date(date_to, 'numeric')})" if date_from and date_to else ""
            insights.append(f"👥 <strong>+{weekly:,} Follower</strong> in den letzten 7 Datentagen{label}.")

    return insights


def main():
    st.title("📊 DesignParser TikTok Analytics 2026")
    st.caption("Educational Content Benchmarks")

    content_path   = DATA_DIR / 'content.csv'
    overview_path  = DATA_DIR / 'overview.csv'
    viewers_path   = DATA_DIR / 'viewers.csv'
    followers_path = DATA_DIR / 'followers.csv'
    activity_path  = DATA_DIR / 'activity.csv'

    # ── UPLOAD GUIDE (erster Start) ───────────────────────────────────────────
    if not content_path.exists():
        st.markdown("## 👆 So startest du")
        st.markdown(
            "<div class='upload-hero'>" + UPLOAD_GUIDE_MD.replace("\n", "<br>") + "</div>",
            unsafe_allow_html=True
        )
        st.info("Lade die ZIPs in der Sidebar hoch und klicke auf **Process Data**.")
        st.sidebar.header("📂 Upload Data")
        uploaded_files = st.sidebar.file_uploader("TikTok ZIP files", type=['zip'], accept_multiple_files=True)
        if uploaded_files:
            st.sidebar.success(f"✅ {len(uploaded_files)} files")
            if st.sidebar.button("🔄 Process Data"):
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

    with st.sidebar.expander("📋 Welche ZIPs hochladen?", expanded=False):
        st.markdown(UPLOAD_GUIDE_MD)

    # ── Daten laden ───────────────────────────────────────────────────────────
    content_df   = pd.read_csv(content_path)
    overview_df  = pd.read_csv(overview_path)  if overview_path.exists()  else None
    viewers_df   = pd.read_csv(viewers_path)   if viewers_path.exists()   else None
    followers_df = pd.read_csv(followers_path) if followers_path.exists() else None
    activity_df  = pd.read_csv(activity_path)  if activity_path.exists()  else None

    # Auf Mitternacht normalisieren — sonst wird der Grenztag (z.B. 8. März)
    # ausgeschlossen weil seine gespeicherte Zeit 00:00:00 vor datetime.now() liegt
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Posted Date: String → datetime, timezone-naive, NaT bei Fehlern
    content_df['Posted Date'] = pd.to_datetime(content_df['Posted Date'], errors='coerce')
    content_df['Posted Date'] = content_df['Posted Date'].dt.tz_localize(None) \
        if hasattr(content_df['Posted Date'].dt, 'tz_localize') \
        and content_df['Posted Date'].dt.tz is not None else content_df['Posted Date']

    if overview_df is not None:
        overview_df['Date'] = pd.to_datetime(overview_df['Date'], errors='coerce')
        # Zukunftsdaten rausfiltern — TikTok schreibt Nullwerte für zukünftige Tage in den Export
        overview_df = overview_df[overview_df['Date'] <= now]

    if followers_df is not None:
        followers_df['Date'] = pd.to_datetime(followers_df['Date'], errors='coerce')
        followers_df = followers_df[followers_df['Date'] <= now]

    if viewers_df is not None:
        viewers_df['Date'] = pd.to_datetime(viewers_df['Date'], errors='coerce')

    # ── Sidebar Status ────────────────────────────────────────────────────────
    st.sidebar.divider()
    st.sidebar.write(f"✅ Videos: {len(content_df)}")
    if overview_df  is not None: st.sidebar.write(f"✅ Daily: {len(overview_df[overview_df['Views']>0])} Tage mit Daten")
    if viewers_df   is not None: st.sidebar.write(f"✅ Viewers: {len(viewers_df)} Tage")
    else:                        st.sidebar.write("⚠️ Viewers: nicht geladen")
    if followers_df is not None:
        max_fol = followers_df['Date'].max()
        st.sidebar.write(f"✅ Followers: Daten bis {fmt_date(max_fol, 'full')}")
    if activity_df  is not None: st.sidebar.write("✅ Activity: ✓")

    # ── Period Filter ─────────────────────────────────────────────────────────
    period = st.radio("📅 Period", ['All Time', 'Last 30 Days', 'Last 7 Days'], horizontal=True)
    filtered_df = content_df.copy()
    period_start = None
    if period == 'Last 7 Days':
        period_start = now - timedelta(days=7)
        filtered_df = filtered_df[filtered_df['Posted Date'] >= period_start]
    elif period == 'Last 30 Days':
        period_start = now - timedelta(days=30)
        filtered_df = filtered_df[filtered_df['Posted Date'] >= period_start]

    if len(filtered_df) == 0:
        st.warning(f"⚠️ Keine Videos im Zeitraum {period}")
        return

    # ── AUTO-INSIGHTS ─────────────────────────────────────────────────────────
    st.subheader("🔍 Diese Woche beachten")
    insights = generate_insights(filtered_df, viewers_df, followers_df)
    st.markdown("<div class='insight-box'>" + "<br>".join(insights) + "</div>", unsafe_allow_html=True)
    st.divider()

    # ── METRICS ───────────────────────────────────────────────────────────────
    st.subheader("🎯 Performance Metrics")
    avg_share = filtered_df['Share Rate'].mean()
    cc, status = get_metric_color_status(avg_share, 'share_rate')
    st.markdown(f'<div class="{cc}">{avg_share:.2f}%</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-label">Share Rate • {status} • Target: 0.3–0.5%</div>', unsafe_allow_html=True)
    for a in get_actions('share_rate', status)[:3]:
        ac = 'action-critical' if '🔴' in a else 'action-warning' if '🟡' in a else 'action-good'
        st.markdown(f'<div class="{ac}">{a}</div>', unsafe_allow_html=True)
    st.divider()

    avg_eng = filtered_df['Engagement Rate'].mean()
    cc, status = get_metric_color_status(avg_eng, 'engagement_rate')
    st.markdown(f'<div class="{cc}">{avg_eng:.1f}%</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-label">Engagement Rate (Likes+Comments+Shares/Views) • {status} • Target: 4–6%</div>', unsafe_allow_html=True)
    for a in get_actions('engagement_rate', status)[:2]:
        ac = 'action-critical' if '🔴' in a else 'action-warning' if '🟡' in a else 'action-good'
        st.markdown(f'<div class="{ac}">{a}</div>', unsafe_allow_html=True)
    st.divider()

    # ── OVERVIEW ──────────────────────────────────────────────────────────────
    st.subheader("📊 Overview")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Views", f"{int(filtered_df['Video Views'].sum()):,}")

    with col2:
        if followers_df is not None:
            weekly, date_from, date_to = get_follower_weekly(followers_df)
            fs_latest = followers_df.sort_values('Date').dropna(subset=['Date'])
            latest_followers = int(fs_latest.iloc[-1]['Followers']) if len(fs_latest) > 0 else 0
            # Datumsbereich als Delta-Label anzeigen
            if date_from and date_to:
                delta_label = f"+{weekly} ({fmt_date(date_from, 'numeric')}–{fmt_date(date_to, 'numeric')})"
            else:
                delta_label = f"+{weekly} (7d)"
            st.metric("Followers", f"{latest_followers:,}", delta_label)
        else:
            st.metric("Followers", "—")

    with col3:
        # Avg Daily Views: nur echte Tage (Views > 0), period-gefiltert
        avg_daily = get_avg_daily_views(overview_df, period_start)
        if avg_daily > 0:
            period_label = period.replace('Last ', '').replace(' Days', 'd') if period != 'All Time' else 'All Time'
            st.metric("Avg Daily Views", f"{avg_daily:,}", help=f"Nur Tage mit Views > 0 · {period_label}")
        else:
            st.metric("Videos", len(filtered_df))

    with col4:
        if viewers_df is not None:
            total_v = viewers_df['Total'].sum()
            ret_v   = viewers_df['Returning'].sum()
            ret_pct = ret_v / total_v * 100 if total_v > 0 else 0
            st.metric("Returning Viewers", f"{ret_pct:.1f}%",
                      "✅ Healthy" if ret_pct >= 40 else "⚠️ Low", help="Ziel: 40%+")
        else:
            st.metric("Avg Views/Video", f"{int(filtered_df['Video Views'].mean()):,}")

    # ── VIEWERS ───────────────────────────────────────────────────────────────
    if viewers_df is not None:
        st.subheader("👁️ New vs. Returning Viewers")
        total_new = viewers_df['New'].sum()
        total_ret = viewers_df['Returning'].sum()
        ret_pct   = total_ret / (total_new + total_ret) * 100 if (total_new + total_ret) > 0 else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("New Viewers",       f"{int(total_new):,}")
        c2.metric("Returning Viewers", f"{int(total_ret):,}")
        c3.metric("Retention Rate",    f"{ret_pct:.1f}%",
                  delta="✅ Healthy" if ret_pct >= 40 else "⚠️ Audience kommt nicht zurück")
        vdf = viewers_df.sort_values('Date')
        fig = go.Figure()
        fig.add_trace(go.Bar(x=vdf['Date'], y=vdf['New'],       name='New',       marker_color='#007AFF'))
        fig.add_trace(go.Bar(x=vdf['Date'], y=vdf['Returning'], name='Returning', marker_color='#34C759'))
        fig.update_layout(barmode='stack', height=250, margin=dict(l=0,r=0,t=10,b=0),
                          legend=dict(orientation='h', y=1.1))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("📌 **Viewers-Daten fehlen** — Lade das Viewers ZIP (365 Tage) hoch, um New vs. Returning zu sehen.")

    # ── DAILY VIEWS ───────────────────────────────────────────────────────────
    if overview_df is not None:
        st.subheader("📈 Daily Views")
        ov = overview_df[overview_df['Views'] > 0].sort_values('Date')
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ov['Date'], y=ov['Views'], mode='lines+markers',
                                 line=dict(color='#007AFF', width=3)))
        fig.update_layout(height=300, margin=dict(l=0,r=0,t=10,b=0))
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
            fig.update_layout(height=250, margin=dict(l=0,r=0,t=10,b=0))
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=fs['Date'], y=fs['Daily Growth'], marker_color='#34C759'))
            fig.update_layout(height=250, margin=dict(l=0,r=0,t=10,b=0))
            st.plotly_chart(fig, use_container_width=True)

    # ── BEST DAY + BEST TIME ──────────────────────────────────────────────────
    col_day, col_time = st.columns(2)

    with col_day:
        st.subheader("📅 Best Day to Post")
        if filtered_df['Posted Date'].notna().sum() > 3:
            day_map = {0:'Mo', 1:'Di', 2:'Mi', 3:'Do', 4:'Fr', 5:'Sa', 6:'So'}
            fd = filtered_df.copy()
            fd['Weekday'] = fd['Posted Date'].dt.dayofweek.map(day_map)
            day_stats = (fd.groupby('Weekday')['Video Views'].mean()
                           .reindex(['Mo','Di','Mi','Do','Fr','Sa','So'])
                           .fillna(0).reset_index())
            day_stats.columns = ['Day', 'Avg Views']
            fig = px.bar(day_stats, x='Day', y='Avg Views',
                         color='Avg Views', color_continuous_scale=['#1C1C1E','#007AFF'],
                         text='Avg Views')
            fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
            fig.update_layout(height=300, showlegend=False, margin=dict(l=0,r=0,t=10,b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nicht genug Videos für Wochentag-Auswertung.")

    with col_time:
        st.subheader("🕐 Best Time to Post")
        if activity_df is not None and 'Hour' in activity_df.columns:
            hourly = activity_df.groupby('Hour')['Active'].mean().reset_index()
            hourly.columns = ['Hour', 'Avg Active']
            peak_hour = int(hourly.loc[hourly['Avg Active'].idxmax(), 'Hour'])

            # 30 Minuten vor dem Peak — Video braucht Anlaufzeit bevor
            # Follower-Aktivität ihr Maximum erreicht (Quelle: TikTok Creator Guides)
            post_hour     = (peak_hour - 1) % 24  # volle Stunde davor
            post_time_str = f"{post_hour}:30"       # :30 = halbe Stunde vor dem Peak

            st.caption(
                f"📌 Follower-Peak: **{peak_hour}:00 Uhr** → "
                f"optimaler Post-Zeitpunkt: **{post_time_str} Uhr** "
                f"(30 Min. vor Peak)"
            )
            fig = px.bar(hourly, x='Hour', y='Avg Active',
                         color='Avg Active', color_continuous_scale=['#1C1C1E','#FF9500'])
            fig.add_vline(x=post_hour, line_dash='dash', line_color='#FF9500',
                          annotation_text=f"Poste hier (~{post_time_str})",
                          annotation_position="top right")
            fig.update_layout(height=300, showlegend=False, margin=dict(l=0,r=0,t=30,b=0),
                              xaxis=dict(tickmode='linear', dtick=2))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Lade das Followers-ZIP hoch — enthält FollowerActivity.csv mit Stunden-Daten.")

    # ── TOP 5 ─────────────────────────────────────────────────────────────────
    st.subheader("🏆 Top 5 Videos")
    top_5 = filtered_df.nlargest(5, 'Video Views')[
        ['Video Title', 'Video Views', 'Share Rate', 'Engagement Rate', 'Category']
    ].copy()
    top_5['Video Views']     = top_5['Video Views'].apply(lambda x: f"{int(x):,}")
    top_5['Share Rate']      = top_5['Share Rate'].apply(lambda x: f"{x:.2f}%")
    top_5['Engagement Rate'] = top_5['Engagement Rate'].apply(lambda x: f"{x:.1f}%")
    top_5['Video Title']     = top_5['Video Title'].str[:60] + '…'
    st.dataframe(top_5, use_container_width=True, hide_index=True)

    # ── CATEGORY ──────────────────────────────────────────────────────────────
    st.subheader("📁 Category Performance")
    cat_stats = (filtered_df.groupby('Category')
                             .agg(Avg_Views=('Video Views', 'mean'),
                                  Avg_Engagement=('Engagement Rate', 'mean'),
                                  Count=('Video Title', 'count'))
                             .round(1).reset_index()
                             .sort_values('Avg_Views', ascending=False))
    fig = px.bar(cat_stats, x='Category', y='Avg_Views',
                 color='Avg_Engagement', color_continuous_scale=['red','yellow','green'],
                 text='Avg_Views',
                 labels={'Avg_Views': 'Avg Views', 'Avg_Engagement': 'Avg Engagement %'})
    fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    fig.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def _process_uploads(uploaded_files):
    """Extracts and saves all ZIP data to DATA_DIR."""
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
            'Video title': 'Video Title', 'Video link': 'Video Link',
            'Total views': 'Video Views', 'Total likes': 'Likes',
            'Total comments': 'Comments', 'Total shares': 'Shares',
            'Post time': 'Posted Date',
        })
        for col in ['Video Views', 'Likes', 'Comments', 'Shares']:
            df[col] = clean_numeric(df[col])
        df = df.sort_values('Video Views', ascending=False)
        df = df.drop_duplicates(subset=['Video Link'], keep='first')
        st.sidebar.success(f"✅ {len(df)} unique videos")
        df['Posted Date']     = smart_parse_dates(df['Posted Date'])
        df['Share Rate']      = (df['Shares'] / df['Video Views'].replace(0, 1) * 100).clip(0, 100)
        df['Engagement Rate'] = ((df['Likes'] + df['Comments'] + df['Shares']) /
                                  df['Video Views'].replace(0, 1) * 100).clip(0, 100)
        df['Category']        = df['Video Title'].apply(categorize_topic)
        df.to_csv(DATA_DIR / 'content.csv', index=False)

    if all_overview:
        df = pd.concat(all_overview, ignore_index=True)
        df = df.rename(columns={'Video Views': 'Views'})
        df['Date'] = smart_parse_dates(df['Date'])
        for col in ['Views', 'Profile Views', 'Likes', 'Comments', 'Shares']:
            if col in df.columns: df[col] = clean_numeric(df[col])
        # Zukunftsdaten beim Speichern bereits rausfiltern
        df = df[df['Views'] > 0].dropna(subset=['Date'])
        df = df.drop_duplicates(subset=['Date'], keep='last')
        df.to_csv(DATA_DIR / 'overview.csv', index=False)
        st.sidebar.success(f"✅ Overview: {len(df)} Tage mit Daten")

    if all_viewers:
        df = pd.concat(all_viewers, ignore_index=True)
        df = df.rename(columns={'Total Viewers': 'Total', 'New Viewers': 'New', 'Returning Viewers': 'Returning'})
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
        st.sidebar.success(f"✅ Followers: Daten bis {fmt_date(df['Date'].max(), 'full')}")

    if all_activity:
        df = pd.concat(all_activity, ignore_index=True)
        df.columns = [c.strip() for c in df.columns]
        rename_map = {}
        for c in df.columns:
            cl = c.lower()
            if 'hour' in cl: rename_map[c] = 'Hour'
            elif 'active' in cl: rename_map[c] = 'Active'
        df = df.rename(columns=rename_map)
        if 'Hour' in df.columns and 'Active' in df.columns:
            df['Hour']   = clean_numeric(df['Hour']).astype(int)
            df['Active'] = clean_numeric(df['Active'])
            df = df[df['Active'] > 0]
            df.to_csv(DATA_DIR / 'activity.csv', index=False)
            st.sidebar.success("✅ Activity: ✓")

    st.sidebar.success("🎉 Fertig! Daten aktualisiert.")


if __name__ == "__main__":
    main()