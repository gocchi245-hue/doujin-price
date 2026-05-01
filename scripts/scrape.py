import json
import os
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

def scrape_dlsite_ranking():
    """PlaywrightでDLsiteの同人ランキングを取得"""
    print("[DLsite] ランキング取得開始")
    items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        try:
            page.goto('https://www.dlsite.com/maniax/ranking/day', timeout=60000)
            page.wait_for_timeout(5000)

            # product_idを含むリンクを全て取得
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

                dlsite_url = f"https://www.dlsite.com/maniax/work/=/product_id/{pid}.html"
                items.append({
                    'rank': rank,
                    'title': title,
                    'circle': '',
                    'genre': 'その他',
                    'price': 0,
                    'originalPrice': None,
                    'tags': [],
                    'dlsiteUrl': dlsite_url,
                    'productId': pid,
                    'rating': None,
                    'emoji': '📄',
                    'isOnSale': False,
                    'fanzaPrice': None,
                    'fanzaUrl': '',
                })

            print(f"[DLsite] ユニーク作品数: {len(items)}")

            # 各作品の詳細ページから情報を取得
            for item in items[:20]:
                try:
                    page.goto(item['dlsiteUrl'], timeout=30000)
                    page.wait_for_timeout(2000)

                    # タイトル再取得
                    title_el = page.query_selector('#work_name, [id*="work_name"]')
                    if title_el:
                        item['title'] = title_el.inner_text().strip()

                    # サークル名
                    circle_el = page.query_selector('[class*="maker_name"] a')
                    if circle_el:
                        item['circle'] = circle_el.inner_text().strip()

                    # 価格
                    price_el = page.query_selector('[class*="work_buy"] [class*="price"], [class*="work_price"]')
                    if price_el:
                        price_text = price_el.inner_text().strip()
                        nums = re.findall(r'[\d]+', price_text.replace(',', ''))
                        if nums:
                            item['price'] = int(nums[0])

                    # ジャンルタグ
                    tag_els = page.query_selector_all('[class*="work_genre"] a, [class*="genre"] a')
                    item['tags'] = [t.inner_text().strip() for t in tag_els[:5] if t.inner_text().strip()]

                    # ジャンル推定
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
            print(f"[DLsite] メインエラー: {e}")
            try:
                print(f"[DEBUG] ページタイトル: {page.title()}")
            except:
                pass

        finally:
            browser.close()

    print(f"[DLsite] 合計{len(items)}件取得完了")
    return items


def scrape_fanza_api(api_id, affiliate_id):
    """FANZA APIから同人作品を取得"""
    if not api_id or not affiliate_id:
        print("[FANZA] APIキー未設定 - スキップ")
        return {}

    import requests
    url = 'https://api.dmm.com/affiliate/v3/ItemList'
    params = {
        'api_id': api_id,
        'affiliate_id': affiliate_id,
        'site': 'FANZA',
        'service': 'digital',
        'floor': 'doujin',
        'hits': 50,
        'sort': 'rank',
        'output': 'json',
    }

    try:
        res = requests.get(url, params=params, timeout=30)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"[FANZA] 取得失敗: {e}")
        return {}

    fanza_items = {}
    for item in data.get('result', {}).get('items', []):
        title = item.get('title', '')
        price_info = item.get('prices', {})
        price = price_info.get('price', '0')
        price = int(''.join(c for c in str(price) if c.isdigit()) or '0')
        fanza_url = item.get('URL', '')
        fanza_items[title] = {'price': price, 'url': fanza_url}

    print(f"[FANZA] {len(fanza_items)}件取得完了")
    return fanza_items


def main():
    dlsite_items = scrape_dlsite_ranking()

    fanza_api_id = os.environ.get('FANZA_API_ID', '')
    fanza_affiliate_id = os.environ.get('FANZA_AFFILIATE_ID', '')
    fanza_items = scrape_fanza_api(fanza_api_id, fanza_affiliate_id)

    for item in dlsite_items:
        for ftitle, fdata in fanza_items.items():
            if item['title'] in ftitle or ftitle in item['title']:
                item['fanzaPrice'] = fdata['price']
                item['fanzaUrl'] = fdata['url']
                break

    output = {
        'updatedAt': datetime.now().strftime('%Y/%m/%d %H:%M'),
        'source': 'DLsite ranking + FANZA API',
        'items': dlsite_items,
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\ndata.json に{len(dlsite_items)}件保存しました")


if __name__ == '__main__':
    main()
