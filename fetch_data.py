#!/usr/bin/env python3
"""Fetch all trading activity for target wallet via Etherscan V2 + DeFiLlama."""

import json
import os
import time
import urllib.request
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

API_KEY = 'KI3JG1UGI7B7SNZIVZK943XRV8SFK83NHG'
TRADING = '0x2546cf80eb6fb4ee0f22e1a9803Fb268FF7B591D'
VAULT = '0xa799242db91ec215c5a2f6628f4cceda9b478727'

os.makedirs('data', exist_ok=True)


def eth_api(module, action, address, **kwargs):
    """Call Etherscan V2 API."""
    params = f'chainid=1&module={module}&action={action}&address={address}&apikey={API_KEY}'
    for k, v in kwargs.items():
        params += f'&{k}={v}'
    url = f'https://api.etherscan.io/v2/api?{params}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    return resp.get('result', [])


def fetch_all_pages(module, action, address, page_size=1000):
    """Fetch all pages of results."""
    all_results = []
    page = 1
    while True:
        results = eth_api(module, action, address,
                         startblock=0, endblock=99999999,
                         page=page, offset=page_size, sort='asc')
        if not results or not isinstance(results, list):
            break
        all_results.extend(results)
        print(f'  Page {page}: {len(results)} results (total: {len(all_results)})')
        if len(results) < page_size:
            break
        page += 1
        time.sleep(0.25)
    return all_results


def fetch_prices(dates):
    """Fetch ETH/USD prices for all unique dates via DeFiLlama."""
    ETH_ADDR = 'ethereum:0x0000000000000000000000000000000000000000'
    price_map = {}
    dates = sorted(set(dates))
    print(f'\nFetching ETH prices for {len(dates)} unique dates...')

    for i, d in enumerate(dates):
        ts = int(datetime.strptime(d, '%Y-%m-%d').timestamp()) + 43200
        url = f'https://coins.llama.fi/prices/historical/{ts}/{ETH_ADDR}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
            price = resp.get('coins', {}).get(ETH_ADDR, {}).get('price', 0)
            price_map[d] = round(price, 2)
            if (i + 1) % 20 == 0:
                print(f'  {i+1}/{len(dates)}: {d} = ${price:.2f}')
        except Exception as e:
            print(f'  Error for {d}: {e}')
            price_map[d] = 0
        time.sleep(0.1)

    print(f'Fetched {len(price_map)} prices')
    return price_map


def main():
    print('=== Fetching Trading Wallet Data ===')
    print(f'Trading: {TRADING}')
    print(f'Vault: {VAULT}')

    # 1. Normal transactions
    print('\n--- Normal Transactions ---')
    normal_txs = fetch_all_pages('account', 'txlist', TRADING)
    print(f'Total normal txs: {len(normal_txs)}')

    # 2. Internal transactions
    print('\n--- Internal Transactions ---')
    internal_txs = fetch_all_pages('account', 'txlistinternal', TRADING)
    print(f'Total internal txs: {len(internal_txs)}')

    # 3. ERC-20 transfers
    print('\n--- ERC-20 Transfers ---')
    erc20_txs = fetch_all_pages('account', 'tokentx', TRADING)
    print(f'Total ERC-20 txs: {len(erc20_txs)}')

    # 4. ERC-721 transfers
    print('\n--- ERC-721 Transfers ---')
    nft_txs = fetch_all_pages('account', 'tokennfttx', TRADING)
    print(f'Total NFT txs: {len(nft_txs)}')

    # Build a tx_hash -> ETH value map from normal + internal + WETH txs
    # Many NFT sales pay via WETH, so we must include those
    WETH_ADDR = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
    tx_eth = {}
    for tx in normal_txs:
        h = tx['hash']
        val = int(tx['value']) / 1e18
        ts = int(tx['timeStamp'])
        dt = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
        is_out = tx['from'].lower() == TRADING.lower()
        if h not in tx_eth:
            tx_eth[h] = {'date': dt, 'eth_out': 0, 'eth_in': 0}
        if is_out:
            tx_eth[h]['eth_out'] += val
        else:
            tx_eth[h]['eth_in'] += val

    for tx in internal_txs:
        h = tx['hash']
        val = int(tx['value']) / 1e18
        ts = int(tx['timeStamp'])
        dt = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
        is_out = tx['from'].lower() == TRADING.lower()
        if h not in tx_eth:
            tx_eth[h] = {'date': dt, 'eth_out': 0, 'eth_in': 0}
        if is_out:
            tx_eth[h]['eth_out'] += val
        else:
            tx_eth[h]['eth_in'] += val

    # Also include WETH (Wrapped ETH) transfers — these are ETH-equivalent
    for tx in erc20_txs:
        if tx.get('contractAddress', '').lower() != WETH_ADDR:
            continue
        h = tx['hash']
        val = int(tx['value']) / 1e18
        ts = int(tx['timeStamp'])
        dt = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
        is_in = tx['to'].lower() == TRADING.lower()
        if h not in tx_eth:
            tx_eth[h] = {'date': dt, 'eth_out': 0, 'eth_in': 0}
        if is_in:
            tx_eth[h]['eth_in'] += val
        else:
            tx_eth[h]['eth_out'] += val

    # Process NFT trades - match NFT transfers to ETH values
    nft_trades = []
    nft_collections = {}
    for tx in nft_txs:
        h = tx['hash']
        collection = tx.get('tokenName', 'Unknown')
        sym = tx.get('tokenSymbol', '?')
        is_buy = tx['to'].lower() == TRADING.lower()
        eth_info = tx_eth.get(h, {'date': '', 'eth_out': 0, 'eth_in': 0})
        eth_val = eth_info['eth_out'] if is_buy else eth_info['eth_in']
        date = eth_info.get('date', '')
        if not date:
            ts = int(tx['timeStamp'])
            date = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')

        trade = {
            'date': date,
            'collection': collection,
            'symbol': sym,
            'token_id': tx.get('tokenID', ''),
            'type': 'buy' if is_buy else 'sell',
            'value_eth': eth_val,
            'tx_hash': h,
            'contract': tx['contractAddress'],
        }
        nft_trades.append(trade)

        key = sym
        if key not in nft_collections:
            nft_collections[key] = {'name': collection, 'buys': 0, 'sells': 0, 'eth_in': 0, 'eth_out': 0, 'contract': tx['contractAddress']}
        if is_buy:
            nft_collections[key]['buys'] += 1
            nft_collections[key]['eth_out'] += eth_val
        else:
            nft_collections[key]['sells'] += 1
            nft_collections[key]['eth_in'] += eth_val

    # Process ERC-20 token trades
    # Filter out spam (tokens with only 1 'in' and 0 'out' are likely airdrops/spam)
    token_summary = {}
    token_trades = []
    SPAM_TOKENS = set()

    for tx in erc20_txs:
        sym = tx.get('tokenSymbol', '?')
        name = tx.get('tokenName', 'Unknown')
        key = sym
        if key not in token_summary:
            token_summary[key] = {'name': name, 'in': 0, 'out': 0, 'contract': tx['contractAddress']}
        is_in = tx['to'].lower() == TRADING.lower()
        if is_in:
            token_summary[key]['in'] += 1
        else:
            token_summary[key]['out'] += 1

    # Identify real tokens (traded both ways, or significant WETH activity)
    REAL_TOKENS = set()
    for sym, info in token_summary.items():
        if info['in'] + info['out'] >= 3 and (info['in'] > 0 and info['out'] > 0):
            REAL_TOKENS.add(sym)
        if sym in ('WETH', 'USDC', 'VIBESTR'):
            REAL_TOKENS.add(sym)

    for tx in erc20_txs:
        sym = tx.get('tokenSymbol', '?')
        if sym not in REAL_TOKENS:
            continue
        h = tx['hash']
        name = tx.get('tokenName', 'Unknown')
        dec = int(tx.get('tokenDecimal', 18))
        amount = int(tx['value']) / (10 ** dec) if dec > 0 else int(tx['value'])
        is_in = tx['to'].lower() == TRADING.lower()
        eth_info = tx_eth.get(h, {'date': '', 'eth_out': 0, 'eth_in': 0})
        date = eth_info.get('date', '')
        if not date:
            ts = int(tx['timeStamp'])
            date = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')

        token_trades.append({
            'date': date,
            'token': sym,
            'token_name': name,
            'type': 'in' if is_in else 'out',
            'amount': amount,
            'value_eth': eth_info['eth_out'] if is_in else eth_info['eth_in'],
            'tx_hash': h,
            'contract': tx['contractAddress'],
        })

    # Collect all dates for price lookup
    all_dates = set()
    for t in nft_trades + token_trades:
        if t['date']:
            all_dates.add(t['date'][:10])
    for h, info in tx_eth.items():
        if info['date']:
            all_dates.add(info['date'][:10])

    # Fetch prices
    prices = fetch_prices(list(all_dates))

    # Compute totals
    # ETH in = ETH received (from sells, withdrawals, etc.)
    # ETH out = ETH spent (on buys, etc.)
    total_eth_in = 0
    total_eth_out = 0
    for h, info in tx_eth.items():
        total_eth_in += info['eth_in']
        total_eth_out += info['eth_out']

    print(f'\n=== SUMMARY ===')
    print(f'Total ETH received: {total_eth_in:.4f}')
    print(f'Total ETH spent: {total_eth_out:.4f}')
    print(f'Net: {total_eth_in - total_eth_out:+.4f}')

    print(f'\n--- Top NFT Collections by ETH Volume ---')
    sorted_nfts = sorted(nft_collections.items(), key=lambda x: x[1]['eth_in'] + x[1]['eth_out'], reverse=True)
    for sym, info in sorted_nfts[:15]:
        net = info['eth_in'] - info['eth_out']
        print(f'  {sym} ({info["name"]}): {info["buys"]} bought ({info["eth_out"]:.2f} ETH), {info["sells"]} sold ({info["eth_in"]:.2f} ETH) | Net: {net:+.2f} ETH')

    print(f'\n--- Real Token Activity ---')
    for sym in sorted(REAL_TOKENS):
        info = token_summary[sym]
        print(f'  {sym}: {info["in"]} in, {info["out"]} out')

    # Save everything
    data = {
        'trading_wallet': TRADING,
        'vault_wallet': VAULT,
        'nft_trades': nft_trades,
        'token_trades': token_trades,
        'nft_collections': {k: v for k, v in sorted_nfts},
        'eth_totals': {'eth_in': total_eth_in, 'eth_out': total_eth_out},
        'prices': prices,
        'fetched_at': datetime.utcnow().isoformat(),
    }

    with open('data/wallet_data.json', 'w') as f:
        json.dump(data, f, indent=2)
    print(f'\nSaved to data/wallet_data.json')


if __name__ == '__main__':
    main()
