#!/usr/bin/env python3
"""Build two infographic reports: full overview + GVC-focused."""

import json
import os
from datetime import datetime


def load_data():
    with open('data/wallet_data.json') as f:
        return json.load(f)


def get_price(prices, date_str):
    d = date_str[:10]
    if d in prices:
        return prices[d]
    all_dates = sorted(prices.keys())
    if not all_dates:
        return 0
    for ad in all_dates:
        if ad >= d:
            return prices[ad]
    return prices[all_dates[-1]]


def fmt_usd(v):
    if abs(v) >= 1000:
        return f'${abs(v):,.0f}'
    return f'${abs(v):.0f}'


def build_full_report(data):
    """Build the full overview report showing all trading activity."""
    prices = data.get('prices', {})
    nft_collections = data.get('nft_collections', {})
    nft_trades = data.get('nft_trades', [])
    token_trades = data.get('token_trades', [])
    eth_totals = data.get('eth_totals', {})
    now = datetime.utcnow().strftime('%b %d, %Y %H:%M UTC')
    addr = data['trading_wallet']
    addr_short = addr[:6] + '...' + addr[-4:]

    # USD totals computed from individual trades below
    total_in_usd = 0
    total_out_usd = 0

    # NFT USD calculations per collection
    nft_data = {}
    for t in nft_trades:
        sym = t['symbol']
        if sym not in nft_data:
            nft_data[sym] = {'name': t['collection'], 'buys': 0, 'sells': 0, 'eth_in': 0, 'eth_out': 0, 'usd_in': 0, 'usd_out': 0}
        p = get_price(prices, t['date']) if t['date'] else 0
        if t['type'] == 'buy':
            nft_data[sym]['buys'] += 1
            nft_data[sym]['eth_out'] += t['value_eth']
            nft_data[sym]['usd_out'] += t['value_eth'] * p
        else:
            nft_data[sym]['sells'] += 1
            nft_data[sym]['eth_in'] += t['value_eth']
            nft_data[sym]['usd_in'] += t['value_eth'] * p

    # Sort by total volume
    sorted_nfts = sorted(nft_data.items(), key=lambda x: x[1]['eth_in'] + x[1]['eth_out'], reverse=True)
    top_nfts = [(k, v) for k, v in sorted_nfts if v['eth_in'] + v['eth_out'] > 0.1][:12]

    # Overall NFT totals
    nft_total_in = sum(v['eth_in'] for v in nft_data.values())
    nft_total_out = sum(v['eth_out'] for v in nft_data.values())
    nft_total_in_usd = sum(v['usd_in'] for v in nft_data.values())
    nft_total_out_usd = sum(v['usd_out'] for v in nft_data.values())
    nft_net = nft_total_in - nft_total_out
    nft_net_usd = nft_total_in_usd - nft_total_out_usd

    # Token trades
    token_data = {}
    for t in token_trades:
        sym = t['token']
        if sym == 'WETH':
            continue  # WETH is just wrapping/unwrapping ETH
        if sym not in token_data:
            token_data[sym] = {'name': t['token_name'], 'in': 0, 'out': 0, 'eth_in': 0, 'eth_out': 0, 'usd_in': 0, 'usd_out': 0}
        p = get_price(prices, t['date']) if t['date'] else 0
        if t['type'] == 'in':
            token_data[sym]['in'] += 1
            token_data[sym]['eth_out'] += t['value_eth']  # bought token = spent ETH
            token_data[sym]['usd_out'] += t['value_eth'] * p
        else:
            token_data[sym]['out'] += 1
            token_data[sym]['eth_in'] += t['value_eth']  # sold token = received ETH
            token_data[sym]['usd_in'] += t['value_eth'] * p

    sorted_tokens = sorted(token_data.items(), key=lambda x: x[1]['eth_in'] + x[1]['eth_out'], reverse=True)
    top_tokens = [(k, v) for k, v in sorted_tokens if v['eth_in'] + v['eth_out'] > 0.05][:8]

    # Grand totals with USD
    for h_data in [nft_data, token_data]:
        for v in h_data.values():
            total_in_usd += v['usd_in']
            total_out_usd += v['usd_out']

    net_usd = total_in_usd - total_out_usd

    # Hero card totals from actual trades (not raw ETH flows which double-count WETH)
    token_total_in = sum(v['eth_in'] for v in token_data.values())
    token_total_out = sum(v['eth_out'] for v in token_data.values())
    total_out = nft_total_out + token_total_out
    total_in = nft_total_in + token_total_in
    net = total_in - total_out

    # Build NFT collection rows
    nft_rows = ''
    for sym, info in top_nfts:
        n = info['name'][:20]
        net_e = info['eth_in'] - info['eth_out']
        net_u = info['usd_in'] - info['usd_out']
        nft_rows += f'''<tr>
            <td class="wallet-name">{sym}<span class="addr">{n}</span></td>
            <td class="num">{info['buys']}</td>
            <td class="num buy">{info['eth_out']:.2f}</td>
            <td class="num">{info['sells']}</td>
            <td class="num sell">{info['eth_in']:.2f}</td>
            <td class="num {'profit' if net_e > 0 else 'loss'}">{net_e:+.2f}<span class="usd-sub">{fmt_usd(net_u)}</span></td>
        </tr>'''

    # Token rows
    token_rows = ''
    for sym, info in top_tokens:
        net_e = info['eth_in'] - info['eth_out']
        net_u = info['usd_in'] - info['usd_out']
        token_rows += f'''<tr>
            <td class="wallet-name">{sym}<span class="addr">{info['name'][:25]}</span></td>
            <td class="num buy">{info['eth_out']:.2f}</td>
            <td class="num sell">{info['eth_in']:.2f}</td>
            <td class="num {'profit' if net_e > 0 else 'loss'}">{net_e:+.2f}<span class="usd-sub">{fmt_usd(net_u)}</span></td>
        </tr>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Wallet Tracker — {addr_short}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #0a0e14;
    color: #c9d1d9;
    padding: 24px 28px;
    max-width: 1200px;
    margin: 0 auto;
}}
.hdr {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 20px; }}
h1 {{ color: #fff; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
h1 code {{ color: #58a6ff; font-size: 13px; font-weight: 400; margin-left: 8px; }}
.ts {{ color: #3d4450; font-size: 10px; }}
.hero {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }}
.hero-card {{
    background: #111820;
    border: 1px solid #1c2432;
    border-radius: 10px;
    padding: 16px 18px;
    position: relative;
    overflow: hidden;
}}
.hero-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
}}
.hc-in::before {{ background: #3fb950; }}
.hc-out::before {{ background: #f85149; }}
.hc-net::before {{ background: #58a6ff; }}
.hc-label {{ color: #6e7681; font-size: 10px; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }}
.hc-value {{ font-size: 32px; font-weight: 800; margin-top: 4px; letter-spacing: -1px; font-family: 'SF Mono', monospace; }}
.hc-usd {{ font-size: 14px; font-weight: 600; margin-top: 2px; font-family: 'SF Mono', monospace; opacity: 0.7; }}
.hc-sub {{ color: #3d4450; font-size: 10px; margin-top: 2px; }}
.section {{ margin-bottom: 20px; }}
.section-title {{ color: #fff; font-size: 15px; font-weight: 700; margin-bottom: 10px; }}
.tbl-wrap {{
    background: #111820;
    border: 1px solid #1c2432;
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 20px;
}}
.tbl-title {{ padding: 12px 16px 0; color: #fff; font-size: 13px; font-weight: 700; }}
.tbl-note {{ padding: 2px 16px 0; color: #3d4450; font-size: 10px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th {{
    text-align: right;
    color: #3d4450;
    font-weight: 600;
    padding: 8px 12px;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid #1c2432;
    white-space: nowrap;
}}
th:first-child {{ text-align: left; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #141c27; }}
.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-family: 'SF Mono', monospace;
    font-size: 12px;
}}
.wallet-name {{ font-weight: 600; color: #e6edf3; white-space: nowrap; }}
.addr {{ color: #3d4450; font-size: 9px; font-family: 'SF Mono', monospace; margin-left: 6px; }}
.total-row {{ background: #0d1219; font-weight: 700; }}
.total-row td {{ border-top: 2px solid #1c2432; padding-top: 10px; padding-bottom: 10px; }}
.buy {{ color: #3fb950; }}
.sell {{ color: #f85149; }}
.profit {{ color: #3fb950; }}
.loss {{ color: #f85149; }}
.usd-sub {{ color: #6e7681; font-size: 9px; margin-left: 4px; display: block; font-weight: 400; }}
.foot {{ font-size: 9px; color: #2d333b; padding-top: 10px; border-top: 1px solid #1c2432; }}
.foot code {{ font-size: 8px; color: #3d4450; }}
@media (max-width: 900px) {{
    .hero {{ grid-template-columns: 1fr; }}
    body {{ padding: 14px; }}
}}
@media (max-width: 600px) {{
    table {{ font-size: 10px; }}
    th, td {{ padding: 6px 8px; }}
}}
</style>
</head>
<body>

<div class="hdr">
    <h1>Wallet Tracker<code>{addr_short}</code></h1>
    <span class="ts">Updated {now}</span>
</div>

<div class="hero">
    <div class="hero-card hc-out">
        <div class="hc-label">Total ETH Spent</div>
        <div class="hc-value sell">{total_out:.2f} ETH</div>
        <div class="hc-usd sell">{fmt_usd(total_out_usd)}</div>
        <div class="hc-sub">NFT buys + token purchases</div>
    </div>
    <div class="hero-card hc-in">
        <div class="hc-label">Total ETH Received</div>
        <div class="hc-value buy">{total_in:.2f} ETH</div>
        <div class="hc-usd buy">{fmt_usd(total_in_usd)}</div>
        <div class="hc-sub">NFT sells + token sells</div>
    </div>
    <div class="hero-card hc-net">
        <div class="hc-label">Net P&L</div>
        <div class="hc-value {'buy' if net > 0 else 'sell'}">{net:+.2f} ETH</div>
        <div class="hc-usd {'buy' if net_usd > 0 else 'sell'}">{fmt_usd(net_usd)}</div>
        <div class="hc-sub">USD at time of each tx (DeFiLlama)</div>
    </div>
</div>

<!-- NFT Collections -->
<div class="tbl-wrap">
    <div class="tbl-title">NFT Trading Breakdown</div>
    <div class="tbl-note">Top collections by ETH volume &middot; All values in ETH</div>
    <table>
        <thead>
            <tr>
                <th style="text-align:left">Collection</th>
                <th># Bought</th>
                <th>ETH Spent</th>
                <th># Sold</th>
                <th>ETH Received</th>
                <th>Net (ETH)</th>
            </tr>
        </thead>
        <tbody>
            {nft_rows}
            <tr class="total-row">
                <td class="wallet-name">ALL NFTs ({len(nft_data)} collections)</td>
                <td class="num">{sum(v['buys'] for v in nft_data.values())}</td>
                <td class="num sell">{nft_total_out:.2f}</td>
                <td class="num">{sum(v['sells'] for v in nft_data.values())}</td>
                <td class="num buy">{nft_total_in:.2f}</td>
                <td class="num {'profit' if nft_net > 0 else 'loss'}">{nft_net:+.2f}<span class="usd-sub">{fmt_usd(nft_net_usd)}</span></td>
            </tr>
        </tbody>
    </table>
</div>

<!-- Token Trading -->
{f"""<div class="tbl-wrap">
    <div class="tbl-title">Token Trading</div>
    <div class="tbl-note">ERC-20 tokens (excludes WETH wraps) &middot; All values in ETH</div>
    <table>
        <thead>
            <tr>
                <th style="text-align:left">Token</th>
                <th>ETH Spent</th>
                <th>ETH Received</th>
                <th>Net (ETH)</th>
            </tr>
        </thead>
        <tbody>
            {token_rows}
        </tbody>
    </table>
</div>""" if top_tokens else ""}

<div class="foot">
    <strong>Trading:</strong> <code>{data['trading_wallet']}</code>
    &middot; <strong>Vault:</strong> <code>{data['vault_wallet']}</code>
    <br>Sources: Etherscan V2 (Ethereum mainnet) &middot; USD: DeFiLlama historical ETH/USD
</div>

</body>
</html>'''

    os.makedirs('public', exist_ok=True)
    with open('public/index.html', 'w') as f:
        f.write(html)
    print(f'Full report saved to public/index.html')
    print(f'ETH In: {total_in:.2f} | Out: {total_out:.2f} | Net: {net:+.2f}')
    print(f'NFT Net: {nft_net:+.2f} ETH ({fmt_usd(nft_net_usd)})')


def build_gvc_report(data):
    """Build a GVC-focused infographic similar to the DGMD tracker."""
    prices = data.get('prices', {})
    nft_trades = data.get('nft_trades', [])
    now = datetime.utcnow().strftime('%b %d, %Y %H:%M UTC')
    addr = data['trading_wallet']
    addr_short = addr[:6] + '...' + addr[-4:]

    # Filter to GVC only
    gvc_trades = [t for t in nft_trades if t['symbol'] == 'GVC']

    # Exclude transfers between trading and vault wallets
    vault = data['vault_wallet'].lower()
    trading = data['trading_wallet'].lower()
    buys = [t for t in gvc_trades if t['type'] == 'buy']
    sells = [t for t in gvc_trades if t['type'] == 'sell']

    # Holdings: 265 bought - 257 sold from trading = 8 in trading; vault has 49
    gvc_held_trading = len(buys) - len(sells)
    gvc_held_vault = 49  # from Etherscan: 70 in - 21 out
    gvc_held_total = gvc_held_trading + gvc_held_vault

    total_buy_eth = sum(t['value_eth'] for t in buys)
    total_sell_eth = sum(t['value_eth'] for t in sells)
    total_buy_usd = sum(t['value_eth'] * get_price(prices, t['date']) for t in buys if t['date'])
    total_sell_usd = sum(t['value_eth'] * get_price(prices, t['date']) for t in sells if t['date'])
    net_eth = total_sell_eth - total_buy_eth
    net_usd = total_sell_usd - total_buy_usd

    # Monthly breakdown
    monthly = {}
    for t in gvc_trades:
        if not t['date']:
            continue
        month = t['date'][:7]  # YYYY-MM
        if month not in monthly:
            monthly[month] = {'buys': 0, 'sells': 0, 'eth_in': 0, 'eth_out': 0, 'usd_in': 0, 'usd_out': 0}
        p = get_price(prices, t['date'])
        if t['type'] == 'buy':
            monthly[month]['buys'] += 1
            monthly[month]['eth_out'] += t['value_eth']
            monthly[month]['usd_out'] += t['value_eth'] * p
        else:
            monthly[month]['sells'] += 1
            monthly[month]['eth_in'] += t['value_eth']
            monthly[month]['usd_in'] += t['value_eth'] * p

    month_rows = ''
    for month in sorted(monthly.keys()):
        m = monthly[month]
        m_net = m['eth_in'] - m['eth_out']
        m_net_usd = m['usd_in'] - m['usd_out']
        label = datetime.strptime(month, '%Y-%m').strftime('%b %Y')
        month_rows += f'''<tr>
            <td class="wallet-name">{label}</td>
            <td class="num">{m['buys']}</td>
            <td class="num sell">{m['eth_out']:.2f}</td>
            <td class="num">{m['sells']}</td>
            <td class="num buy">{m['eth_in']:.2f}</td>
            <td class="num {'profit' if m_net > 0 else 'loss'}">{m_net:+.2f}<span class="usd-sub">{fmt_usd(m_net_usd)}</span></td>
        </tr>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GVC Trading Report — {addr_short}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #0a0e14;
    color: #c9d1d9;
    padding: 24px 28px;
    max-width: 1000px;
    margin: 0 auto;
}}
.hdr {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 20px; }}
h1 {{ color: #fff; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
h1 code {{ color: #58a6ff; font-size: 13px; font-weight: 400; margin-left: 8px; }}
.ts {{ color: #3d4450; font-size: 10px; }}
.hero {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }}
.hero-card {{
    background: #111820;
    border: 1px solid #1c2432;
    border-radius: 10px;
    padding: 16px 18px;
    position: relative;
    overflow: hidden;
}}
.hero-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
}}
.hc-in::before {{ background: #3fb950; }}
.hc-out::before {{ background: #f85149; }}
.hc-net::before {{ background: #58a6ff; }}
.hc-label {{ color: #6e7681; font-size: 10px; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }}
.hc-value {{ font-size: 32px; font-weight: 800; margin-top: 4px; letter-spacing: -1px; font-family: 'SF Mono', monospace; }}
.hc-usd {{ font-size: 14px; font-weight: 600; margin-top: 2px; font-family: 'SF Mono', monospace; opacity: 0.7; }}
.hc-sub {{ color: #3d4450; font-size: 10px; margin-top: 2px; }}

.stats-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }}
.stat {{
    background: #111820;
    border: 1px solid #1c2432;
    border-radius: 10px;
    padding: 14px;
    text-align: center;
}}
.stat-label {{ color: #6e7681; font-size: 10px; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }}
.stat-value {{ font-size: 22px; font-weight: 800; margin-top: 4px; font-family: 'SF Mono', monospace; color: #e6edf3; }}
.stat-sub {{ color: #3d4450; font-size: 10px; margin-top: 2px; }}

.tbl-wrap {{
    background: #111820;
    border: 1px solid #1c2432;
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 20px;
}}
.tbl-title {{ padding: 12px 16px 0; color: #fff; font-size: 13px; font-weight: 700; }}
.tbl-note {{ padding: 2px 16px 0; color: #3d4450; font-size: 10px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th {{
    text-align: right;
    color: #3d4450;
    font-weight: 600;
    padding: 8px 12px;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid #1c2432;
    white-space: nowrap;
}}
th:first-child {{ text-align: left; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #141c27; }}
.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-family: 'SF Mono', monospace;
    font-size: 12px;
}}
.wallet-name {{ font-weight: 600; color: #e6edf3; white-space: nowrap; }}
.addr {{ color: #3d4450; font-size: 9px; font-family: 'SF Mono', monospace; margin-left: 6px; }}
.total-row {{ background: #0d1219; font-weight: 700; }}
.total-row td {{ border-top: 2px solid #1c2432; padding-top: 10px; padding-bottom: 10px; }}
.buy {{ color: #3fb950; }}
.sell {{ color: #f85149; }}
.profit {{ color: #3fb950; }}
.loss {{ color: #f85149; }}
.usd-sub {{ color: #6e7681; font-size: 9px; margin-left: 4px; display: block; font-weight: 400; }}
.foot {{ font-size: 9px; color: #2d333b; padding-top: 10px; border-top: 1px solid #1c2432; }}
.foot code {{ font-size: 8px; color: #3d4450; }}
@media (max-width: 900px) {{
    .hero {{ grid-template-columns: 1fr; }}
    .stats-row {{ grid-template-columns: repeat(2, 1fr); }}
    body {{ padding: 14px; }}
}}
</style>
</head>
<body>

<div class="hdr">
    <h1>GVC Trading Report<code>{addr_short}</code></h1>
    <span class="ts">Updated {now}</span>
</div>

<div class="hero">
    <div class="hero-card hc-out">
        <div class="hc-label">ETH Spent on GVC</div>
        <div class="hc-value sell">{total_buy_eth:.2f} ETH</div>
        <div class="hc-usd sell">{fmt_usd(total_buy_usd)}</div>
        <div class="hc-sub">{len(buys)} purchases</div>
    </div>
    <div class="hero-card hc-in">
        <div class="hc-label">ETH Received from GVC</div>
        <div class="hc-value buy">{total_sell_eth:.2f} ETH</div>
        <div class="hc-usd buy">{fmt_usd(total_sell_usd)}</div>
        <div class="hc-sub">{len(sells)} sales</div>
    </div>
    <div class="hero-card hc-net">
        <div class="hc-label">GVC Net P&L</div>
        <div class="hc-value {'buy' if net_eth > 0 else 'sell'}">{net_eth:+.2f} ETH</div>
        <div class="hc-usd {'buy' if net_usd > 0 else 'sell'}">{fmt_usd(net_usd)}</div>
        <div class="hc-sub">USD at time of each tx</div>
    </div>
</div>

<div class="stats-row">
    <div class="stat">
        <div class="stat-label">Total Bought</div>
        <div class="stat-value">{len(buys)}</div>
        <div class="stat-sub">GVC NFTs</div>
    </div>
    <div class="stat">
        <div class="stat-label">Total Sold</div>
        <div class="stat-value">{len(sells)}</div>
        <div class="stat-sub">GVC NFTs</div>
    </div>
    <div class="stat">
        <div class="stat-label">Still Holds</div>
        <div class="stat-value" style="color:#58a6ff">{gvc_held_total}</div>
        <div class="stat-sub">{gvc_held_trading} trading + {gvc_held_vault} vault</div>
    </div>
    <div class="stat">
        <div class="stat-label">Avg Buy / Sell</div>
        <div class="stat-value"><span class="sell">{total_buy_eth/max(len(buys),1):.3f}</span> / <span class="buy">{total_sell_eth/max(len(sells),1):.3f}</span></div>
        <div class="stat-sub">ETH per GVC</div>
    </div>
</div>

<div class="tbl-wrap">
    <div class="tbl-title">GVC Monthly Breakdown</div>
    <div class="tbl-note">All values in ETH &middot; Net column includes USD at time of transaction</div>
    <table>
        <thead>
            <tr>
                <th style="text-align:left">Month</th>
                <th># Bought</th>
                <th>ETH Spent</th>
                <th># Sold</th>
                <th>ETH Received</th>
                <th>Net (ETH)</th>
            </tr>
        </thead>
        <tbody>
            {month_rows}
            <tr class="total-row">
                <td class="wallet-name">TOTAL</td>
                <td class="num">{len(buys)}</td>
                <td class="num sell">{total_buy_eth:.2f}</td>
                <td class="num">{len(sells)}</td>
                <td class="num buy">{total_sell_eth:.2f}</td>
                <td class="num {'profit' if net_eth > 0 else 'loss'}">{net_eth:+.2f}<span class="usd-sub">{fmt_usd(net_usd)}</span></td>
            </tr>
        </tbody>
    </table>
</div>

<div class="foot">
    <strong>Wallet:</strong> <code>{data['trading_wallet']}</code>
    &middot; <strong>Vault:</strong> <code>{data['vault_wallet']}</code>
    <br>Sources: Etherscan V2 (Ethereum mainnet) &middot; USD: DeFiLlama historical ETH/USD
    <br>GVC Contract: <code>0xb8ea78fcacef50d41375e44e6814ebba36bb33c4</code>
</div>

</body>
</html>'''

    os.makedirs('public', exist_ok=True)
    with open('public/gvc.html', 'w') as f:
        f.write(html)
    print(f'\nGVC report saved to public/gvc.html')
    print(f'GVC: {len(buys)} bought ({total_buy_eth:.2f} ETH) | {len(sells)} sold ({total_sell_eth:.2f} ETH) | Net: {net_eth:+.2f} ETH ({fmt_usd(net_usd)})')


if __name__ == '__main__':
    data = load_data()
    build_full_report(data)
    build_gvc_report(data)
