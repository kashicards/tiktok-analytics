# TikTok Analytics Dashboard 2026

Advanced analytics dashboard for TikTok educational content with 2026 benchmarks.

## Features

- Multi-ZIP data processing (365-day + 7-day exports)
- Automatic deduplication
- Color-coded metrics (Completion Rate, Save Rate, Share Rate)
- Actionable insights based on 2026 TikTok algorithm
- Daily performance tracking
- Follower growth analytics

## Installation

1. Install dependencies:
```bash
pip install streamlit pandas plotly --break-system-packages
```

2. Run dashboard:
```bash
streamlit run dashboard.py
```

3. Upload TikTok exports (ZIP files)

## Benchmarks (2026)

- **Completion Rate:** 70%+ (Viral) | 67%+ (Educational)
- **Save Rate:** 0.5-1% (Very Good) | 1%+ (Exceptional)
- **Share Rate:** 0.3-0.5% (Very Good) | 0.5%+ (Exceptional)
- **Engagement Rate:** 6-12% (Educational content)

## Data Sources

Export from TikTok Studio:
- Content Performance (365 days)
- Overview (7 days)
- Followers (7 days)
- Viewers (7 days)

## Project Structure
```
tiktok-analytics/
├── dashboard.py          # Main Streamlit app
├── data/                 # Processed data (auto-generated)
│   ├── content.csv
│   ├── overview.csv
│   ├── viewers.csv
│   └── followers.csv
└── README.md
```
