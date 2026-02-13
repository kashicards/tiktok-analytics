import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import zipfile
import os
from pathlib import Path

# === CONFIGURATION ===
st.set_page_config(
    page_title="DesignParser Analytics",
    page_icon="📊",
    layout="wide"
)

# Custom CSS for colored metrics
st.markdown("""
<style>
.metric-critical { color: #FF3B30; font-size: 2.5rem; font-weight: bold; }
.metric-warning { color: #FF9500; font-size: 2.5rem; font-weight: bold; }
.metric-good { color: #34C759; font-size: 2.5rem; font-weight: bold; }
.metric-excellent { color: #00C7BE; font-size: 2.5rem; font-weight: bold; }
.metric-label { color: #8E8E93; font-size: 0.9rem; margin-top: -10px; }
.action-critical { background: #FF3B301A; padding: 12px; border-radius: 8px; border-left: 4px solid #FF3B30; margin: 8px 0; }
.action-warning { background: #FF95001A; padding: 12px; border-radius: 8px; border-left: 4px solid #FF9500; margin: 8px 0; }
.action-good { background: #34C7591A; padding: 12px; border-radius: 8px; border-left: 4px solid #34C759; margin: 8px 0; }
</style>
""", unsafe_allow_html=True)

# Paths
BASE_DIR = Path.home() / "tiktok-analytics"
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# 2026 Benchmarks
BENCHMARKS = {
    'completion_rate': {'viral': 70.0, 'educational': 67.0, 'good': 60.0, 'critical': 40.0},
    'save_rate': {'exceptional': 1.0, 'good': 0.5, 'low': 0.2},
    'share_rate': {'exceptional': 0.5, 'good': 0.3, 'low': 0.1},
    'engagement_rate': {'excellent': 10.0, 'good': 6.0, 'low': 3.0}
}

# === HELPER FUNCTIONS ===

def extract_csvs_from_zip(zip_file):
    """Extract CSVs from ZIP"""
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
                            
                            if 'content' in filename:
                                extracted['content'] = df
                            elif 'overview' in filename:
                                extracted['overview'] = df
                            elif 'viewer' in filename:
                                extracted['viewers'] = df
                            elif 'followerhistory' in filename:
                                extracted['followers'] = df
                        except:
                            continue
    except:
        pass
    
    return extracted

def clean_numeric(series):
    """Clean numeric column"""
    return pd.to_numeric(series.replace('undefined', pd.NA), errors='coerce').fillna(0)

def parse_german_date(date_str):
    """Parse German date"""
    if pd.isna(date_str) or str(date_str) == 'undefined' or str(date_str).strip() == '':
        return pd.NaT
    
    month_map = {
        'Januar': 1, 'Februar': 2, 'März': 3, 'April': 4,
        'Mai': 5, 'Juni': 6, 'Juli': 7, 'August': 8,
        'September': 9, 'Oktober': 10, 'November': 11, 'Dezember': 12
    }
    
    try:
        parts = str(date_str).strip().replace('.', '').split()
        if len(parts) >= 2:
            day = int(parts[0])
            month = month_map.get(parts[1], 1)
            year = datetime.now().year
            parsed = datetime(year, month, day)
            if parsed > datetime.now():
                parsed = datetime(year - 1, month, day)
            return parsed
    except:
        pass
    
    return pd.NaT

def categorize_topic(title):
    """Categorize video by title"""
    if pd.isna(title):
        return 'Other'
    
    title_lower = str(title).lower()
    
    keywords = {
        'Color': ['color', 'colour', 'hue', 'palette'],
        'Typography': ['typography', 'font', 'typeface', 'line height', 'weight'],
        'Layout': ['grid', 'layout', 'pattern', 'list'],
        'UX Laws': ['law', 'jakob', 'fitts', 'bias'],
        'Navigation': ['navigation', 'tabs', 'button'],
        'Performance': ['loading', 'skeleton', 'progress'],
        'Components': ['card', 'radius', 'icon']
    }
    
    for category, words in keywords.items():
        if any(word in title_lower for word in words):
            return category
    
    return 'Other'

def get_metric_color_status(value, metric_type):
    """Get color class and status"""
    if metric_type == 'completion_rate':
        if value >= 70: return 'metric-excellent', 'VIRAL THRESHOLD'
        elif value >= 67: return 'metric-good', 'EDUCATIONAL TARGET'
        elif value >= 60: return 'metric-warning', 'NEEDS WORK'
        else: return 'metric-critical', 'CRITICAL'
    
    elif metric_type == 'save_rate':
        if value >= 1.0: return 'metric-excellent', 'EXCEPTIONAL'
        elif value >= 0.5: return 'metric-good', 'VERY GOOD'
        elif value >= 0.2: return 'metric-warning', 'LOW'
        else: return 'metric-critical', 'CRITICAL'
    
    elif metric_type == 'share_rate':
        if value >= 0.5: return 'metric-excellent', 'EXCEPTIONAL'
        elif value >= 0.3: return 'metric-good', 'VERY GOOD'
        elif value >= 0.1: return 'metric-warning', 'LOW'
        else: return 'metric-critical', 'CRITICAL'
    
    elif metric_type == 'engagement_rate':
        if value >= 10: return 'metric-excellent', 'EXCELLENT'
        elif value >= 6: return 'metric-good', 'GOOD'
        elif value >= 3: return 'metric-warning', 'LOW'
        else: return 'metric-critical', 'CRITICAL'
    
    return 'metric-warning', 'UNKNOWN'

def get_actions(metric_type, status):
    """Get concrete actions"""
    actions = {
        'completion_rate': {
            'CRITICAL': [
                '🔴 Hook komplett neu gestalten - erste 3 Sekunden entscheiden alles',
                '🔴 Video auf 12-15 Sekunden kürzen (sweet spot: 76.4% completion)',
                '🔴 Pattern Interrupt bei 5-7s: Farbe/Zoom/Sound ändern'
            ],
            'NEEDS WORK': [
                '🟡 Pacing beschleunigen - jede Sekunde muss Wert liefern',
                '🟡 Ende stärker - letzter Frame = stärkste Aussage',
                '🟡 Rewatch-Trigger: Text nur 1.5s on-screen'
            ],
            'EDUCATIONAL TARGET': [
                '✅ Educational Benchmark erreicht (67%)',
                '✅ Push zu 70%: Hook micro-optimieren'
            ],
            'VIRAL THRESHOLD': [
                '🟢 VIRAL THRESHOLD! Hook-Struktur replizieren'
            ]
        },
        'save_rate': {
            'CRITICAL': [
                '🔴 "Save this 💾" explizit bei Sekunde 12-13',
                '🔴 Konkrete Zahlen statt vage Tips',
                '🔴 Framework-Graphics die man später braucht'
            ],
            'LOW': [
                '🟡 CTAs: "Screenshot this"',
                '🟡 Mehr Spezifität: Zahlen + Regeln'
            ],
            'VERY GOOD': [
                '✅ Solid Save Rate (0.5-1%)',
                '✅ Push zu 1%+: A/B test CTAs'
            ],
            'EXCEPTIONAL': [
                '🟢 EXCEPTIONAL! Replizieren!'
            ]
        },
        'share_rate': {
            'CRITICAL': [
                '🔴 "Send to designer friend" CTA',
                '🔴 Surprising Facts: "93% do this wrong"',
                '🔴 Share-würdig: Frameworks'
            ],
            'LOW': [
                '🟡 Verschiedene CTAs testen',
                '🟡 Überraschende Daten einbauen'
            ],
            'VERY GOOD': [
                '✅ Good Share Rate'
            ],
            'EXCEPTIONAL': [
                '🟢 EXCEPTIONAL!'
            ]
        },
        'engagement_rate': {
            'CRITICAL': [
                '🔴 Clear CTAs in Video',
                '🔴 Frage in Caption'
            ],
            'LOW': [
                '🟡 Stärkere Caption'
            ],
            'GOOD': [
                '✅ Solid Engagement'
            ],
            'EXCELLENT': [
                '🟢 EXCELLENT!'
            ]
        }
    }
    
    return actions.get(metric_type, {}).get(status, [])

# === MAIN APP ===

def main():
    st.title("📊 DesignParser TikTok Analytics 2026")
    st.caption("Educational Content Benchmarks")
    
    # === SIDEBAR ===
    st.sidebar.header("📂 Upload Data")
    
    uploaded_files = st.sidebar.file_uploader(
        "TikTok ZIP files",
        type=['zip'],
        accept_multiple_files=True
    )
    
    if uploaded_files:
        st.sidebar.success(f"✅ {len(uploaded_files)} files")
        
        if st.sidebar.button("🔄 Process Data"):
            with st.spinner("Processing..."):
                # Collect all data
                all_content = []
                all_overview = []
                all_viewers = []
                all_followers = []
                
                for uploaded_file in uploaded_files:
                    extracted = extract_csvs_from_zip(uploaded_file)
                    
                    if 'content' in extracted:
                        all_content.append(extracted['content'])
                    if 'overview' in extracted:
                        all_overview.append(extracted['overview'])
                    if 'viewers' in extracted:
                        all_viewers.append(extracted['viewers'])
                    if 'followers' in extracted:
                        all_followers.append(extracted['followers'])
                
                # Process Content
                if all_content:
                    df = pd.concat(all_content, ignore_index=True)
                    
                    # Rename
                    df = df.rename(columns={
                        'Video title': 'Video Title',
                        'Video link': 'Video Link',
                        'Total views': 'Video Views',
                        'Total likes': 'Likes',
                        'Total comments': 'Comments',
                        'Total shares': 'Shares',
                        'Post time': 'Posted Date'
                    })
                    
                    # Clean numeric
                    for col in ['Video Views', 'Likes', 'Comments', 'Shares']:
                        df[col] = clean_numeric(df[col])
                    
                    # CRITICAL: Deduplicate by Video Link (keep highest views)
                    df = df.sort_values('Video Views', ascending=False)
                    df = df.drop_duplicates(subset=['Video Link'], keep='first')
                    
                    st.sidebar.success(f"✅ {len(df)} unique videos")
                    
                    # Parse dates
                    df['Posted Date'] = df['Posted Date'].apply(parse_german_date)
                    
                    # Calculate metrics
                    df['Completion Rate'] = ((df['Likes'] + df['Comments'] * 2 + df['Shares'] * 3) / 
                                             df['Video Views'].replace(0, 1) * 100).clip(0, 100)
                    
                    # Estimate Saves
                    df['Saves'] = df['Shares'] * 2.5
                    df['Save Rate'] = (df['Saves'] / df['Video Views'].replace(0, 1) * 100).clip(0, 100)
                    df['Share Rate'] = (df['Shares'] / df['Video Views'].replace(0, 1) * 100).clip(0, 100)
                    df['Engagement Rate'] = ((df['Likes'] + df['Comments'] + df['Shares'] + df['Saves']) / 
                                            df['Video Views'].replace(0, 1) * 100).clip(0, 100)
                    
                    # Categorize
                    df['Category'] = df['Video Title'].apply(categorize_topic)
                    
                    # Save
                    df.to_csv(DATA_DIR / 'content.csv', index=False)
                
                # Process Overview
                if all_overview:
                    df = pd.concat(all_overview, ignore_index=True)
                    df = df.rename(columns={
                        'Date': 'Date',
                        'Video Views': 'Views',
                        'Profile Views': 'Profile Views'
                    })
                    
                    df['Date'] = df['Date'].apply(parse_german_date)
                    
                    for col in ['Views', 'Profile Views', 'Likes', 'Comments', 'Shares']:
                        if col in df.columns:
                            df[col] = clean_numeric(df[col])
                    
                    df = df[df['Views'] > 0].dropna(subset=['Date'])
                    df = df.drop_duplicates(subset=['Date'], keep='last')
                    df.to_csv(DATA_DIR / 'overview.csv', index=False)
                    st.sidebar.success(f"✅ Overview: {len(df)} days")
                
                # Process Viewers
                if all_viewers:
                    df = pd.concat(all_viewers, ignore_index=True)
                    df = df.rename(columns={
                        'Date': 'Date',
                        'Total Viewers': 'Total',
                        'New Viewers': 'New',
                        'Returning Viewers': 'Returning'
                    })
                    
                    df['Date'] = df['Date'].apply(parse_german_date)
                    
                    for col in ['Total', 'New', 'Returning']:
                        if col in df.columns:
                            df[col] = clean_numeric(df[col])
                    
                    df = df[df['Total'] > 0].dropna(subset=['Date'])
                    df = df.drop_duplicates(subset=['Date'], keep='last')
                    df.to_csv(DATA_DIR / 'viewers.csv', index=False)
                    st.sidebar.success(f"✅ Viewers: {len(df)} days")
                
                # Process Followers
                if all_followers:
                    df = pd.concat(all_followers, ignore_index=True)
                    df = df.rename(columns={
                        'Date': 'Date',
                        'Followers': 'Followers',
                        'Difference in followers from previous day': 'Daily Growth'
                    })
                    
                    df['Date'] = df['Date'].apply(parse_german_date)
                    
                    for col in ['Followers', 'Daily Growth']:
                        if col in df.columns:
                            df[col] = clean_numeric(df[col])
                    
                    df = df[df['Followers'] > 0].dropna(subset=['Date'])
                    df = df.drop_duplicates(subset=['Date'], keep='last')
                    df.to_csv(DATA_DIR / 'followers.csv', index=False)
                    st.sidebar.success(f"✅ Followers: {len(df)} days")
                
                st.sidebar.success("🎉 Done!")
                st.rerun()
    
    # === LOAD DATA ===
    content_path = DATA_DIR / 'content.csv'
    overview_path = DATA_DIR / 'overview.csv'
    viewers_path = DATA_DIR / 'viewers.csv'
    followers_path = DATA_DIR / 'followers.csv'
    
    if not content_path.exists():
        st.info("👆 Upload TikTok exports to start")
        return
    
    content_df = pd.read_csv(content_path)
    overview_df = pd.read_csv(overview_path) if overview_path.exists() else None
    viewers_df = pd.read_csv(viewers_path) if viewers_path.exists() else None
    followers_df = pd.read_csv(followers_path) if followers_path.exists() else None
    
    # Parse dates
    content_df['Posted Date'] = pd.to_datetime(content_df['Posted Date'], errors='coerce')
    if overview_df is not None:
        overview_df['Date'] = pd.to_datetime(overview_df['Date'], errors='coerce')
    if followers_df is not None:
        followers_df['Date'] = pd.to_datetime(followers_df['Date'], errors='coerce')
    
    st.sidebar.divider()
    st.sidebar.write(f"✅ Videos: {len(content_df)}")
    if overview_df is not None:
        st.sidebar.write(f"✅ Daily: {len(overview_df)} days")
    if followers_df is not None:
        st.sidebar.write(f"✅ Followers: {len(followers_df)} days")
    
    # === PERIOD FILTER ===
    period = st.radio("📅 Period", ['All Time', 'Last 30 Days', 'Last 7 Days'], horizontal=True)
    
    filtered_df = content_df.copy()
    if period == 'Last 7 Days':
        cutoff = datetime.now() - timedelta(days=7)
        filtered_df = filtered_df[filtered_df['Posted Date'] >= cutoff]
    elif period == 'Last 30 Days':
        cutoff = datetime.now() - timedelta(days=30)
        filtered_df = filtered_df[filtered_df['Posted Date'] >= cutoff]
    
    if len(filtered_df) == 0:
        st.warning(f"⚠️ No videos in {period}")
        return
    
    # === METRICS ===
    st.subheader("🎯 Performance Metrics")
    
    avg_completion = filtered_df['Completion Rate'].mean()
    avg_save = filtered_df['Save Rate'].mean()
    avg_share = filtered_df['Share Rate'].mean()
    avg_engagement = filtered_df['Engagement Rate'].mean()
    
    # Completion Rate
    color_class, status = get_metric_color_status(avg_completion, 'completion_rate')
    st.markdown(f'<div class="{color_class}">{avg_completion:.1f}%</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-label">Completion Rate • {status} • Target: 70%+</div>', unsafe_allow_html=True)
    
    for action in get_actions('completion_rate', status)[:3]:
        action_class = 'action-critical' if '🔴' in action else 'action-warning' if '🟡' in action else 'action-good'
        st.markdown(f'<div class="{action_class}">{action}</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # Save Rate
    color_class, status = get_metric_color_status(avg_save, 'save_rate')
    st.markdown(f'<div class="{color_class}">{avg_save:.2f}%</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-label">Save Rate (⚠️ ESTIMATED) • {status} • Target: 0.5-1%</div>', unsafe_allow_html=True)
    
    for action in get_actions('save_rate', status)[:3]:
        action_class = 'action-critical' if '🔴' in action else 'action-warning' if '🟡' in action else 'action-good'
        st.markdown(f'<div class="{action_class}">{action}</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # Share Rate
    color_class, status = get_metric_color_status(avg_share, 'share_rate')
    st.markdown(f'<div class="{color_class}">{avg_share:.2f}%</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-label">Share Rate • {status} • Target: 0.3-0.5%</div>', unsafe_allow_html=True)
    
    for action in get_actions('share_rate', status)[:3]:
        action_class = 'action-critical' if '🔴' in action else 'action-warning' if '🟡' in action else 'action-good'
        st.markdown(f'<div class="{action_class}">{action}</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # Engagement
    color_class, status = get_metric_color_status(avg_engagement, 'engagement_rate')
    st.markdown(f'<div class="{color_class}">{avg_engagement:.1f}%</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="metric-label">Engagement Rate • {status} • Target: 6-12%</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # === OVERVIEW STATS ===
    st.subheader("📊 Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_views = int(filtered_df['Video Views'].sum())
        st.metric("Total Views", f"{total_views:,}")
    
    with col2:
        if followers_df is not None and len(followers_df) > 0:
            followers_sorted = followers_df.sort_values('Date', ascending=False)
            current = int(followers_sorted.iloc[0]['Followers'])
            growth = int(followers_df['Daily Growth'].sum())
            st.metric("Followers", f"{current:,}", f"+{growth}")
        else:
            st.metric("Followers", "—")
    
    with col3:
        if overview_df is not None and len(overview_df) > 0:
            avg_daily = int(overview_df['Views'].mean())
            st.metric("Avg Daily Views", f"{avg_daily:,}")
        else:
            st.metric("Videos", len(filtered_df))
    
    with col4:
        if viewers_df is not None and len(viewers_df) > 0:
            retention = (viewers_df['Returning'].sum() / viewers_df['Total'].sum() * 100)
            st.metric("Viewer Retention", f"{retention:.1f}%")
        else:
            avg_views = int(filtered_df['Video Views'].mean())
            st.metric("Avg Video Views", f"{avg_views:,}")
    
    # === CHARTS ===
    if overview_df is not None and len(overview_df) > 0:
        st.subheader("📈 Daily Performance")
        
        overview_sorted = overview_df.sort_values('Date')
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=overview_sorted['Date'],
            y=overview_sorted['Views'],
            mode='lines+markers',
            line=dict(color='#007AFF', width=3)
        ))
        
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
    
    if followers_df is not None and len(followers_df) > 0:
        st.subheader("👥 Follower Growth")
        
        col1, col2 = st.columns(2)
        
        followers_sorted = followers_df.sort_values('Date')
        
        with col1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=followers_sorted['Date'],
                y=followers_sorted['Followers'],
                mode='lines+markers',
                fill='tozeroy',
                line=dict(color='#34C759', width=2)
            ))
            fig.update_layout(height=250, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=followers_sorted['Date'],
                y=followers_sorted['Daily Growth'],
                marker_color='#34C759'
            ))
            fig.update_layout(height=250, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)
    
    # === TOP VIDEOS ===
    st.subheader("🏆 Top 5 Videos")
    
    top_5 = filtered_df.nlargest(5, 'Video Views')[
        ['Video Title', 'Video Views', 'Completion Rate', 'Share Rate', 'Category']
    ].copy()
    
    top_5['Video Views'] = top_5['Video Views'].apply(lambda x: f"{int(x):,}")
    top_5['Completion Rate'] = top_5['Completion Rate'].apply(lambda x: f"{x:.1f}%")
    top_5['Share Rate'] = top_5['Share Rate'].apply(lambda x: f"{x:.2f}%")
    top_5['Video Title'] = top_5['Video Title'].str[:60] + '...'
    
    st.dataframe(top_5, use_container_width=True, hide_index=True)
    
    # === CATEGORY PERFORMANCE ===
    st.subheader("📁 Category Performance")
    
    cat_stats = filtered_df.groupby('Category').agg({
        'Video Views': 'mean',
        'Completion Rate': 'mean',
        'Video Title': 'count'
    }).round(1).reset_index()
    cat_stats.columns = ['Category', 'Avg Views', 'Avg Completion %', 'Count']
    cat_stats = cat_stats.sort_values('Avg Views', ascending=False)
    
    fig = px.bar(
        cat_stats,
        x='Category',
        y='Avg Views',
        color='Avg Completion %',
        color_continuous_scale=['red', 'yellow', 'green'],
        text='Avg Views'
    )
    fig.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    fig.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()