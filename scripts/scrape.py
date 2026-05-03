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

                price_el = page.query_selector('[class*="work_buy"] [class*="price"], [class*="work_price"]')
                if price_el:
                    price_text = price_el.inner_text().strip()
                    nums = re.findall(r'[\d]+', price_text.replace(',', ''))
                    if nums:
                        item['price'] = int(nums[0])

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


def scrape_fanza_ranking(page):
    """FANZAの同人ランキングをスクレイピング"""
    print("[FANZA] ランキング取得開始")
    fanza_data = {}

    try:
        # FANZAの同人ランキングページにアクセス
        page.goto('https://www.dmm.co.jp/dc/doujin/-/ranking/=/term=daily/', timeout=60000)
        page.wait_for_timeout(3000)

        # 年齢認証ボタンがあればクリック
        age_btn = page.query_selector('a[href*="age_check"], .ageCheck__link--yes, [class*="age"] a, a:has-text("はい"), a:has-text("Yes")')
        if age_btn:
            print("[FANZA] 年齢認証をクリック")
            age_btn.click()
            page.wait_for_timeout(3000)

        # もう一度ランキングページへ
        page.goto('https://www.dmm.co.jp/dc/doujin/-/ranking/=/term=daily/', timeout=60000)
        page.wait_for_timeout(5000)

        # 年齢認証再チェック
        age_btn = page.query_selector('a[href*="age_check"], .ageCheck__link--yes, [class*="age"] a, a:has-text("はい"), a:has-text("Yes")')
        if age_btn:
            age_btn.click()
            page.wait_for_timeout(3000)
            page.goto('https://www.dmm.co.jp/dc/doujin/-/ranking/=/term=daily/', timeout=60000)
            page.wait_for_timeout(5000)

        print(f"[FANZA] ページタイトル: {page.title()}")

        # 作品リンクを取得
        work_links = page.query_selector_all('a[href*="/dc/doujin/-/detail/"], a[href*="doujin"][href*="cid="]')
        print(f"[FANZA] 作品リンク数: {len(work_links)}")

        seen_titles = set()
        for link in work_links:
            href = link.get_attribute('href') or ''
            title = link.get_attribute('title') or link.inner_text().strip()

            if not title or len(title) < 3 or title in seen_titles:
                continue

            # 画像のaltからタイトルを取得する場合
            if not title or len(title) < 3:
                img = link.query_selector('img')
                if img:
                    title = img.get_attribute('alt') or ''

            if not title or len(title) < 3 or title in seen_titles:
                continue

            seen_titles.add(title)

            # URLを構築
            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = 'https://www.dmm.co.jp' + href

            fanza_data[title] = {
                'url': href,
                'price': None,
            }

        print(f"[FANZA] ユニーク作品数: {len(fanza_data)}")

        # 上位作品の価格を詳細ページから取得
        count = 0
        for title, data in list(fanza_data.items()):
            if count >= 20:
                break
            if not data['url']:
                continue

            try:
                page.goto(data['url'], timeout=30000)
                page.wait_for_timeout(2000)

                # 価格を取得
                price_el = page.query_selector('[class*="price"], .price, [class*="Price"]')
                if price_el:
                    price_text = price_el.inner_text().strip()
                    nums = re.findall(r'[\d]+', price_text.replace(',', ''))
                    if nums:
                        data['price'] = int(nums[0])

                count += 1
                print(f"  [FANZA] {title[:25]}... ¥{data['price']}")

            except Exception as e:
                print(f"  [FANZA] 詳細取得失敗: {title[:20]} - {e}")
                count += 1

    except Exception as e:
        print(f"[FANZA] エラー: {e}")
        try:
            print(f"[FANZA DEBUG] ページタイトル: {page.title()}")
            print(f"[FANZA DEBUG] URL: {page.url}")
        except:
            pass

    print(f"[FANZA] 合計{len(fanza_data)}件取得完了")
    return fanza_data


def scrape_fanza_api(api_id, affiliate_id):
    """FANZA公式APIから取得（APIキーがある場合）"""
    if not api_id or not affiliate_id:
        return {}

    import requests
    print("[FANZA API] 取得開始")

    try:
        res = requests.get('https://api.dmm.com/affiliate/v3/ItemList', params={
            'api_id': api_id,
            'affiliate_id': affiliate_id,
            'site': 'FANZA',
            'service': 'digital',
            'floor': 'doujin',
            'hits': 50,
            'sort': 'rank',
            'output': 'json',
        }, timeout=30)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"[FANZA API] 取得失敗: {e}")
        return {}

    fanza_items = {}
    for item in data.get('result', {}).get('items', []):
        title = item.get('title', '')
        price_info = item.get('prices', {})
        price = price_info.get('price', '0')
        price = int(''.join(c for c in str(price) if c.isdigit()) or '0')
        fanza_items[title] = {'price': price, 'url': item.get('URL', '')}

    print(f"[FANZA API] {len(fanza_items)}件取得完了")
    return fanza_items


def match_titles(dlsite_title, fanza_title):
    """タイトルの部分一致チェック（柔軟なマッチング）"""
    # 正規化: 記号・スペースを除去して比較
    def normalize(t):
        t = re.sub(r'[　\s～〜・！？!?\-\[\]【】「」『』（）()]+', '', t)
        return t.lower()

    dt = normalize(dlsite_title)
    ft = normalize(fanza_title)

    # 完全一致
    if dt == ft:
        return True

    # 部分一致（短い方が長い方に含まれる）
    shorter = dt if len(dt) <= len(ft) else ft
    longer = ft if len(dt) <= len(ft) else dt

    if len(shorter) >= 5 and shorter in longer:
        return True

    # 先頭N文字一致
    if len(dt) >= 8 and len(ft) >= 8 and dt[:8] == ft[:8]:
        return True

    return False


def merge_data(dlsite_items, fanza_data):
    """DLsiteとFANZAのデータをマッチング"""
    matched = 0
    for item in dlsite_items:
        for ftitle, fdata in fanza_data.items():
            if match_titles(item['title'], ftitle):
                item['fanzaPrice'] = fdata.get('price')
                item['fanzaUrl'] = fdata.get('url', '')
                matched += 1
                break

    print(f"[マッチング] {matched}/{len(dlsite_items)}件がFANZAと一致")
    return dlsite_items


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        # DLsiteランキング取得
        dlsite_items = scrape_dlsite_ranking(page)

        # FANZA: APIキーがあればAPI、なければスクレイピング
        fanza_api_id = os.environ.get('FANZA_API_ID', '')
        fanza_affiliate_id = os.environ.get('FANZA_AFFILIATE_ID', '')

        if fanza_api_id and fanza_affiliate_id:
            fanza_data = scrape_fanza_api(fanza_api_id, fanza_affiliate_id)
        else:
            fanza_data = scrape_fanza_ranking(page)

        browser.close()

    # マッチング
    merged = merge_data(dlsite_items, fanza_data)

    # JSON保存
    output = {
        'updatedAt': datetime.now().strftime('%Y/%m/%d %H:%M'),
        'source': 'DLsite ranking + FANZA ' + ('API' if fanza_api_id else 'scraping'),
        'fanzaMethod': 'api' if fanza_api_id else 'scraping',
        'items': merged,
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n===== 完了 =====")
    print(f"DLsite: {len(dlsite_items)}件")
    print(f"FANZA: {len(fanza_data)}件")
    matched_count = sum(1 for i in merged if i.get('fanzaPrice'))
    print(f"価格比較可能: {matched_count}件")
    print(f"data.json に保存しました")


if __name__ == '__main__':
    main()
