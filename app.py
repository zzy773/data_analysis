import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Streamlit 页面配置
st.set_page_config(page_title="A股组合多维度回测系统", layout="wide")

# 极速版 CSS
st.markdown(
    """
    <style>
    * { -webkit-touch-callout: none !important; -webkit-user-select: none !important; }
    .js-plotly-plot .plotly .main-svg { touch-action: pan-y !important; }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🚀 A股组合分层分析系统 (极速优化版)")

# --- 侧边栏参数 ---
st.sidebar.header("参数设置")
start_date_input = st.sidebar.text_input("起始时间 (YYYYMMDD)", "20230101")
end_date_input = st.sidebar.text_input("结束时间 (YYYYMMDD)", "20240101")
tickers_input = st.sidebar.text_input("股票代码", "002851,002865,603061,603667")

if st.sidebar.button("开始回测"):
    tickers_input = tickers_input.replace('，', ',')
    tickers = [t.strip() for t in tickers_input.split(',')]
    
    # 建立进度条
    progress_bar = st.progress(0)
    
    with st.spinner('正在极速抓取行情数据...'):
        start_dt = datetime.strptime(start_date_input, "%Y%m%d")
        fetch_start_str = (start_dt - timedelta(days=10)).strftime("%Y%m%d")
        
        close_prices = pd.DataFrame()
        stock_names = {}
        
        # 优化：不再使用慢速的 info 接口，改为直接从历史行情中剥离或使用映射
        for i, ticker in enumerate(tickers):
            try:
                # 获取历史行情
                df = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=fetch_start_str, end_date=end_date_input, adjust="qfq")
                if not df.empty:
                    df.set_index("日期", inplace=True)
                    df.index = pd.to_datetime(df.index)
                    close_prices[ticker] = df["收盘"]
                    # 临时暂代名称，若需要精准中文名，建议在下方明细表中手动维护或通过小巧的 spot 接口一次性获取
                    stock_names[ticker] = ticker 
                progress_bar.progress((i + 1) / len(tickers))
            except:
                pass

        # 尝试一次性获取全市场名称映射（比循环获取单股信息快得多）
        try:
            name_map_df = ak.stock_zh_a_spot_em()[['代码', '名称']]
            name_dict = dict(zip(name_map_df['代码'], name_map_df['名称']))
            for t in tickers:
                if t in name_dict: stock_names[t] = name_dict[t]
        except:
            pass

        close_prices.dropna(inplace=True)
        if close_prices.empty:
            st.error("数据抓取失败，请检查网络或代码")
            st.stop()

        # --- 计算核心指标 ---
        daily_returns = close_prices.pct_change().dropna()
        target_start_date = pd.to_datetime(start_date_input)
        daily_returns = daily_returns[daily_returns.index >= target_start_date]
        
        portfolio_return = daily_returns.mean(axis=1)
        cumulative_return = (1 + portfolio_return).cumprod()
        individual_cum_returns = (1 + daily_returns).cumprod()
        drawdown = (cumulative_return - cumulative_return.cummax()) / cumulative_return.cummax()

        # --- 绘图逻辑：重排顺序 ---
        dt_breaks = pd.date_range(start=cumulative_return.index.min(), end=cumulative_return.index.max()).difference(cumulative_return.index).strftime('%Y-%m-%d').tolist()

        fig = make_subplots(
            rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04, 
            row_heights=[0.3, 0.2, 0.2, 0.3],
            subplot_titles=("1. 组合累积净值", "2. 组合每日涨跌 (%)", "3. 组合最大回撤 (%)", "4. 个股累积贡献对比")
        )

        date_display = cumulative_return.index.strftime('%Y年%m月%d日')

        # 1. 组合净值
        total_growth_hover = [f"{(y-1)*100:+.2f}%" for y in cumulative_return]
        fig.add_trace(go.Scatter(x=cumulative_return.index, y=cumulative_return, name='组合', line=dict(color='#ff4b4b', width=3),
                                 customdata=list(zip(date_display, total_growth_hover)),
                                 hovertemplate='<b>组合总计</b><br>%{customdata[0]}<br>净值: %{y:.4f}<br>累计增长: %{customdata[1]}<extra></extra>'), row=1, col=1)

        # 2. 每日涨跌
        daily_ret_hover = [f"{v*100:+.2f}%" for v in portfolio_return]
        fig.add_trace(go.Bar(x=portfolio_return.index, y=portfolio_return, name='涨跌', marker_color='#3b82f6', opacity=0.7,
                             customdata=list(zip(date_display, daily_ret_hover)),
                             hovertemplate='<b>%{customdata[0]}</b><br>当日涨跌: %{customdata[1]}<extra></extra>'), row=2, col=1)

        # 3. 最大回撤
        drawdown_hover = [f"{v*100:.2f}%" for v in drawdown]
        fig.add_trace(go.Scatter(x=drawdown.index, y=drawdown, name='回撤', fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.2)', line=dict(color='#22c55e'),
                                 customdata=list(zip(date_display, drawdown_hover)),
                                 hovertemplate='<b>%{customdata[0]}</b><br>动态回撤: %{customdata[1]}<extra></extra>'), row=3, col=1)

        # 4. 个股贡献
        colors = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A']
        for i, ticker in enumerate(tickers):
            if ticker in individual_cum_returns.columns:
                name = stock_names[ticker]
                y_val = individual_cum_returns[ticker]
                hover_growth = [f"{v*100-100:+.2f}%" for v in y_val]
                fig.add_trace(go.Scatter(x=individual_cum_returns.index, y=y_val, name=name, mode='lines',
                                         line=dict(width=1.8, color=colors[i % len(colors)]),
                                         customdata=list(zip(date_display, hover_growth)),
                                         hovertemplate=f'<b>{name}</b><br>%{{customdata[0]}}<br>累计贡献: %{{customdata[1]}}<extra></extra>'), row=4, col=1)

        fig.update_layout(height=900, margin=dict(l=10, r=10, t=50, b=20), hovermode="closest", dragmode=False, showlegend=False)
        fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], tickformat="%y-%m-%d", showgrid=True, gridcolor='rgba(128,128,128,0.15)', showspikes=True, spikemode='across')
        fig.update_yaxes(fixedrange=True)

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        
        # 结果表
        st.subheader("📊 最终贡献排名")
        final_perf = (individual_cum_returns.iloc[-1] - 1).sort_values(ascending=False)
        st.table(pd.DataFrame({"股票": [stock_names[c] for c in final_perf.index], "收益": final_perf.values}).style.format({"收益": "{:.2%}"}))
