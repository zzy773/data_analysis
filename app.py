import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Streamlit 页面配置
st.set_page_config(page_title="A股组合回测系统", layout="wide")

# 注入 CSS 优化触摸体验
st.markdown(
    """
    <style>
    * { -webkit-touch-callout: none !important; -webkit-user-select: none !important; }
    .js-plotly-plot .plotly .main-svg { touch-action: pan-y !important; }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📈 A股组合等权重回测系统")

# --- 侧边栏参数 ---
st.sidebar.header("参数设置")
start_date_input = st.sidebar.text_input("回测起始时间 (YYYYMMDD)", "20230101")
end_date_input = st.sidebar.text_input("回测结束时间 (YYYYMMDD)", "20240101")
tickers_input = st.sidebar.text_input("股票代码 (逗号分隔)", "002050,600118")

if st.sidebar.button("开始回测"):
    tickers_input = tickers_input.replace('，', ',')
    tickers = [ticker.strip() for ticker in tickers_input.split(',')]
    
    with st.spinner('正在精准获取个股数据...'):
        start_dt = datetime.strptime(start_date_input, "%Y%m%d")
        fetch_start_dt = start_dt - timedelta(days=10)
        fetch_start_str = fetch_start_dt.strftime("%Y%m%d")
        
        close_prices = pd.DataFrame()
        stock_names = {}
        
        for ticker_code in tickers:
            if not ticker_code: continue
            try:
                # 优化点：直接获取单只股票的基本信息，速度极快
                info_df = ak.stock_individual_info_em(symbol=ticker_code)
                stock_names[ticker_code] = info_df[info_df['item'] == '股票简称']['value'].values[0]
                
                # 获取历史行情
                df = ak.stock_zh_a_hist(symbol=ticker_code, period="daily", start_date=fetch_start_str, end_date=end_date_input, adjust="qfq")
                if not df.empty:
                    df.set_index("日期", inplace=True)
                    df.index = pd.to_datetime(df.index)
                    close_prices[ticker_code] = df["收盘"]
                    print(f"成功获取 {stock_names[ticker_code]} 数据")
            except Exception as e:
                stock_names[ticker_code] = ticker_code # 降级处理，显示代码
                st.warning(f"获取代码 {ticker_code} 详情失败，将显示原代码。")

        close_prices.dropna(inplace=True)
        if close_prices.empty:
            st.error("未获取到足够数据，请检查日期或代码。")
            st.stop()

        # 计算逻辑
        daily_returns = close_prices.pct_change().dropna()
        target_start_date = pd.to_datetime(start_date_input)
        daily_returns = daily_returns[daily_returns.index >= target_start_date]
        
        # 个股独立累计收益
        individual_cum_returns = (1 + daily_returns).cumprod()
        portfolio_daily_return = daily_returns.mean(axis=1)
        cumulative_return = (1 + portfolio_daily_return).cumprod()
        
        running_max = cumulative_return.cummax()
        drawdown = (cumulative_return - running_max) / running_max

        # --- Plotly 交互逻辑 ---
        dt_all = pd.date_range(start=cumulative_return.index.min(), end=cumulative_return.index.max())
        dt_breaks = dt_all.difference(cumulative_return.index).strftime('%Y-%m-%d').tolist()

        # 构造悬浮展示数据
        customdata_list = []
        for i in range(len(cumulative_return)):
            date_str = cumulative_return.index[i].strftime('%Y-%m-%d')
            total_growth = f"{(cumulative_return.iloc[i]-1)*100:+.2f}%"
            
            indiv_parts = []
            for t in tickers:
                if t in individual_cum_returns.columns:
                    val = (individual_cum_returns[t].iloc[i] - 1) * 100
                    indiv_parts.append(f"{stock_names[t]}: {val:+.2f}%")
            indiv_str = "<br>".join(indiv_parts)
            customdata_list.append([date_str, total_growth, indiv_str])

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.05, 
                            row_heights=[0.5, 0.25, 0.25])

        # 1. 净值图
        fig.add_trace(go.Scatter(
            x=cumulative_return.index, y=cumulative_return, name='组合净值',
            line=dict(color='#ff4b4b', width=2),
            customdata=customdata_list,
            hovertemplate='<b>%{customdata[0]}</b><br>组合累计收益: %{customdata[1]}<br>------------------<br>%{customdata[2]}<extra></extra>'
        ), row=1, col=1)

        # 2. 涨跌柱
        fig.add_trace(go.Bar(x=cumulative_return.index, y=portfolio_daily_return, marker_color='#3b82f6', opacity=0.8), row=2, col=1)

        # 3. 回撤图
        fig.add_trace(go.Scatter(x=cumulative_return.index, y=drawdown, fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.2)', line=dict(color='#22c55e')), row=3, col=1)

        fig.update_layout(
            height=700, margin=dict(l=10, r=10, t=30, b=20),
            hovermode="closest", dragmode=False, showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            hoverlabel=dict(bgcolor="rgba(255, 255, 255, 0.9)", font=dict(color="#000", size=12), align="left")
        )
        
        fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], tickformat="%y-%m-%d", showspikes=True, spikemode='across', spikesnap='cursor')
        fig.update_yaxes(fixedrange=True)

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # 总结表格
        final_perf = (individual_cum_returns.iloc[-1] - 1).sort_values(ascending=False)
        summary_df = pd.DataFrame({
            "股票简称": [stock_names[c] for c in final_perf.index],
            "周期累计贡献": final_perf.values
        })
        st.subheader("📊 组合个股表现总结")
        st.table(summary_df.style.format({"周期累计贡献": "{:.2%}"}))
