import json
import os
import re
from datetime import datetime
from playwright.sync_api import sync_playwright


def scrape_dlsite_ranking(page):
    """DLsiteの同人ランキングを取得"""
    print("[DLsite] ランキング取得開始")
    items = []

    try:
        page.goto('https://www.dlsite.com/maniax/ranking/day', timeout=60000)
        page.wait_for_timeout(5000)

        links = page.query_selector_all('a[href*="/product_id/RJ"]')
        print(f"[DLsite] product_idリンク数: {len(links)}")

        seen_ids = set()
        rank = 0
        for link in links:
            href = link.get_attribute('href') or ''
            match = re.search(r'product_id/(RJ\d+)', href)
            if not match:
                continue
            pid = match.group(1)
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            rank += 1
            if rank > 30:
                break

            title = link.get_attribute('title') or link.inner_text().strip()
            if not title or len(title) < 2:
                title = pid

            items.append({
                'rank': rank,
                'title': title,
                'circle': '',
                'genre': 'その他',
                'price': 0,
                'originalPrice': None,
                'tags': [],
                'dlsiteUrl': f"https://www.dlsite.com/maniax/work/=/product_id/{pid}.html",
                'productId': pid,
                'rating': None,
                'emoji': '📄',
                'isOnSale': False,
                'fanzaPrice': None,
                'fanzaUrl': '',
            })

        print(f"[DLsite] ユニーク作品数: {len(items)}")

        # 詳細ページから情報取得
        for item in items[:20]:
            try:
                page.goto(item['dlsiteUrl'], timeout=30000)
                page.wait_for_timeout(2000)

                title_el = page.query_selector('#work_name, [id*="work_name"]')
                if title_el:
                    item['title'] = title_el.inner_text().strip()

                circle_el = page.query_selector('[class*="maker_name"] a')
                if circle_el:
                    item['circle'] = circle_el.inner_text().strip()

                price = 0
                for selector in [
                    '.work_buy_content .price',
                    '[class*="work_buy"] [class*="price"]',
                    '.work_price',
                    '#work_price',
                ]:
                    price_el = page.query_selector(selector)
                    if price_el:
                        price_text = price_el.inner_text().strip()
                        price_match = re.search(r'([\d,]+)\s*円', price_text)
                        if price_match:
                            price = int(price_match.group(1).replace(',', ''))
                            break
                        nums = re.findall(r'[\d,]+', price_text)
                        for n in nums:
                            val = int(n.replace(',', ''))
                            if val >= 100:
                                price = val
                                break
                    if price > 0:
                        break

                item['price'] = price

                tag_els = page.query_selector_all('[class*="work_genre"] a, [class*="genre"] a')
                item['tags'] = [t.inner_text().strip() for t in tag_els[:5] if t.inner_text().strip()]

                all_text = item['title'] + ' ' + ' '.join(item['tags'])
                for g, kws in {
                    'RPG': ['RPG', 'ロールプレイング'],
                    '音声': ['音声', 'ASMR', 'ボイス', 'バイノーラル'],
                    'CG集': ['CG', 'イラスト集'],
                    'ノベル': ['ノベル', 'ADV', 'アドベンチャー'],
                    'マンガ': ['マンガ', '漫画', 'コミック'],
                    'アクション': ['アクション', 'ACT'],
                    'シミュレーション': ['シミュレーション', 'SLG'],
                    '動画': ['動画', 'アニメーション'],
                }.items():
                    if any(kw in all_text for kw in kws):
                        item['genre'] = g
                        break

                emoji_map = {'RPG':'⚔️','音声':'🎵','CG集':'🎨','ノベル':'📖','マンガ':'📚','アクション':'🎮','シミュレーション':'🏰','動画':'🎬','その他':'📄'}
                item['emoji'] = emoji_map.get(item['genre'], '📄')

                print(f"  [{item['rank']}] {item['title'][:30]} / {item['circle']} / ¥{item['price']}")

            except Exception as e:
                print(f"  [{item['rank']}] 詳細取得失敗: {e}")

    except Exception as e:
        print(f"[DLsite] エラー: {e}")

    print(f"[DLsite] 合計{len(items)}件取得完了")
    return items


def load_fanza_manual():
    """fanza_manual.txt から手動入力されたFANZAデータを読み込む

    フォーマット（1行に1作品）:
      価格 タイトル URL
    例:
      1320 魔王城のリリア https://www.dmm.co.jp/dc/doujin/...
      880 催眠音声 vol.3 https://www.dmm.co.jp/dc/doujin/...

    # で始まる行はコメント、空行はスキップ
    """
    filepath = 'fanza_manual.txt'
    fanza_data = {}

    if not os.path.exists(filepath):
        print(f"[FANZA手動] {filepath} が見つかりません - スキップ")
        return fanza_data

    print(f"[FANZA手動] {filepath} を読み込み中")

    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # 空行・コメント行をスキップ
            if not line or line.startswith('#'):
                continue

            # URLを抽出（行内のhttps://で始まる部分）
            url_match = re.search(r'(https?://\S+)', line)
            url = url_match.group(1) if url_match else ''

            # URLを除いた部分から価格とタイトルを取得
            remaining = line
            if url:
                remaining = line.replace(url, '').strip()

            # 先頭の数値を価格として取得
            price_match = re.match(r'^(\d+)\s+(.+)', remaining)
            if price_match:
                price = int(price_match.group(1))
                title = price_match.group(2).strip()
            else:
                print(f"  [警告] 行{line_num}: パース失敗 → {line[:50]}")
                continue

            if title and price > 0:
                fanza_data[title] = {
                    'price': price,
                    'url': url,
                }
                print(f"  [FANZA] {title[:25]}... ¥{price}")

    print(f"[FANZA手動] {len(fanza_data)}件読み込み完了")
    return fanza_data


def scrape_fanza_api(api_id, affiliate_id):
    """FANZA公式APIから取得"""
    if not api_id or not affiliate_id:
        return {}

    import requests
    print("[FANZA API] 取得開始")
    try:
        res = requests.get('https://api.dmm.com/affiliate/v3/ItemList', params={
            'api_id': api_id, 'affiliate_id': affiliate_id,
            'site': 'FANZA', 'service': 'digital', 'floor': 'doujin',
            'hits': 50, 'sort': 'rank', 'output': 'json',
        }, timeout=30)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"[FANZA API] 失敗: {e}")
        return {}

    items = {}
    for item in data.get('result', {}).get('items', []):
        title = item.get('title', '')
        price = item.get('prices', {}).get('price', '0')
        price = int(''.join(c for c in str(price) if c.isdigit()) or '0')
        items[title] = {'price': price, 'url': item.get('URL', '')}

    print(f"[FANZA API] {len(items)}件取得完了")
    return items


def match_titles(t1, t2):
    """タイトルの柔軟なマッチング"""
    def norm(t):
        return re.sub(r'[　\s～〜・！？!?\-\[\]【】「」『』（）()]+', '', t).lower()

    n1, n2 = norm(t1), norm(t2)
    if n1 == n2:
        return True
    shorter = n1 if len(n1) <= len(n2) else n2
    longer = n2 if len(n1) <= len(n2) else n1
    if len(shorter) >= 4 and shorter in longer:
        return True
    if len(n1) >= 6 and len(n2) >= 6 and n1[:6] == n2[:6]:
        return True
    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        # DLsiteランキング取得
        dlsite_items = scrape_dlsite_ranking(page)
        page.close()
        browser.close()

    # FANZA: APIキーがあればAPI、なければ手動ファイル
    fanza_api_id = os.environ.get('FANZA_API_ID', '')
    fanza_affiliate_id = os.environ.get('FANZA_AFFILIATE_ID', '')

    if fanza_api_id and fanza_affiliate_id:
        fanza_data = scrape_fanza_api(fanza_api_id, fanza_affiliate_id)
        fanza_method = 'api'
    else:
        fanza_data = load_fanza_manual()
        fanza_method = 'manual'

    # マッチング
    matched = 0
    for item in dlsite_items:
        for ftitle, fdata in fanza_data.items():
            if match_titles(item['title'], ftitle):
                item['fanzaPrice'] = fdata.get('price')
                item['fanzaUrl'] = fdata.get('url', '')
                matched += 1
                print(f"  [一致] {item['title'][:20]} ←→ {ftitle[:20]} (DL:¥{item['price']} / FZ:¥{fdata.get('price')})")
                break

    print(f"\n[マッチング] {matched}/{len(dlsite_items)}件がFANZAと一致")

    output = {
        'updatedAt': datetime.now().strftime('%Y/%m/%d %H:%M'),
        'source': f'DLsite ranking + FANZA {fanza_method}',
        'fanzaMethod': fanza_method,
        'items': dlsite_items,
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n===== 完了 =====")
    print(f"DLsite: {len(dlsite_items)}件")
    print(f"FANZA: {len(fanza_data)}件")
    print(f"価格比較可能: {matched}件")


if __name__ == '__main__':
    main()
