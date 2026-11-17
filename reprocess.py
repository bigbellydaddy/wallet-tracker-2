#!/usr/bin/env python3
"""Re-process wallet data with WETH transfers included in ETH mapping."""

import json
import os
from datetime import datetime

TRADING = '0x2546cf80eb6fb4ee0f22e1a9803Fb268FF7B591D'.lower()
VAULT = '0xa799242db91ec215c5a2f6628f4cceda9b478727'
WETH_ADDR = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'

# Load raw data that was already fetched
with open('data/wallet_data.json') as f:
    old = json.load(f)

prices = old.get('prices', {})

# We need the raw API responses. Let's re-fetch just the data we need
# Actually, let's re-run the full fetch with the fix
import urllib.request
import time

API_KEY = 'KI3JG1UGI7B7SNZIVZK943XRV8SFK83NHG'
TRADING_ORIG = '0x2546cf80eb6fb4ee0f22e1a9803Fb268FF7B591D'

def eth_api(module, action, address, **kwargs):
    params = f'chainid=1&module={module}&action={action}&address={address}&apikey={API_KEY}'
    for k, v in kwargs.items():
        params += f'&{k}={v}'
    url = f'https://api.etherscan.io/v2/api?{params}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    return resp.get('result', [])

def fetch_all_pages(module, action, address, page_size=1000):
    all_results = []
    page = 1
    while True:
        results = eth_api(module, action, address,
                         startblock=0, endblock=99999999,
                         page=page, offset=page_size, sort='asc')
        if not results or not isinstance(results, list):
            break
        all_results.extend(results)
        print(f'  Page {page}: {len(results)} (total: {len(all_results)})')
        if len(results) < page_size:
            break
        page += 1
        time.sleep(0.25)
    return all_results

print('Fetching normal txs...')
normal_txs = fetch_all_pages('account', 'txlist', TRADING_ORIG)
print('Fetching internal txs...')
internal_txs = fetch_all_pages('account', 'txlistinternal', TRADING_ORIG)
print('Fetching ERC-20 txs...')
erc20_txs = fetch_all_pages('account', 'tokentx', TRADING_ORIG)
print('Fetching NFT txs...')
nft_txs = fetch_all_pages('account', 'tokennfttx', TRADING_ORIG)

# Build tx_hash -> ETH value map INCLUDING WETH
tx_eth = {}
for tx in normal_txs:
    h = tx['hash']
    val = int(tx['value']) / 1e18
    ts = int(tx['timeStamp'])
    dt = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
    is_out = tx['from'].lower() == TRADING
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
    is_out = tx['from'].lower() == TRADING
    if h not in tx_eth:
        tx_eth[h] = {'date': dt, 'eth_out': 0, 'eth_in': 0}
    if is_out:
        tx_eth[h]['eth_out'] += val
    else:
        tx_eth[h]['eth_in'] += val

# WETH transfers count as ETH
weth_count = 0
for tx in erc20_txs:
    if tx.get('contractAddress', '').lower() != WETH_ADDR:
        continue
    h = tx['hash']
    val = int(tx['value']) / 1e18
    ts = int(tx['timeStamp'])
    dt = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
    is_in = tx['to'].lower() == TRADING
    if h not in tx_eth:
        tx_eth[h] = {'date': dt, 'eth_out': 0, 'eth_in': 0}
    if is_in:
        tx_eth[h]['eth_in'] += val
    else:
        tx_eth[h]['eth_out'] += val
    weth_count += 1

print(f'\nIncluded {weth_count} WETH transfers in ETH mapping')

# Count NFT transfers per tx_hash and direction, so we can split ETH evenly
nft_per_tx = {}
for tx in nft_txs:
    h = tx['hash']
    is_buy = tx['to'].lower() == TRADING
    key = (h, 'buy' if is_buy else 'sell')
    nft_per_tx[key] = nft_per_tx.get(key, 0) + 1

# Re-process NFT trades with ETH split across batch trades
nft_trades = []
nft_collections = {}
for tx in nft_txs:
    h = tx['hash']
    collection = tx.get('tokenName', 'Unknown')
    sym = tx.get('tokenSymbol', '?')
    is_buy = tx['to'].lower() == TRADING
    eth_info = tx_eth.get(h, {'date': '', 'eth_out': 0, 'eth_in': 0})
    total_eth = eth_info['eth_out'] if is_buy else eth_info['eth_in']
    key = (h, 'buy' if is_buy else 'sell')
    n_in_batch = nft_per_tx.get(key, 1)
    eth_val = total_eth / n_in_batch  # Split evenly across NFTs in same tx
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

    key2 = sym
    if key2 not in nft_collections:
        nft_collections[key2] = {'name': collection, 'buys': 0, 'sells': 0, 'eth_in': 0, 'eth_out': 0}
    if is_buy:
        nft_collections[key2]['buys'] += 1
        nft_collections[key2]['eth_out'] += eth_val
    else:
        nft_collections[key2]['sells'] += 1
        nft_collections[key2]['eth_in'] += eth_val

# Token trades (non-WETH)
token_summary = {}
token_trades = []
for tx in erc20_txs:
    sym = tx.get('tokenSymbol', '?')
    name = tx.get('tokenName', 'Unknown')
    if sym not in token_summary:
        token_summary[sym] = {'name': name, 'in': 0, 'out': 0, 'contract': tx['contractAddress']}
    is_in = tx['to'].lower() == TRADING
    if is_in:
        token_summary[sym]['in'] += 1
    else:
        token_summary[sym]['out'] += 1

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
    is_in = tx['to'].lower() == TRADING
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

# Totals
total_in = sum(info['eth_in'] for info in tx_eth.values())
total_out = sum(info['eth_out'] for info in tx_eth.values())

print(f'\n=== UPDATED SUMMARY (with WETH) ===')
print(f'Total ETH+WETH received: {total_in:.4f}')
print(f'Total ETH+WETH spent: {total_out:.4f}')
print(f'Net: {total_in - total_out:+.4f}')

print(f'\n--- Top NFT Collections ---')
sorted_nfts = sorted(nft_collections.items(), key=lambda x: x[1]['eth_in'] + x[1]['eth_out'], reverse=True)
for sym, info in sorted_nfts[:15]:
    net = info['eth_in'] - info['eth_out']
    print(f'  {sym}: {info["buys"]} bought ({info["eth_out"]:.2f} ETH), {info["sells"]} sold ({info["eth_in"]:.2f} ETH) | Net: {net:+.2f}')

data = {
    'trading_wallet': TRADING_ORIG,
    'vault_wallet': VAULT,
    'nft_trades': nft_trades,
    'token_trades': token_trades,
    'nft_collections': {k: v for k, v in sorted_nfts},
    'eth_totals': {'eth_in': total_in, 'eth_out': total_out},
    'prices': prices,
    'fetched_at': datetime.utcnow().isoformat(),
}

with open('data/wallet_data.json', 'w') as f:
    json.dump(data, f, indent=2)
print(f'\nSaved updated data to data/wallet_data.json')
