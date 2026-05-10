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
                'url': f"https://www.dlsite.com/maniax/work/=/product_id/{pid}.html",
                'productId': pid,
                'tags': [],
                'emoji': '📄',
                'rivalPrice': None,
                'rivalUrl': '',
            })

        print(f"[DLsite] ユニーク作品数: {len(items)}")

        for item in items[:20]:
            try:
                page.goto(item['url'], timeout=30000)
                page.wait_for_timeout(2000)

                title_el = page.query_selector('#work_name, [id*="work_name"]')
                if title_el:
                    item['title'] = title_el.inner_text().strip()

                circle_el = page.query_selector('[class*="maker_name"] a')
                if circle_el:
                    item['circle'] = circle_el.inner_text().strip()

                price = 0
                for selector in ['.work_buy_content .price', '[class*="work_buy"] [class*="price"]', '.work_price', '#work_price']:
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
                    'RPG': ['RPG', 'ロールプレイング'], '音声': ['音声', 'ASMR', 'ボイス', 'バイノーラル'],
                    'CG集': ['CG', 'イラスト集'], 'ノベル': ['ノベル', 'ADV', 'アドベンチャー'],
                    'マンガ': ['マンガ', '漫画', 'コミック'], 'アクション': ['アクション', 'ACT'],
                    'シミュレーション': ['シミュレーション', 'SLG'], '動画': ['動画', 'アニメーション'],
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
    """fanza_manual.txt からFANZAデータを読み込む"""
    filepath = 'fanza_manual.txt'
    items = []

    if not os.path.exists(filepath):
        print(f"[FANZA] {filepath} が見つかりません")
        return items

    print(f"[FANZA] {filepath} を読み込み中")

    with open(filepath, 'r', encoding='utf-8') as f:
        rank = 0
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            url_match = re.search(r'(https?://\S+)', line)
            url = url_match.group(1) if url_match else ''

            remaining = line.replace(url, '').strip() if url else line

            price_match = re.match(r'^(\d+)\s+(.+)', remaining)
            if price_match:
                price = int(price_match.group(1))
                title = price_match.group(2).strip()
            else:
                print(f"  [警告] 行{line_num}: パース失敗 → {line[:50]}")
                continue

            if title and price > 0:
                rank += 1
                items.append({
                    'rank': rank,
                    'title': title,
                    'price': price,
                    'url': url,
                    'circle': '',
                    'genre': '',
                    'tags': [],
                    'emoji': '📄',
                    'rivalPrice': None,
                    'rivalUrl': '',
                })
                print(f"  [{rank}] {title[:30]} / ¥{price}")

    print(f"[FANZA] {len(items)}件読み込み完了")
    return items


def load_fanza_api(api_id, affiliate_id):
    """FANZA APIから取得"""
    if not api_id or not affiliate_id:
        return []

    import requests
    print("[FANZA API] 取得開始")
    try:
        res = requests.get('https://api.dmm.com/affiliate/v3/ItemList', params={
            'api_id': api_id, 'affiliate_id': affiliate_id,
            'site': 'FANZA', 'service': 'digital', 'floor': 'doujin',
            'hits': 30, 'sort': 'rank', 'output': 'json',
        }, timeout=30)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"[FANZA API] 失敗: {e}")
        return []

    items = []
    for i, item in enumerate(data.get('result', {}).get('items', []), 1):
        title = item.get('title', '')
        price = item.get('prices', {}).get('price', '0')
        price = int(''.join(c for c in str(price) if c.isdigit()) or '0')
        items.append({
            'rank': i, 'title': title, 'price': price,
            'url': item.get('URL', ''), 'circle': '', 'genre': '', 'tags': [],
            'emoji': '📄', 'rivalPrice': None, 'rivalUrl': '',
        })

    print(f"[FANZA API] {len(items)}件取得完了")
    return items


def match_titles(t1, t2):
    """タイトルの柔軟なマッチング"""
    def norm(t):
        return re.sub(r'[　\s～〜・！？!?\-\[\]【】「」『』（）()＆&]+', '', t).lower()
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


def cross_match(dlsite_items, fanza_items):
    """双方向のマッチング"""
    dl_matched = 0
    fz_matched = 0

    # DLsite → FANZA
    for dl in dlsite_items:
        for fz in fanza_items:
            if match_titles(dl['title'], fz['title']):
                dl['rivalPrice'] = fz['price']
                dl['rivalUrl'] = fz['url']
                dl_matched += 1
                break

    # FANZA → DLsite
    for fz in fanza_items:
        for dl in dlsite_items:
            if match_titles(fz['title'], dl['title']):
                fz['rivalPrice'] = dl['price']
                fz['rivalUrl'] = dl['url']
                fz['circle'] = dl['circle']
                fz['genre'] = dl['genre']
                fz['tags'] = dl['tags']
                fz['emoji'] = dl['emoji']
                fz_matched += 1
                break

    print(f"[マッチング] DLsite→FANZA: {dl_matched}件一致")
    print(f"[マッチング] FANZA→DLsite: {fz_matched}件一致")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        dlsite_items = scrape_dlsite_ranking(page)
        page.close()
        browser.close()

    # FANZA
    fanza_api_id = os.environ.get('FANZA_API_ID', '')
    fanza_affiliate_id = os.environ.get('FANZA_AFFILIATE_ID', '')

    if fanza_api_id and fanza_affiliate_id:
        fanza_items = load_fanza_api(fanza_api_id, fanza_affiliate_id)
        fanza_method = 'api'
    else:
        fanza_items = load_fanza_manual()
        fanza_method = 'manual'

    # 双方向マッチング
    cross_match(dlsite_items, fanza_items)

    output = {
        'updatedAt': datetime.now().strftime('%Y/%m/%d %H:%M'),
        'fanzaMethod': fanza_method,
        'dlsiteItems': dlsite_items,
        'fanzaItems': fanza_items,
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n===== 完了 =====")
    print(f"DLsite: {len(dlsite_items)}件")
    print(f"FANZA: {len(fanza_items)}件")


if __name__ == '__main__':
    main()
